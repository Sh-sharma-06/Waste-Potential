"""
Greedy demand matcher for energy supply allocation.

Allocates a daily supply of energy (kWh/day) to a prioritised list of demand
sinks, maximising revenue by serving the highest-priced sinks first.

Design decisions
----------------
- Greedy allocation: sort sinks by descending price, fill each up to its
  demand_kwh_d cap, continue until supply is exhausted or all sinks are served.
- Pure synchronous function — no network I/O, no side effects.
- Accepts plain Python dicts for sinks (matching the SinkEntry schema shape)
  so this module has no hard Pydantic dependency and can be called by the
  service layer, router, or tests without instantiating schema objects.
- Numerical precision: all intermediate sums use standard float arithmetic.
  Values returned are rounded to 6 dp to avoid trailing noise.

Terminology
-----------
supply_kwh_d    : total energy available per day (kWh/day)
demand_kwh_d    : maximum absorption capacity of a single sink (kWh/day)
allocated_kwh_d : portion of supply assigned to one sink in this run
revenue         : allocated_kwh_d × sink.price (INR/day)
"""

from __future__ import annotations


def match_demand_greedy(
    supply_kwh_d: float,
    sinks: list[dict],
) -> dict:
    """Allocate *supply_kwh_d* to *sinks* greedily by descending price.

    Parameters
    ----------
    supply_kwh_d:
        Total energy supply available per day (kWh/day).  Must be ≥ 0.
    sinks:
        List of sink dicts.  Each must contain:
          - ``demand_kwh_d`` (float ≥ 0) — maximum absorption capacity.
          - ``price``        (float ≥ 0) — INR per kWh.
        Optional keys carried through unchanged to the allocation list:
          - ``customer_class`` (str)
          - ``accepts``        (list[str])
          - ``road_km``        (float)
        Missing optional keys are omitted from the allocation output.

    Returns
    -------
    dict with keys:
        ``total_matched_kwh_d``  (float) — total kWh/day successfully matched.
        ``total_revenue_inr_d``  (float) — total daily revenue in INR.
        ``remaining_supply_kwh_d`` (float) — unallocated supply after matching.
        ``allocations``          (list[dict]) — per-sink allocation details.
            Each entry has:
              ``customer_class`` (str, if provided in sink)
              ``allocated_kwh_d`` (float)
              ``revenue_inr_d``   (float)
              ``price``           (float)
              ``road_km``         (float, if provided in sink)

    Raises
    ------
    ValueError
        If ``supply_kwh_d`` < 0, or if any sink has a negative
        ``demand_kwh_d`` or ``price``.

    Examples
    --------
    >>> sinks = [
    ...     {"customer_class": "industrial", "accepts": ["heat"],
    ...      "demand_kwh_d": 500.0, "road_km": 5.0, "price": 8.50},
    ...     {"customer_class": "residential", "accepts": ["electricity"],
    ...      "demand_kwh_d": 300.0, "road_km": 2.0, "price": 7.50},
    ... ]
    >>> result = match_demand_greedy(600.0, sinks)
    >>> result["total_matched_kwh_d"]
    600.0
    >>> result["remaining_supply_kwh_d"]
    0.0
    """
    if supply_kwh_d < 0:
        raise ValueError(f"supply_kwh_d must be ≥ 0, got {supply_kwh_d}")

    for idx, s in enumerate(sinks):
        if s.get("demand_kwh_d", 0.0) < 0:
            raise ValueError(
                f"sinks[{idx}].demand_kwh_d must be ≥ 0, "
                f"got {s['demand_kwh_d']}"
            )
        if s.get("price", 0.0) < 0:
            raise ValueError(
                f"sinks[{idx}].price must be ≥ 0, got {s['price']}"
            )

    # Sort by descending price (revenue maximisation)
    ranked = sorted(sinks, key=lambda s: s.get("price", 0.0), reverse=True)

    remaining = supply_kwh_d
    total_matched = 0.0
    total_revenue = 0.0
    allocations: list[dict] = []

    for sink in ranked:
        if remaining <= 0.0:
            break

        cap = float(sink.get("demand_kwh_d", 0.0))
        price = float(sink.get("price", 0.0))

        allocated = min(remaining, cap)
        revenue = allocated * price

        remaining -= allocated
        total_matched += allocated
        total_revenue += revenue

        entry: dict = {
            "allocated_kwh_d": round(allocated, 6),
            "revenue_inr_d": round(revenue, 6),
            "price": price,
        }
        # Carry through optional descriptive fields when present
        for opt_key in ("customer_class", "road_km"):
            if opt_key in sink:
                entry[opt_key] = sink[opt_key]

        allocations.append(entry)

    return {
        "total_matched_kwh_d":    round(total_matched, 6),
        "total_revenue_inr_d":    round(total_revenue, 6),
        "remaining_supply_kwh_d": round(remaining, 6),
        "allocations":            allocations,
    }
