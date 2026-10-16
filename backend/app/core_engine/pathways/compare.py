"""compare.py — multi-pathway economic comparison for a single feedstock.

All values are ILLUSTRATIVE — replace CAPEX/OPEX defaults with validated data.
Currency: Indian Rupees (INR).  Mass basis: wet tonnes unless noted.

Units used throughout
---------------------
annual_net_value_inr   INR / year  (revenue_inr_y - cost_inr_y)
revenue_inr_y          INR / year
cost_inr_y             INR / year
e_net_kwh_d            kWh / day   (electrical net; thermal basis for pyrolysis)
capex_inr              INR         (overnight capital cost, illustrative)
opex_inr_per_t         INR / tonne wet input / year
transport_cost_inr_per_t_km  INR / tonne / km

Revenue components
------------------
electricity : e_net_kwh_d * 365 * tariff   [only when e_net > 0 AND grid_available]
compost     : compost_kg_d * 365 * compost_price
heat        : heat_surplus_kwh_d * 365 * heat_price  [AD only, when heat_surplus > 0]

Cost components
---------------
capex annualised : capex_inr * CRF(discount_rate, life_years)
opex             : opex_inr_per_t * tonnes_per_year
transport        : nearest_buyer_km * transport_cost_inr_per_t_km * tonnes_per_year

Capital Recovery Factor (CRF)
------------------------------
CRF(i, n) = i * (1 + i)^n / ((1 + i)^n - 1)   for i > 0
            = 1 / n                               for i == 0
"""
from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .feedstock import Feedstock
from .feasibility import PATHWAYS, check_pathway
from .composting import CompostingParams, simulate_composting
from .incineration import IncinerationParams, simulate_incineration
from .gasification import GasificationParams, simulate_gasification
from .pyrolysis import PyrolysisParams, simulate_pyrolysis


# ---------------------------------------------------------------------------
# LocationContext
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LocationContext:
    """Site- and market-specific context for economic comparison.

    Parameters
    ----------
    electricity_tariff_inr_per_kwh:
        Grid electricity selling price (INR / kWh).  Must be >= 0.
    compost_price_inr_per_kg:
        Compost product selling price (INR / kg).  Must be >= 0.
    heat_price_inr_per_kwh:
        Heat selling price (INR / kWh thermal).  Must be >= 0.
    nearest_buyer_km:
        Distance to the nearest product buyer / disposal site (km).
        Used for transport cost calculation.  Must be >= 0.
    transport_cost_inr_per_t_km:
        Freight cost (INR / tonne / km).  Must be >= 0.
    grid_available:
        True when the site has a grid connection capable of accepting exported
        electricity.  When False, electricity revenue is zero for all pathways.
    facilities:
        Optional list of dicts, each with keys ``pathway`` (str) and
        ``capacity_t_d`` (float, tonnes/day) and ``road_km`` (float, km).
        When provided, a pathway with no matching entry is marked infeasible
        with reason "no facility capacity within range".  When the list is
        empty or None, the capacity constraint is not applied.
    """

    electricity_tariff_inr_per_kwh: float
    compost_price_inr_per_kg: float
    heat_price_inr_per_kwh: float
    nearest_buyer_km: float
    transport_cost_inr_per_t_km: float
    grid_available: bool
    facilities: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self) -> None:
        for name, val in (
            ("electricity_tariff_inr_per_kwh", self.electricity_tariff_inr_per_kwh),
            ("compost_price_inr_per_kg", self.compost_price_inr_per_kg),
            ("heat_price_inr_per_kwh", self.heat_price_inr_per_kwh),
            ("nearest_buyer_km", self.nearest_buyer_km),
            ("transport_cost_inr_per_t_km", self.transport_cost_inr_per_t_km),
        ):
            if val < 0:
                raise ValueError(f"LocationContext.{name} must be >= 0; got {val}")


# ---------------------------------------------------------------------------
# PathwayCosts
# ---------------------------------------------------------------------------

