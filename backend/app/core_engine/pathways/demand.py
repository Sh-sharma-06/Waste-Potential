"""demand.py — Demand-side matching for waste-to-energy pathway outputs.

Pure functions: no file, network, or DB access.
All values are ILLUSTRATIVE unless the caller provides validated data.

Units
-----
demand_kwh_d        kWh / day
road_km             km
price_inr_per_kwh   INR / kWh
revenue_inr_d       INR / day
kwh_d               kWh / day

Products recognised
-------------------
"electricity"   net electrical output (e_net_kwh_d, must be > 0)
"heat"          surplus thermal output (heat_surplus_kwh_d or product_energy)
"biogas"        raw biogas volume expressed as energy (ch4_nm3_d * LHV_CH4)

Allocation upper bounds (stated in match_supply docstring)
----------------------------------------------------------
Delivery of matched kWh depends on timing, grid access, and logistics.
The match_supply function computes an upper bound only.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from typing import Any, Dict, FrozenSet, List, Tuple

# Valid product labels
_VALID_PRODUCTS: FrozenSet[str] = frozenset({"electricity", "heat", "biogas"})

# Valid customer classes
_VALID_CLASSES: FrozenSet[str] = frozenset({"home", "industry"})


# ---------------------------------------------------------------------------
# DemandSink
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DemandSink:
    """A single demand-side customer for pathway energy products.

    Parameters
    ----------
    name:
        Human-readable identifier.  Must not be empty.
    customer_class:
        ``"home"`` or ``"industry"``.
    accepts:
        Tuple of product labels the sink can receive.  Each element must be
        one of ``"electricity"``, ``"heat"``, ``"biogas"``.
        Home sinks (``customer_class == "home"``) may only accept
        ``"electricity"`` and/or ``"heat"``; biogas is not permitted.
    demand_kwh_d:
        Daily energy demand [kWh/day].  Must be >= 0.
    road_km:
        Distance to this sink [km].  Must be >= 0.
    price_inr_per_kwh:
        Selling price offered by this sink [INR/kWh].  Must be >= 0.
    max_km:
        Maximum delivery distance [km] the sink will accept.  Must be >= 0.
        A sink is only eligible when ``road_km <= max_km``.
    """

    name: str
    customer_class: str
    accepts: Tuple[str, ...]
    demand_kwh_d: float
    road_km: float
    price_inr_per_kwh: float
    max_km: float

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("DemandSink.name must not be empty.")

        if self.customer_class not in _VALID_CLASSES:
            raise ValueError(
                f"DemandSink.customer_class must be one of {sorted(_VALID_CLASSES)}; "
                f"got '{self.customer_class}'."
            )

        for prod in self.accepts:
            if prod not in _VALID_PRODUCTS:
                raise ValueError(
                    f"DemandSink.accepts contains unknown product '{prod}'. "
                    f"Must be one of {sorted(_VALID_PRODUCTS)}."
                )

        if self.customer_class == "home" and "biogas" in self.accepts:
            raise ValueError(
                "Home sinks (customer_class='home') may not accept 'biogas'."
            )

        if self.demand_kwh_d < 0:
            raise ValueError(
                f"DemandSink.demand_kwh_d must be >= 0; got {self.demand_kwh_d}."
            )
        if self.road_km < 0:
            raise ValueError(
                f"DemandSink.road_km must be >= 0; got {self.road_km}."
            )
        if self.price_inr_per_kwh < 0:
            raise ValueError(
                f"DemandSink.price_inr_per_kwh must be >= 0; "
                f"got {self.price_inr_per_kwh}."
            )
        if self.max_km < 0:
            raise ValueError(
                f"DemandSink.max_km must be >= 0; got {self.max_km}."
            )


# ---------------------------------------------------------------------------
# home_sink helper
# ---------------------------------------------------------------------------

def home_sink(
    households: int,
    kwh_per_household_d: float,
    road_km: float,
    price_inr_per_kwh: float,
    max_km: float,
    name: str = "residential",
    accepts: Tuple[str, ...] = ("electricity",),
) -> DemandSink:
    """Construct a home :class:`DemandSink` for a cluster of households.

    The daily demand is ``households * kwh_per_household_d``.  The kWh per
    household is an INPUT; there is no built-in default because consumption
    varies enormously by region and season.

    Parameters
    ----------
    households:
        Number of households.  Must be >= 0.
    kwh_per_household_d:
        Daily electricity consumption per household [kWh/day].  Must be >= 0.
    road_km:
        Distance to the cluster [km].  Must be >= 0.
    price_inr_per_kwh:
        Selling price [INR/kWh].  Must be >= 0.
    max_km:
        Maximum delivery distance [km].  Must be >= 0.
    name:
        Human-readable label.  Default ``"residential"``.
    accepts:
        Products to accept.  Must not include ``"biogas"``.
        Default ``("electricity",)``.

    Returns
    -------
    DemandSink
        A frozen home sink with ``demand_kwh_d = households * kwh_per_household_d``.

    Raises
    ------
    ValueError
        If ``households < 0``, ``kwh_per_household_d < 0``, or ``"biogas"``
        is in ``accepts``.
    """
    if households < 0:
        raise ValueError(f"households must be >= 0; got {households}.")
    if kwh_per_household_d < 0:
        raise ValueError(
            f"kwh_per_household_d must be >= 0; got {kwh_per_household_d}."
        )

    demand = float(households) * kwh_per_household_d

    return DemandSink(
        name=name,
        customer_class="home",
        accepts=accepts,
        demand_kwh_d=demand,
        road_km=road_km,
        price_inr_per_kwh=price_inr_per_kwh,
        max_km=max_km,
    )


# ---------------------------------------------------------------------------
# match_supply
# ---------------------------------------------------------------------------

def match_supply(
    products: Dict[str, float],
    sinks: List[DemandSink],
) -> Dict[str, Any]:
    """Greedily allocate product supply to demand sinks by descending price.

    Allocation upper bounds
    -----------------------
    The returned ``matched_kwh_d`` and per-allocation ``kwh_d`` values are
    upper bounds.  Actual delivery depends on timing, grid access, and
    logistics and may be lower.

    Algorithm
    ---------
    For each product, sinks are ranked by ``price_inr_per_kwh`` (descending).
    Each sink is eligible only when:
      - the product name is in ``sink.accepts``,
      - ``sink.road_km <= sink.max_km``, and
      - ``sink.demand_kwh_d > 0``.
    Allocation to each sink = ``min(remaining_supply, remaining_demand)``.

    Parameters
    ----------
    products:
        Dict mapping product name to available supply [kWh/day].  Negative
        values are treated as zero (no supply).  Unknown product names are
        accepted and included in ``unmatched_kwh_d``.
    sinks:
        List of :class:`DemandSink` instances.

    Returns
    -------
    dict
        ``allocations`` list[dict]:
            Each entry has keys ``sink`` (str, sink name),
            ``product`` (str), ``kwh_d`` (float), ``revenue_inr_d`` (float).
        ``unmatched_kwh_d`` dict[str, float]:
            Remaining unallocated supply per product [kWh/day].
        ``matched_kwh_d`` float:
            Total kWh/day successfully matched across all products.
    """
    # Clamp negative supply to zero
    remaining: Dict[str, float] = {
        prod: max(0.0, float(v)) for prod, v in products.items()
    }

    # Remaining demand per sink (mutable copy; keyed by sink object identity)
    remaining_demand: Dict[int, float] = {
        id(s): s.demand_kwh_d for s in sinks
    }

    # Sort sinks once by descending price for the greedy pass
    sinks_by_price = sorted(sinks, key=lambda s: s.price_inr_per_kwh, reverse=True)

    allocations: List[Dict[str, Any]] = []
    total_matched: float = 0.0

    for product in remaining:
        for sink in sinks_by_price:
            # Hard filters
            if product not in sink.accepts:
                continue
            if sink.road_km > sink.max_km:
                continue
            rem_demand = remaining_demand[id(sink)]
            if rem_demand <= 0.0:
                continue
            if remaining[product] <= 0.0:
                break  # no supply left for this product

            # Allocate
            alloc = min(remaining[product], rem_demand)
            remaining[product] -= alloc
            remaining_demand[id(sink)] -= alloc
            total_matched += alloc

            allocations.append({
                "sink": sink.name,
                "product": product,
                "kwh_d": float(alloc),
                "revenue_inr_d": float(alloc * sink.price_inr_per_kwh),
            })

    unmatched: Dict[str, float] = {
        prod: float(remaining[prod]) for prod in remaining
    }

    return {
        "allocations": allocations,
        "unmatched_kwh_d": unmatched,
        "matched_kwh_d": float(total_matched),
    }
