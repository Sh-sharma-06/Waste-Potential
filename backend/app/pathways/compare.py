"""
Coarse feasibility screening for waste treatment pathways.

Purpose
-------
This module performs a SCREENING pass only — it is NOT a substitute for the
LP optimizer in app.decision.optimizer.  Its job is to:

  1. Reject pathways that are physically or logistically impossible before the
     expensive LP allocation step is triggered.
  2. Produce illustrative annualised cost / revenue / GHG estimates so the
     frontend can show a ranked summary card.

P3 integration (Task 5)
-----------------------
When a request carries P3 optional fields the screening pipeline:

  A. Feedstock characterisation — calls ``get_stream(location_id)`` to obtain
     moisture, LHV, ash and contamination fractions for the site.
  B. ML yield override — when both ``crop_type`` and ``area_ha`` are provided,
     calls ``YieldPredictor().predict_yield()`` to replace the request's
     waste_tpd with the predicted daily biomass (converted from kg → tonnes).
  C. Location context — calls ``get_location_context(location_id)`` to obtain
     the site electricity tariff, compost/heat prices, ambient weather, and a
     list of demand sinks.
  D. Revenue matching — calls ``match_demand_greedy(e_net_kwh_d, sinks)`` to
     compute revenue from actual demand sinks rather than a flat e-price;
     uses the returned total_revenue_inr_d × 365.25 as revenue_inr_y.
  E. Spatial lookup — if the location context carries facility records with a
     ``road_km`` key matching the pathway, that distance is used instead of the
     request's ``distance_km``.

When the optional fields are absent the module falls back to the original
flat-price revenue calculation so all existing unit tests continue to pass.

Screening checks (coarse, not strict):
  S1 — Distance: pathway is within max_distance_km.
  S2 — Capacity: facility capacity_tpd ≥ waste_tpd (rough check; no LP).
  S3 — Positive waste supply: waste_tpd > 0.

Boundary rule:
  All cost / GHG estimates use an ANNUAL boundary (× 365.25).

CRF import:
  Uses the standalone ``crf()`` from app.decision.cost.
"""

from __future__ import annotations

from typing import Optional

from app.data.demand import match_demand_greedy
from app.data.service import get_location_context, get_stream
from app.decision.cost import (
    DEFAULT_ASSET_LIFE_YEARS,
    DEFAULT_DISCOUNT_RATE,
    crf,
)
from app.decision.emission_factors import get_factor
from app.ml.predictor import YieldPredictor

from .schemas import PathwayCompareRequest, PathwayResult

# ---------------------------------------------------------------------------
# Per-pathway output derivation helpers
# ---------------------------------------------------------------------------

# Approximate conversion factors used for illustrative output estimates.
_BIOGAS_M3_PER_TONNE = 100.0      # m³ biogas per tonne MSW (AD, indicative)
_COMPOST_TONNE_PER_TONNE = 0.30   # tonne compost per tonne feedstock
_RDF_TONNE_PER_TONNE = 0.55       # tonne RDF per tonne waste
_SYNGAS_MJ_PER_TONNE = 3_500.0    # MJ syngas per tonne waste (gasification)

_PATHWAY_OUTPUTS: dict[str, str] = {
    "anaerobic_digestion": "biogas_m3_d",
    "composting": "compost_t_d",
    "rdf": "rdf_t_d",
    "gasification": "syngas_mj_d",
    "incineration": "heat_mj_d",
    "landfill": "leachate_note",
}


def _derive_outputs(pathway: str, waste_tpd: float) -> dict[str, float]:
    """Return indicative daily output quantities for *pathway* at *waste_tpd* input."""
    p = pathway.lower()
    if "anaerobic" in p or "ad" == p or "biogas" in p:
        return {"biogas_m3_d": round(waste_tpd * _BIOGAS_M3_PER_TONNE, 2)}
    if "compost" in p:
        return {"compost_t_d": round(waste_tpd * _COMPOST_TONNE_PER_TONNE, 2)}
    if "rdf" in p:
        return {"rdf_t_d": round(waste_tpd * _RDF_TONNE_PER_TONNE, 2)}
    if "gasif" in p or "syngas" in p:
        return {"syngas_mj_d": round(waste_tpd * _SYNGAS_MJ_PER_TONNE, 2)}
    if "inciner" in p or "wte" in p:
        return {"heat_mj_d": round(waste_tpd * 10_000.0, 2)}
    return {}


# ---------------------------------------------------------------------------
# P3 integration helpers
# ---------------------------------------------------------------------------