# Default costs — ALL ILLUSTRATIVE, source="TBD", status="illustrative"
_DEFAULT_COSTS: Dict[str, Dict[str, Any]] = {
    "anaerobic_digestion": {
        "capex_inr":       40_000_000.0,   # ILLUSTRATIVE, source=TBD
        "opex_inr_per_t":  800.0,           # ILLUSTRATIVE, source=TBD
        "life_years":      20.0,            # ILLUSTRATIVE, source=TBD
        "discount_rate":   0.10,            # ILLUSTRATIVE, source=TBD
    },
    "composting": {
        "capex_inr":       8_000_000.0,    # ILLUSTRATIVE, source=TBD
        "opex_inr_per_t":  300.0,           # ILLUSTRATIVE, source=TBD
        "life_years":      15.0,            # ILLUSTRATIVE, source=TBD
        "discount_rate":   0.10,            # ILLUSTRATIVE, source=TBD
    },
    "incineration": {
        "capex_inr":       120_000_000.0,  # ILLUSTRATIVE, source=TBD
        "opex_inr_per_t":  1500.0,          # ILLUSTRATIVE, source=TBD
        "life_years":      25.0,            # ILLUSTRATIVE, source=TBD
        "discount_rate":   0.10,            # ILLUSTRATIVE, source=TBD
    },
    "gasification": {
        "capex_inr":       60_000_000.0,   # ILLUSTRATIVE, source=TBD
        "opex_inr_per_t":  900.0,           # ILLUSTRATIVE, source=TBD
        "life_years":      20.0,            # ILLUSTRATIVE, source=TBD
        "discount_rate":   0.10,            # ILLUSTRATIVE, source=TBD
    },
    "pyrolysis": {
        "capex_inr":       50_000_000.0,   # ILLUSTRATIVE, source=TBD
        "opex_inr_per_t":  1000.0,          # ILLUSTRATIVE, source=TBD
        "life_years":      20.0,            # ILLUSTRATIVE, source=TBD
        "discount_rate":   0.10,            # ILLUSTRATIVE, source=TBD
    },
}


@dataclass(frozen=True)
class PathwayCosts:
    """Capital and operating cost parameters for one pathway.

    All default values are ILLUSTRATIVE — replace with validated project data.

    Parameters
    ----------
    capex_inr:
        Overnight capital expenditure (INR).  Must be >= 0.
    opex_inr_per_t:
        Annual operating cost per tonne of wet feedstock processed (INR/t/y).
        Must be >= 0.
    life_years:
        Project life for capital recovery (years).  Must be > 0.
    discount_rate:
        Annual discount rate (fraction, e.g. 0.10 = 10 %).  Must be >= 0.
    """

    capex_inr: float
    opex_inr_per_t: float
    life_years: float
    discount_rate: float

    def __post_init__(self) -> None:
        if self.capex_inr < 0:
            raise ValueError(f"PathwayCosts.capex_inr must be >= 0; got {self.capex_inr}")
        if self.opex_inr_per_t < 0:
            raise ValueError(
                f"PathwayCosts.opex_inr_per_t must be >= 0; got {self.opex_inr_per_t}"
            )
        if self.life_years <= 0:
            raise ValueError(
                f"PathwayCosts.life_years must be > 0; got {self.life_years}"
            )
        if self.discount_rate < 0:
            raise ValueError(
                f"PathwayCosts.discount_rate must be >= 0; got {self.discount_rate}"
            )


# ---------------------------------------------------------------------------
# Capital Recovery Factor
# ---------------------------------------------------------------------------

