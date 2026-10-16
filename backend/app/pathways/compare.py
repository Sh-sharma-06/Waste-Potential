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

Screening checks (coarse, not strict):
  S1 — Distance: pathway is within max_distance_km.
  S2 — Capacity: facility capacity_tpd ≥ waste_tpd (rough check; no LP).
  S3 — Positive waste supply: waste_tpd > 0 (guaranteed by schema, but checked
       defensively).

Boundary rule (consistency with decision layer):
  All cost and GHG estimates use an ANNUAL boundary (tonnes/year, INR/year,
  kgCO2e/year) so they are directly comparable to the LP objective coefficients
  produced by cost.py and the GHG delta produced by carbon.py.

CRF import:
  Uses the standalone `crf()` function from app.decision.cost — the formula
  lives in exactly one place.

Design decisions:
  - No database calls — all inputs come from the validated request schema.
  - No hard-coded emission factors — uses emission_factors.get_factor().
  - Returns a list[PathwayResult] directly; the router serialises to JSON.
"""

from __future__ import annotations

from typing import Optional

from app.decision.cost import (
    DEFAULT_ASSET_LIFE_YEARS,
    DEFAULT_DISCOUNT_RATE,
    crf,
)
from app.decision.emission_factors import get_factor

from .schemas import PathwayCompareRequest, PathwayResult

# ---------------------------------------------------------------------------
# Per-pathway output derivation helpers
# ---------------------------------------------------------------------------

# Approximate conversion factors used for illustrative output estimates.
# These are INDICATIVE only — the actual mass/energy balance lives in the ML
# yield model (app.ml).  The frontend displays these as "indicative outputs".
_BIOGAS_M3_PER_TONNE = 100.0      # m³ biogas per tonne MSW (AD, indicative)
_COMPOST_TONNE_PER_TONNE = 0.30   # tonne compost per tonne feedstock (composting)
_RDF_TONNE_PER_TONNE = 0.55       # tonne RDF per tonne waste (pre-treatment + RDF)
_SYNGAS_MJ_PER_TONNE = 3_500.0    # MJ syngas per tonne waste (gasification, indicative)

_PATHWAY_OUTPUTS: dict[str, str] = {
    "anaerobic_digestion": "biogas_m3_d",
    "composting": "compost_t_d",
    "rdf": "rdf_t_d",
    "gasification": "syngas_mj_d",
    "incineration": "heat_mj_d",
    "landfill": "leachate_note",      # no positive output
}


def _derive_outputs(pathway: str, waste_tpd: float) -> dict[str, float]:
    """Return indicative daily output quantities for *pathway* at *waste_tpd* input.

    All outputs are labelled as illustrative in the warnings list by the caller.
    """
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
        # Rough steam/heat estimate: ~10 GJ per tonne
        return {"heat_mj_d": round(waste_tpd * 10_000.0, 2)}
    return {}  # unknown pathway — no output estimate


# ---------------------------------------------------------------------------
# Core screening logic
# ---------------------------------------------------------------------------

_DAYS_PER_YEAR: float = 365.25


def screen_pathway(
    pathway: str,
    request: PathwayCompareRequest,
    *,
    grid_factor: float,
    transport_factor: float,
) -> PathwayResult:
    """Run coarse feasibility screening for a single *pathway*.

    Parameters
    ----------
    pathway:
        Pathway identifier string (must be in request.pathways).
    request:
        Validated PathwayCompareRequest.
    grid_factor:
        kgCO2e / kWh — resolved by the router before calling this function.
    transport_factor:
        kgCO2e / tonne-km — resolved by the router.

    Returns
    -------
    PathwayResult
        All fields populated; feasible=False + reasons set if any check fails.
    """
    reasons: list[str] = []
    warnings: list[str] = []

    waste_tpy = request.waste_tpd * _DAYS_PER_YEAR  # annual tonnes

    # ------------------------------------------------------------------
    # S1 — Distance check (hard filter)
    # ------------------------------------------------------------------
    if request.distance_km > request.max_distance_km:
        reasons.append(
            f"Distance {request.distance_km:.1f} km exceeds maximum "
            f"{request.max_distance_km:.1f} km for pathway '{pathway}'."
        )

    # ------------------------------------------------------------------
    # S2 — Capacity check (coarse; leaves strict allocation to optimizer)
    # ------------------------------------------------------------------
    cap_tpd = request.capacity_tpd.get(pathway)
    if cap_tpd is not None and cap_tpd < request.waste_tpd:
        reasons.append(
            f"Pathway '{pathway}' capacity {cap_tpd:.1f} t/day is less than "
            f"available waste {request.waste_tpd:.1f} t/day. "
            "Partial allocation may be possible — refer to the LP optimizer."
        )

    # ------------------------------------------------------------------
    # S3 — Positive supply (defensive)
    # ------------------------------------------------------------------
    if request.waste_tpd <= 0:
        reasons.append("waste_tpd must be > 0.")

    feasible = len(reasons) == 0

    # ------------------------------------------------------------------
    # Financial estimates (annual boundary)
    # ------------------------------------------------------------------
    capex = request.capex_inr.get(pathway, 0.0)
    opex_yr = request.opex_inr_yr.get(pathway, 0.0)
    life_yr = request.asset_life_yr.get(pathway, DEFAULT_ASSET_LIFE_YEARS)
    dr = request.discount_rate if request.discount_rate > 0 else DEFAULT_DISCOUNT_RATE

    # Annualised CAPEX using CRF imported from app.decision.cost
    ann_capex = capex * crf(dr, life_yr) if capex > 0 else 0.0
    cost_inr_y = ann_capex + opex_yr

    # Electricity revenue / import cost (annual boundary)
    net_kwh_t = request.net_kwh_per_tonne.get(pathway, 0.0)
    net_kwh_yr = net_kwh_t * waste_tpy
    e_price = request.electricity_price_inr_kwh
    if net_kwh_yr > 0:
        elec_value_yr = net_kwh_yr * e_price          # revenue
    else:
        elec_value_yr = net_kwh_yr * e_price           # negative (import cost)
        cost_inr_y += abs(elec_value_yr)               # add import cost to costs
        elec_value_yr = 0.0                            # no export revenue

    gate_fee = request.gate_fee_inr_t.get(pathway, 0.0)
    gate_revenue_yr = gate_fee * waste_tpy

    revenue_inr_y = (
        (net_kwh_t * waste_tpy * e_price if net_kwh_t > 0 else 0.0)
        + gate_revenue_yr
    )
    annual_net_value_inr = revenue_inr_y - cost_inr_y
    e_net_kwh_d = net_kwh_t * request.waste_tpd  # kWh/day (signed)

    # ------------------------------------------------------------------
    # Illustrative GHG check (annual boundary; informational only)
    # ------------------------------------------------------------------
    direct_ghg_t = request.direct_ghg_kg_per_tonne.get(pathway, 0.0)
    direct_ghg_yr = direct_ghg_t * waste_tpy  # kgCO2e/year

    transport_ghg_yr = (
        request.distance_km * waste_tpy * transport_factor
    )  # kgCO2e/year

    elec_credit_yr = (
        max(0.0, net_kwh_yr) * grid_factor
    )  # kgCO2e/year avoided

    net_ghg_yr = direct_ghg_yr + transport_ghg_yr - elec_credit_yr

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

    outputs = _derive_outputs(pathway, request.waste_tpd)
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

    Resolves emission factors once and reuses them across all pathways
    to keep per-call overhead minimal.

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

    return [
        screen_pathway(
            pw,
            request,
            grid_factor=grid_factor,
            transport_factor=transport_factor,
        )
        for pw in request.pathways
    ]