_DAYS_PER_YEAR: float = 365.25

_KG_PER_TONNE: float = 1_000.0


def _resolve_waste_tpd(request: PathwayCompareRequest) -> tuple[float, list[str]]:
    """Return (effective_waste_tpd, warnings).

    If ``crop_type`` and ``area_ha`` are both provided, calls YieldPredictor to
    override the request's waste_tpd with the ML-predicted daily biomass.
    Otherwise returns request.waste_tpd unchanged.
    """
    warnings: list[str] = []

    if request.crop_type is not None and request.area_ha is not None and request.area_ha > 0:
        si = request.soil_index if request.soil_index is not None else 0.75
        try:
            pred = YieldPredictor().predict_yield(request.crop_type, request.area_ha, si)
            waste_tpd = pred["total_mass_kg_d"] / _KG_PER_TONNE
            warnings.append(
                f"waste_tpd overridden by YieldPredictor to {waste_tpd:.4f} t/day "
                f"(crop={request.crop_type}, area={request.area_ha} ha, "
                f"soil_index={si:.2f})."
            )
        except Exception as exc:  # noqa: BLE001
            warnings.append(
                f"YieldPredictor failed ({exc}); falling back to request.waste_tpd."
            )
            waste_tpd = request.waste_tpd
    else:
        waste_tpd = request.waste_tpd

    return waste_tpd, warnings


def _resolve_distance_km(
    pathway: str,
    request: PathwayCompareRequest,
    facilities: list[dict],
) -> float:
    """Return the road distance for *pathway*.

    Checks the location-context facility list for a matching ``pathway`` key
    with a ``road_km`` entry.  Falls back to ``request.distance_km``.
    """
    p_lower = pathway.lower()
    for fac in facilities:
        if fac.get("pathway", "").lower() == p_lower and "road_km" in fac:
            return float(fac["road_km"])
    return request.distance_km


def _resolve_electricity_price(ctx: dict) -> float:
    """Extract electricity tariff from a LocationContext dict.

    Handles both the wrapped {value, meta} form and a plain float.
    """
    raw = ctx.get("electricity_tariff_inr_per_kwh", 0.0)
    if isinstance(raw, dict):
        return float(raw.get("value", 0.0))
    return float(raw)


def _resolve_sinks(ctx: dict) -> list[dict]:
    """Extract sinks list from a LocationContext dict."""
    return list(ctx.get("sinks", []))


def _resolve_revenue_with_sinks(
    e_net_kwh_d: float,
    waste_tpd: float,
    gate_fee: float,
    sinks: list[dict],
) -> tuple[float, list[str]]:
    """Compute annual revenue using the greedy demand matcher.

    Returns (revenue_inr_y, warnings).
    """
    warnings: list[str] = []
    gate_revenue_yr = gate_fee * waste_tpd * _DAYS_PER_YEAR

    if e_net_kwh_d > 0 and sinks:
        match = match_demand_greedy(e_net_kwh_d, sinks)
        daily_revenue = match["total_revenue_inr_d"]
        revenue_inr_y = daily_revenue * _DAYS_PER_YEAR + gate_revenue_yr
        warnings.append(
            f"Energy revenue from greedy sink matcher: "
            f"{daily_revenue:.2f} INR/day matched across {len(sinks)} sink(s) "
            f"({match['total_matched_kwh_d']:.2f}/{e_net_kwh_d:.2f} kWh/day absorbed)."
        )
    else:
        revenue_inr_y = gate_revenue_yr

    return revenue_inr_y, warnings


# ---------------------------------------------------------------------------
# Core screening logic
# ---------------------------------------------------------------------------