def crf(discount_rate: float, life_years: float) -> float:
    """Capital Recovery Factor: annualises a lump-sum capital cost.

    Parameters
    ----------
    discount_rate:
        Annual discount rate as a fraction (e.g. 0.10 for 10 %).  Must be >= 0.
    life_years:
        Project life in years.  Must be > 0.

    Returns
    -------
    float
        CRF such that:  annual_payment = capex * CRF.
        For i > 0:  i * (1 + i)^n / ((1 + i)^n - 1)
        For i = 0:  1 / n   (equal principal repayment, no interest)

    Raises
    ------
    ValueError
        If discount_rate < 0 or life_years <= 0.
    """
    if discount_rate < 0:
        raise ValueError(f"discount_rate must be >= 0; got {discount_rate}")
    if life_years <= 0:
        raise ValueError(f"life_years must be > 0; got {life_years}")

    i = discount_rate
    n = life_years
    if i == 0.0:
        return 1.0 / n
    factor = (1.0 + i) ** n
    return i * factor / (factor - 1.0)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _check_facility_capacity(
    pathway: str,
    facilities: List[Dict[str, Any]],
) -> Optional[str]:
    """Return an infeasibility reason string if no facility matches pathway.

    Returns None when facilities list is empty/None (constraint not applied),
    or when at least one entry has a matching ``pathway`` key.
    """
    if not facilities:
        return None
    for fac in facilities:
        if fac.get("pathway") == pathway:
            return None
    return "no facility capacity within range"


def _run_ad(
    feedstock: Feedstock,
    ad_params: Optional[Any],
) -> Dict[str, Any]:
    """Run the anaerobic digestion simulator via engine.simulate.

    Builds a Params instance from feedstock fields that share names with Params
    (total_mass_kg_d, organic_fraction), using dataclasses.replace on defaults.
    Additional ad_params fields (ts_fraction, vs_of_ts, etc.) are applied when
    they exist on the Params dataclass.

    Parameters
    ----------
    feedstock:
        Validated Feedstock instance.
    ad_params:
        Optional mapping or frozen dataclass of extra Params overrides.
        Fields not present on Params are silently ignored.

    Returns
    -------
    dict
        Result from engine.simulate (includes e_net_kwh_d, warnings, status, …).
    """
    from app.core_engine.engine import simulate
    from app.core_engine.params import Params

    # Collect Params field names once
    params_fields = {f.name for f in dataclasses.fields(Params)}

    # Start with Feedstock fields that match Params field names
    overrides: Dict[str, Any] = {}
    for f in dataclasses.fields(feedstock):
        if f.name in params_fields:
            overrides[f.name] = getattr(feedstock, f.name)

    # Apply caller-supplied ad_params overrides (mapping or dataclass)
    if ad_params is not None:
        if dataclasses.is_dataclass(ad_params):
            for f in dataclasses.fields(ad_params):
                if f.name in params_fields:
                    overrides[f.name] = getattr(ad_params, f.name)
        else:
            # Treat as mapping
            for k, v in ad_params.items():
                if k in params_fields:
                    overrides[k] = v

    base = Params()
    p = dataclasses.replace(base, **overrides)
    return simulate(p)


def _electricity_revenue(
    e_net_kwh_d: float,
    tariff: float,
    grid_available: bool,
) -> float:
    """Annual electricity revenue (INR/y).

    Zero when e_net_kwh_d <= 0 or grid is unavailable.
    """
    if not grid_available or e_net_kwh_d <= 0:
        return 0.0
    return e_net_kwh_d * 365.0 * tariff


def _annual_cost(
    costs: PathwayCosts,
    tonnes_per_year: float,
    nearest_buyer_km: float,
    transport_cost_inr_per_t_km: float,
) -> float:
    """Annual total cost (INR/y): annualised CAPEX + OPEX + transport."""
    annual_capex = costs.capex_inr * crf(costs.discount_rate, costs.life_years)
    annual_opex = costs.opex_inr_per_t * tonnes_per_year
    annual_transport = nearest_buyer_km * transport_cost_inr_per_t_km * tonnes_per_year
    return annual_capex + annual_opex + annual_transport


# ---------------------------------------------------------------------------
# compare_pathways — public entry point
# ---------------------------------------------------------------------------

def compare_pathways(
    feedstock: Feedstock,
    context: LocationContext,
    costs: Optional[Dict[str, PathwayCosts]] = None,
    ad_params: Optional[Any] = None,
) -> List[Dict[str, Any]]:
    """Simulate all five pathways and rank them by annual net value.

    Parameters
    ----------
    feedstock:
        Validated :class:`~feedstock.Feedstock` instance describing the
        incoming waste stream.
    context:
        :class:`LocationContext` with market prices and site logistics.
    costs:
        Optional mapping from pathway name to :class:`PathwayCosts`.  Any
        missing pathway falls back to :data:`_DEFAULT_COSTS`.  When None,
        all pathways use the illustrative defaults.
    ad_params:
        Optional Params overrides for the anaerobic digestion pathway.
        Accepts a Params instance, a dataclass with overlapping field names,
        or a plain dict.  Fields not on Params are silently ignored.

    Returns
    -------
    list of dict
        One dict per pathway in :data:`~feasibility.PATHWAYS`, sorted:
        feasible pathways first (by annual_net_value_inr descending), then
        infeasible pathways (by annual_net_value_inr descending).

        Each dict contains:
        ``pathway``, ``feasible``, ``reasons`` (list[str]),
        ``outputs`` (simulator result dict), ``revenue_inr_y``,
        ``cost_inr_y``, ``annual_net_value_inr``, ``e_net_kwh_d``,
        ``status``, ``warnings`` (list[str]).
        All numeric values are plain Python floats (JSON serialisable).
    """
    costs = costs or {}
    tonnes_per_year = feedstock.total_mass_kg_d * 365.0 / 1000.0  # tonnes/year wet

    results: List[Dict[str, Any]] = []

    for pathway in PATHWAYS:
        # --- 1. Feasibility check ---
        feas = check_pathway(pathway, feedstock)
        feasible: bool = feas.feasible
        reasons: List[str] = list(feas.reasons)

        # --- 2. Capacity constraint ---
        capacity_reason = _check_facility_capacity(pathway, context.facilities)
        if capacity_reason is not None:
            feasible = False
            reasons.append(capacity_reason)

        # --- 3. Per-pathway costs ---
        if pathway in costs:
            pw_costs = costs[pathway]
        else:
            d = _DEFAULT_COSTS[pathway]
            pw_costs = PathwayCosts(
                capex_inr=d["capex_inr"],
                opex_inr_per_t=d["opex_inr_per_t"],
                life_years=d["life_years"],
                discount_rate=d["discount_rate"],
            )

        # --- 4. Run simulator ---
        if pathway == "anaerobic_digestion":
            outputs = _run_ad(feedstock, ad_params)
        elif pathway == "composting":
            outputs = simulate_composting(feedstock)
        elif pathway == "incineration":
            outputs = simulate_incineration(feedstock)
        elif pathway == "gasification":
            outputs = simulate_gasification(feedstock)
        else:  # pyrolysis
            outputs = simulate_pyrolysis(feedstock)

        # --- 5. Extract e_net_kwh_d ---
        # Pyrolysis uses e_net_energy_kwh_d (thermal); all others use e_net_kwh_d.
        e_net_kwh_d: float = float(
            outputs.get("e_net_kwh_d", outputs.get("e_net_energy_kwh_d", 0.0))
        )

        # --- 6. Revenue ---
        rev_elec = _electricity_revenue(
            e_net_kwh_d,
            context.electricity_tariff_inr_per_kwh,
            context.grid_available,
        )

        # Compost revenue (composting pathway only)
        rev_compost = 0.0
        compost_kg_d = outputs.get("compost_kg_d", 0.0)
        if compost_kg_d > 0:
            rev_compost = float(compost_kg_d) * 365.0 * context.compost_price_inr_per_kg

        # Heat revenue (AD only — heat_surplus_kwh_d may be present)
        rev_heat = 0.0
        heat_surplus_kwh_d = outputs.get("heat_surplus_kwh_d", 0.0)
        if heat_surplus_kwh_d > 0:
            rev_heat = float(heat_surplus_kwh_d) * 365.0 * context.heat_price_inr_per_kwh

        revenue_inr_y: float = rev_elec + rev_compost + rev_heat

        # --- 7. Annual cost ---
        cost_inr_y: float = _annual_cost(
            pw_costs,
            tonnes_per_year,
            context.nearest_buyer_km,
            context.transport_cost_inr_per_t_km,
        )

        annual_net_value_inr: float = revenue_inr_y - cost_inr_y

        # --- 8. Aggregate warnings ---
        warnings: List[str] = list(outputs.get("warnings", []))
        if not feasible:
            for r in reasons:
                if r not in warnings:
                    warnings.append(r)

        results.append({
            "pathway": pathway,
            "feasible": feasible,
            "reasons": reasons,
            "outputs": outputs,
            "revenue_inr_y": revenue_inr_y,
            "cost_inr_y": cost_inr_y,
            "annual_net_value_inr": annual_net_value_inr,
            "e_net_kwh_d": e_net_kwh_d,
            "status": "illustrative_estimate",
            "warnings": warnings,
        })

    # --- 9. Sort: feasible first, then by annual_net_value_inr descending ---
    results.sort(
        key=lambda r: (0 if r["feasible"] else 1, -r["annual_net_value_inr"])
    )

    return results