def screen_pathway(
    pathway: str,
    request: PathwayCompareRequest,
    *,
    grid_factor: float,
    transport_factor: float,
    # P3 context objects — pre-resolved by evaluate_pathways() for efficiency
    waste_tpd: Optional[float] = None,
    facilities: Optional[list[dict]] = None,
    sinks: Optional[list[dict]] = None,
    electricity_price_override: Optional[float] = None,
    yield_warnings: Optional[list[str]] = None,
) -> PathwayResult:
    """Run coarse feasibility screening for a single *pathway*.

    Parameters
    ----------
    pathway:
        Pathway identifier string.
    request:
        Validated PathwayCompareRequest.
    grid_factor:
        kgCO2e / kWh — resolved by the router before calling this function.
    transport_factor:
        kgCO2e / tonne-km.
    waste_tpd:
        Effective waste throughput in t/day.  When provided (from
        ``_resolve_waste_tpd``), overrides ``request.waste_tpd``.
    facilities:
        List of facility dicts from LocationContext (used for road_km lookup).
    sinks:
        List of SinkEntry dicts from LocationContext (used for revenue matching).
    electricity_price_override:
        Tariff from LocationContext; takes precedence over
        ``request.electricity_price_inr_kwh`` when sinks are NOT available.
    yield_warnings:
        Pre-computed YieldPredictor warnings to carry into the result.

    Returns
    -------
    PathwayResult
    """
    reasons: list[str] = []
    warnings: list[str] = list(yield_warnings or [])

    effective_waste_tpd = waste_tpd if waste_tpd is not None else request.waste_tpd
    effective_facilities = facilities or []
    effective_sinks = sinks or []

    waste_tpy = effective_waste_tpd * _DAYS_PER_YEAR  # annual tonnes

    # ------------------------------------------------------------------
    # Resolve road distance (prefer location-context facility record)
    # ------------------------------------------------------------------
    distance_km = _resolve_distance_km(pathway, request, effective_facilities)

    # ------------------------------------------------------------------
    # S1 — Distance check (hard filter)
    # ------------------------------------------------------------------
    if distance_km > request.max_distance_km:
        reasons.append(
            f"Distance {distance_km:.1f} km exceeds maximum "
            f"{request.max_distance_km:.1f} km for pathway '{pathway}'."
        )

    # ------------------------------------------------------------------
    # S2 — Capacity check (coarse)
    # ------------------------------------------------------------------
    cap_tpd = request.capacity_tpd.get(pathway)
    if cap_tpd is not None and cap_tpd < effective_waste_tpd:
        reasons.append(
            f"Pathway '{pathway}' capacity {cap_tpd:.1f} t/day is less than "
            f"available waste {effective_waste_tpd:.1f} t/day. "
            "Partial allocation may be possible — refer to the LP optimizer."
        )

    # ------------------------------------------------------------------
    # S3 — Positive supply
    # ------------------------------------------------------------------
    if effective_waste_tpd <= 0:
        reasons.append("waste_tpd must be > 0.")

    feasible = len(reasons) == 0

    # ------------------------------------------------------------------
    # Financial estimates (annual boundary)
    # ------------------------------------------------------------------
    capex = request.capex_inr.get(pathway, 0.0)
    opex_yr = request.opex_inr_yr.get(pathway, 0.0)
    life_yr = request.asset_life_yr.get(pathway, DEFAULT_ASSET_LIFE_YEARS)
    dr = request.discount_rate if request.discount_rate > 0 else DEFAULT_DISCOUNT_RATE

    ann_capex = capex * crf(dr, life_yr) if capex > 0 else 0.0
    cost_inr_y = ann_capex + opex_yr

    # Net electricity (kWh/day) — used for both revenue and GHG credit
    net_kwh_t = request.net_kwh_per_tonne.get(pathway, 0.0)
    e_net_kwh_d = net_kwh_t * effective_waste_tpd   # kWh/day (signed)
    net_kwh_yr = net_kwh_t * waste_tpy

    gate_fee = request.gate_fee_inr_t.get(pathway, 0.0)

    # ------------------------------------------------------------------
    # Revenue: prefer greedy sink matching when sinks are available
    # ------------------------------------------------------------------
    if effective_sinks:
        revenue_inr_y, sink_warnings = _resolve_revenue_with_sinks(
            e_net_kwh_d, effective_waste_tpd, gate_fee, effective_sinks
        )
        warnings.extend(sink_warnings)
        # Grid import cost still applies when net consumption
        if e_net_kwh_d < 0:
            e_price = electricity_price_override or request.electricity_price_inr_kwh
            cost_inr_y += abs(e_net_kwh_d) * _DAYS_PER_YEAR * e_price
    else:
        # Legacy flat-price path (backwards-compatible)
        e_price = electricity_price_override if electricity_price_override is not None \
            else request.electricity_price_inr_kwh
        gate_revenue_yr = gate_fee * waste_tpy
        if net_kwh_yr > 0:
            elec_value_yr = net_kwh_yr * e_price
        else:
            elec_value_yr = 0.0
            cost_inr_y += abs(net_kwh_yr) * e_price
        revenue_inr_y = (net_kwh_yr * e_price if net_kwh_yr > 0 else 0.0) + gate_revenue_yr

    annual_net_value_inr = revenue_inr_y - cost_inr_y

    # ------------------------------------------------------------------
    # Illustrative GHG (informational only)
    # ------------------------------------------------------------------
    direct_ghg_t = request.direct_ghg_kg_per_tonne.get(pathway, 0.0)
    direct_ghg_yr = direct_ghg_t * waste_tpy
    transport_ghg_yr = distance_km * waste_tpy * transport_factor
    elec_credit_yr = max(0.0, net_kwh_yr) * grid_factor
    net_ghg_yr = direct_ghg_yr + transport_ghg_yr - elec_credit_yr

    # ------------------------------------------------------------------
    # Warnings
    # ------------------------------------------------------------------
    if not feasible:
        warnings.append(
            "Financial and GHG estimates are illustrative; pathway has been rejected."
        )

    if capex == 0.0 and opex_yr == 0.0:
        warnings.append(
            f"No cost data supplied for pathway '{pathway}'. "
            "Cost estimates are zero — supply capex_inr and opex_inr_yr for accurate results."
        )

    if direct_ghg_t == 0.0:
        warnings.append(
            f"No direct GHG factor supplied for pathway '{pathway}'. "
            "GHG estimate excludes process emissions."
        )

    warnings.append(
        "Output quantities are indicative only — based on generic conversion "
        "factors. Use the ML yield model for site-specific estimates."
    )

    outputs = _derive_outputs(pathway, effective_waste_tpd)
    outputs["net_ghg_kgco2e_y"] = round(net_ghg_yr, 2)

    status = "feasible" if feasible else "rejected"

    return PathwayResult(
        pathway=pathway,
        feasible=feasible,
        reasons=reasons,
        outputs=outputs,
        revenue_inr_y=round(revenue_inr_y, 2),
        cost_inr_y=round(cost_inr_y, 2),
        annual_net_value_inr=round(annual_net_value_inr, 2),
        e_net_kwh_d=round(e_net_kwh_d, 4),
        status=status,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def evaluate_pathways(
    request: PathwayCompareRequest,
    *,
    region: Optional[str] = None,
    operator_overrides: Optional[dict[str, float]] = None,
) -> list[PathwayResult]:
    """Screen all pathways in *request* and return one PathwayResult per pathway.

    P3 integration:
      - Calls ``get_stream(location_id)`` for feedstock characterisation.
      - Calls ``get_location_context(location_id)`` for tariffs, facilities,
        weather and sinks.
      - When crop_type + area_ha are present, calls YieldPredictor to derive
        effective waste_tpd from ML predictions.
      - Uses greedy demand matching (``match_demand_greedy``) for energy revenue
        when sinks are available from the location context.

    Falls back gracefully to the original flat-price behaviour when the P3
    optional fields are absent or when service calls fail.

    Parameters
    ----------
    request:
        Validated PathwayCompareRequest from the router.
    region:
        ISO region code; forwarded to get_factor() for regional grid factors.
    operator_overrides:
        Operator-supplied emission factor overrides.

    Returns
    -------
    list[PathwayResult]
        One entry per pathway in request.pathways, in the same order.
    """
    overrides = operator_overrides or {}
    grid_factor = get_factor(
        "grid_electricity", region=region, operator_overrides=overrides
    )
    transport_factor = get_factor(
        "transport_road", region=region, operator_overrides=overrides
    )

    # ------------------------------------------------------------------
    # P3 data lookups (once per evaluate_pathways call)
    # ------------------------------------------------------------------
    # Feedstock characterisation (not yet threaded into mass balance — Phase 5b)
    _stream = get_stream(request.location_id)  # noqa: F841 — reserved for Phase 5b

    ctx = get_location_context(request.location_id)
    facilities: list[dict] = ctx.get("facilities", [])
    sinks: list[dict] = _resolve_sinks(ctx)

    # Electricity tariff from location context (used only when no sinks)
    electricity_price_override = _resolve_electricity_price(ctx)
    # If the caller explicitly set a non-zero price, prefer theirs
    if request.electricity_price_inr_kwh > 0:
        electricity_price_override = request.electricity_price_inr_kwh

    # ML yield prediction (shared across all pathways)
    effective_waste_tpd, yield_warnings = _resolve_waste_tpd(request)

    return [
        screen_pathway(
            pw,
            request,
            grid_factor=grid_factor,
            transport_factor=transport_factor,
            waste_tpd=effective_waste_tpd,
            facilities=facilities,
            sinks=sinks,
            electricity_price_override=electricity_price_override,
            yield_warnings=yield_warnings,
        )
        for pw in request.pathways
    ]