# ---------------------------------------------------------------------------
# compare_with_demand — demand-side enrichment of compare_pathways rows
# ---------------------------------------------------------------------------

def compare_with_demand(
    feedstock,
    context: "LocationContext",
    sinks: "List",
    weather=None,
    costs=None,
    ad_params=None,
) -> "List[Dict[str, Any]]":
    """Run compare_pathways and enrich each row with demand-matching results.

    Calls :func:`compare_pathways` to obtain the base pathway rows, then for
    each pathway extracts available products, runs
    :func:`~demand.match_supply`, attaches a :class:`~resources.ResourceLedger`
    (as a plain dict), and recomputes ``annual_net_value_inr`` from matched
    supply revenue only.

    Products extracted per pathway
    --------------------------------
    ``electricity``
        ``e_net_kwh_d`` when > 0 and ``context.grid_available`` is True.
    ``heat``
        AD: ``heat_surplus_kwh_d`` when > 0.
        Pyrolysis: ``e_net_energy_kwh_d`` when > 0 (product thermal energy).
    ``biogas``
        AD: ``ch4_nm3_d * LHV_CH4_KWH_NM3`` (chemical energy of methane).

    Weather
    -------
    When *weather* is a :class:`~weather.WeatherContext` instance the feedstock
    moisture is adjusted (``enabled=True``) before simulation.

    Sorting
    -------
    Infeasible pathways are always sorted after feasible ones.  Within each
    group rows are sorted by the recomputed ``annual_net_value_inr`` descending.

    Parameters
    ----------
    feedstock:
        :class:`~feedstock.Feedstock` base instance.
    context:
        :class:`~compare.LocationContext`.
    sinks:
        List of :class:`~demand.DemandSink` instances.  May be empty.
    weather:
        Optional :class:`~weather.WeatherContext`.  When provided, feedstock
        moisture is adjusted before simulation.
    costs:
        Optional per-pathway :class:`~compare.PathwayCosts` overrides.
    ad_params:
        Optional AD Params overrides (see :func:`compare_pathways`).

    Returns
    -------
    list of dict
        All keys from :func:`compare_pathways` plus:

        ``resources`` dict
            :class:`~resources.ResourceLedger` as a plain dict.
        ``matched_kwh_d`` float
            Total kWh/day matched to sinks.
        ``unmatched_kwh_d`` dict[str, float]
            Unallocated supply per product [kWh/day].
        ``supply_revenue_inr_y`` float
            Annual revenue from matched allocations only [INR/year].
        ``customer_split`` dict
            ``{"home": float, "industry": float}`` kWh/day split by class.
        ``annual_net_value_inr`` float
            Recomputed as ``supply_revenue_inr_y - cost_inr_y``.
    """
    # Late imports to avoid circular dependency and forbidden top-level imports
    import dataclasses as _dc
    from app.core_engine.engine import LHV_CH4_KWH_NM3
    from .demand import match_supply
    from .resources import ledger_from_result
    from .weather import adjust_feedstock_moisture

    # Optionally adjust feedstock moisture from weather
    active_feedstock = feedstock
    if weather is not None:
        active_feedstock, _ = adjust_feedstock_moisture(
            feedstock, weather, enabled=True
        )

    # Base comparison rows
    base_rows: List[Dict[str, Any]] = compare_pathways(
        active_feedstock, context, costs=costs, ad_params=ad_params
    )

    enriched: List[Dict[str, Any]] = []

    for row in base_rows:
        pathway: str = row["pathway"]
        outputs: Dict[str, Any] = row["outputs"]

        # --- Build product supply dict [kWh/d] ---
        products: Dict[str, float] = {}

        e_net = float(outputs.get("e_net_kwh_d", outputs.get("e_net_energy_kwh_d", 0.0)))
        if e_net > 0 and context.grid_available:
            products["electricity"] = e_net

        # Heat surplus (AD) or product thermal energy (pyrolysis)
        heat_surplus = float(outputs.get("heat_surplus_kwh_d", 0.0))
        if heat_surplus > 0:
            products["heat"] = heat_surplus
        elif pathway == "pyrolysis":
            pyr_net = float(outputs.get("e_net_energy_kwh_d", 0.0))
            if pyr_net > 0:
                products["heat"] = pyr_net

        # Biogas energy (AD only: ch4_nm3_d × LHV)
        if pathway == "anaerobic_digestion":
            ch4_nm3_d = float(outputs.get("ch4_nm3_d", 0.0))
            biogas_kwh = ch4_nm3_d * LHV_CH4_KWH_NM3
            if biogas_kwh > 0:
                products["biogas"] = biogas_kwh

        # --- Match supply to sinks ---
        match = match_supply(products, list(sinks))
        allocations: List[Dict[str, Any]] = match["allocations"]
        unmatched_kwh_d: Dict[str, float] = match["unmatched_kwh_d"]
        matched_kwh_d: float = float(match["matched_kwh_d"])

        # --- Annual revenue from matched allocations ---
        supply_revenue_inr_y: float = sum(
            a["revenue_inr_d"] * 365.0 for a in allocations
        )

        # --- Customer split [kWh/d] ---
        home_kwh: float = 0.0
        industry_kwh: float = 0.0
        for alloc in allocations:
            sink_name = alloc["sink"]
            kwh = float(alloc["kwh_d"])
            # Look up class from the original sinks list
            matched_sink = next(
                (s for s in sinks if s.name == sink_name), None
            )
            if matched_sink is not None:
                if matched_sink.customer_class == "home":
                    home_kwh += kwh
                else:
                    industry_kwh += kwh

        customer_split: Dict[str, float] = {
            "home": float(home_kwh),
            "industry": float(industry_kwh),
        }

        # --- Resource ledger ---
        ledger = ledger_from_result(pathway, outputs)
        ledger_dict: Dict[str, Any] = _dc.asdict(ledger)

        # --- Recomputed annual net value ---
        cost_inr_y: float = float(row["cost_inr_y"])
        annual_net_value_inr: float = supply_revenue_inr_y - cost_inr_y

        # --- Assemble enriched row ---
        new_row: Dict[str, Any] = dict(row)   # shallow copy — all values immutable
        new_row["resources"] = ledger_dict
        new_row["matched_kwh_d"] = matched_kwh_d
        new_row["unmatched_kwh_d"] = unmatched_kwh_d
        new_row["supply_revenue_inr_y"] = supply_revenue_inr_y
        new_row["customer_split"] = customer_split
        new_row["annual_net_value_inr"] = annual_net_value_inr

        enriched.append(new_row)

    # Re-sort: feasible first, then descending recomputed annual_net_value_inr
    enriched.sort(
        key=lambda r: (0 if r["feasible"] else 1, -r["annual_net_value_inr"])
    )

    return enriched
