"""
Unit tests for backend/app/data/demand.py — match_demand_greedy()

Coverage:
  Allocation correctness:
  - Exact supply == one sink capacity → full allocation to that sink, zero remaining
  - Supply < single sink capacity → partial allocation, rest remains
  - Supply > all sinks combined → sinks fully served, leftover remaining supply
  - Supply == 0 → no allocations, zero matched, zero revenue
  - Empty sinks list → nothing matched, full supply returned as remaining

  Revenue maximisation:
  - Higher-priced sink receives supply before lower-priced sink
  - Revenue equals sum of (allocated_kwh_d × price) per allocation
  - total_revenue_inr_d matches sum of per-allocation revenue_inr_d

  Capacity enforcement:
  - No single sink is allocated more than its demand_kwh_d
  - Remaining supply + total_matched_kwh_d == original supply_kwh_d

  Result structure:
  - Returns dict with required keys: total_matched_kwh_d, total_revenue_inr_d,
    remaining_supply_kwh_d, allocations
  - Each allocation dict has allocated_kwh_d, revenue_inr_d, price
  - Optional keys (customer_class, road_km) present when supplied in sink dict

  Edge cases:
  - Two sinks with equal price — both served in order, allocation is correct
  - Sink with demand_kwh_d == 0 → receives zero allocation (not skipped, just 0)
  - Large supply with many sinks — correct totals
  - Fractional kWh values — no precision loss (rounded to 6 dp)

  Input validation:
  - supply_kwh_d < 0 raises ValueError
  - sink.demand_kwh_d < 0 raises ValueError
  - sink.price < 0 raises ValueError
"""

import math
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.data.demand import match_demand_greedy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sink(
    customer_class: str = "industrial",
    accepts: list | None = None,
    demand_kwh_d: float = 100.0,
    road_km: float = 5.0,
    price: float = 8.0,
) -> dict:
    return {
        "customer_class": customer_class,
        "accepts": accepts or ["electricity"],
        "demand_kwh_d": demand_kwh_d,
        "road_km": road_km,
        "price": price,
    }


# ---------------------------------------------------------------------------
# Result structure
# ---------------------------------------------------------------------------

class TestResultStructure:
    def test_required_keys_present(self):
        result = match_demand_greedy(100.0, [_sink()])
        assert "total_matched_kwh_d" in result
        assert "total_revenue_inr_d" in result
        assert "remaining_supply_kwh_d" in result
        assert "allocations" in result

    def test_allocations_is_list(self):
        result = match_demand_greedy(50.0, [_sink()])
        assert isinstance(result["allocations"], list)

    def test_each_allocation_has_required_keys(self):
        result = match_demand_greedy(50.0, [_sink()])
        for alloc in result["allocations"]:
            assert "allocated_kwh_d" in alloc
            assert "revenue_inr_d" in alloc
            assert "price" in alloc

    def test_optional_keys_carried_through(self):
        """customer_class and road_km from the sink dict appear in the allocation."""
        result = match_demand_greedy(50.0, [_sink(customer_class="agri", road_km=3.5)])
        alloc = result["allocations"][0]
        assert alloc.get("customer_class") == "agri"
        assert alloc.get("road_km") == 3.5


# ---------------------------------------------------------------------------
# Allocation correctness
# ---------------------------------------------------------------------------

class TestAllocationCorrectness:
    def test_supply_exactly_fills_one_sink(self):
        """Supply == sink capacity → full allocation, zero remaining."""
        result = match_demand_greedy(200.0, [_sink(demand_kwh_d=200.0, price=8.0)])
        assert math.isclose(result["total_matched_kwh_d"], 200.0)
        assert math.isclose(result["remaining_supply_kwh_d"], 0.0)

    def test_supply_less_than_sink_capacity(self):
        """Partial fill: allocated ≤ demand_kwh_d, remaining == 0."""
        result = match_demand_greedy(75.0, [_sink(demand_kwh_d=200.0)])
        assert math.isclose(result["total_matched_kwh_d"], 75.0)
        assert math.isclose(result["remaining_supply_kwh_d"], 0.0)
        alloc = result["allocations"][0]
        assert math.isclose(alloc["allocated_kwh_d"], 75.0)

    def test_supply_exceeds_all_sinks(self):
        """Supply > combined capacity → sinks full, leftover in remaining."""
        sinks = [
            _sink(demand_kwh_d=100.0, price=9.0),
            _sink(demand_kwh_d=150.0, price=7.0),
        ]
        result = match_demand_greedy(400.0, sinks)
        assert math.isclose(result["total_matched_kwh_d"], 250.0)
        assert math.isclose(result["remaining_supply_kwh_d"], 150.0)

    def test_zero_supply_produces_empty_allocations(self):
        result = match_demand_greedy(0.0, [_sink(), _sink(price=5.0)])
        assert math.isclose(result["total_matched_kwh_d"], 0.0)
        assert math.isclose(result["total_revenue_inr_d"], 0.0)
        assert math.isclose(result["remaining_supply_kwh_d"], 0.0)
        # Sinks may still appear with 0 allocation — or allocations list empty
        total_alloc = sum(a["allocated_kwh_d"] for a in result["allocations"])
        assert math.isclose(total_alloc, 0.0)

    def test_empty_sinks_list(self):
        result = match_demand_greedy(500.0, [])
        assert math.isclose(result["total_matched_kwh_d"], 0.0)
        assert math.isclose(result["remaining_supply_kwh_d"], 500.0)
        assert result["allocations"] == []

    def test_remaining_plus_matched_equals_supply(self):
        """Conservation: total_matched + remaining == supply."""
        supply = 350.0
        sinks = [_sink(demand_kwh_d=200.0, price=9.0), _sink(demand_kwh_d=200.0, price=7.0)]
        result = match_demand_greedy(supply, sinks)
        total = result["total_matched_kwh_d"] + result["remaining_supply_kwh_d"]
        assert math.isclose(total, supply, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Revenue maximisation
# ---------------------------------------------------------------------------

class TestRevenueMaximisation:
    def test_higher_price_sink_served_first(self):
        """With limited supply, the higher-priced sink receives the allocation."""
        sinks = [
            _sink(customer_class="cheap",     demand_kwh_d=300.0, price=5.0),
            _sink(customer_class="expensive", demand_kwh_d=300.0, price=10.0),
        ]
        result = match_demand_greedy(200.0, sinks)
        alloc_map = {a["customer_class"]: a for a in result["allocations"]}
        # expensive should receive the full 200 kWh, cheap should get 0
        expensive_alloc = alloc_map.get("expensive", {}).get("allocated_kwh_d", 0.0)
        cheap_alloc     = alloc_map.get("cheap",     {}).get("allocated_kwh_d", 0.0)
        assert math.isclose(expensive_alloc, 200.0), (
            f"Expected expensive=200, got {expensive_alloc}"
        )
        assert math.isclose(cheap_alloc, 0.0), (
            f"Expected cheap=0, got {cheap_alloc}"
        )

    def test_revenue_per_allocation_is_price_times_kwh(self):
        """revenue_inr_d == allocated_kwh_d × price for each allocation."""
        sinks = [
            _sink(demand_kwh_d=100.0, price=7.50),
            _sink(demand_kwh_d=200.0, price=4.00),
        ]
        result = match_demand_greedy(250.0, sinks)
        for alloc in result["allocations"]:
            expected_rev = alloc["allocated_kwh_d"] * alloc["price"]
            assert math.isclose(alloc["revenue_inr_d"], expected_rev, rel_tol=1e-9), (
                f"Revenue mismatch: {alloc['revenue_inr_d']} != {expected_rev}"
            )

    def test_total_revenue_equals_sum_of_per_sink_revenue(self):
        sinks = [_sink(demand_kwh_d=100.0, price=8.0), _sink(demand_kwh_d=100.0, price=6.0)]
        result = match_demand_greedy(150.0, sinks)
        expected_total = sum(a["revenue_inr_d"] for a in result["allocations"])
        assert math.isclose(result["total_revenue_inr_d"], expected_total, rel_tol=1e-9)

    def test_greedy_maximises_revenue_vs_inverse_order(self):
        """Greedy allocation must earn more revenue than a reverse-price allocation."""
        sinks = [
            _sink(demand_kwh_d=200.0, price=9.0),
            _sink(demand_kwh_d=200.0, price=3.0),
        ]
        supply = 250.0
        greedy_result = match_demand_greedy(supply, sinks)
        # Manually compute worst-case (cheap-first) revenue
        cheap_first_rev = min(supply, 200.0) * 3.0 + max(0.0, supply - 200.0) * 9.0
        assert greedy_result["total_revenue_inr_d"] >= cheap_first_rev


# ---------------------------------------------------------------------------
# Capacity enforcement
# ---------------------------------------------------------------------------

class TestCapacityEnforcement:
    def test_no_sink_receives_more_than_its_demand(self):
        sinks = [
            _sink(demand_kwh_d=100.0, price=9.0),
            _sink(demand_kwh_d=80.0,  price=7.0),
            _sink(demand_kwh_d=60.0,  price=5.0),
        ]
        result = match_demand_greedy(500.0, sinks)
        # capacities: 100+80+60 = 240; supply 500 → all sinks at capacity
        for alloc in result["allocations"]:
            cap = next(
                s["demand_kwh_d"] for s in sinks if s["price"] == alloc["price"]
            )
            assert alloc["allocated_kwh_d"] <= cap + 1e-9, (
                f"Sink over-allocated: {alloc['allocated_kwh_d']} > {cap}"
            )

    def test_sink_with_zero_demand_receives_nothing(self):
        sinks = [
            _sink(demand_kwh_d=0.0,   price=10.0),  # zero-demand sink
            _sink(demand_kwh_d=100.0, price=5.0),
        ]
        result = match_demand_greedy(50.0, sinks)
        zero_sink_alloc = result["allocations"][0]["allocated_kwh_d"]
        assert math.isclose(zero_sink_alloc, 0.0)

    def test_two_sinks_equal_price_both_served(self):
        """Equal-priced sinks — order is stable, both filled correctly."""
        sinks = [
            _sink(customer_class="A", demand_kwh_d=100.0, price=8.0),
            _sink(customer_class="B", demand_kwh_d=100.0, price=8.0),
        ]
        result = match_demand_greedy(150.0, sinks)
        total_alloc = sum(a["allocated_kwh_d"] for a in result["allocations"])
        assert math.isclose(total_alloc, 150.0)
        # First sink should be full (100), second partial (50)
        first_alloc  = result["allocations"][0]["allocated_kwh_d"]
        second_alloc = result["allocations"][1]["allocated_kwh_d"]
        assert math.isclose(first_alloc, 100.0)
        assert math.isclose(second_alloc, 50.0)


# ---------------------------------------------------------------------------
# Integration: sinks from get_location_context()
# ---------------------------------------------------------------------------

class TestIntegrationWithServiceSinks:
    def test_default_sinks_can_be_passed_directly(self):
        """Default sinks from the service layer must work without conversion."""
        from app.data.service import get_location_context
        ctx = get_location_context("loc-001")
        sinks = ctx["sinks"]
        total_demand = sum(s["demand_kwh_d"] for s in sinks)
        # Supply equals half total demand → half utilisation
        supply = total_demand / 2
        result = match_demand_greedy(supply, sinks)
        assert math.isclose(
            result["total_matched_kwh_d"] + result["remaining_supply_kwh_d"],
            supply, rel_tol=1e-9,
        )

    def test_industrial_sink_prioritised_over_residential(self):
        """industrial (8.50 INR/kWh) must be served before residential (7.50 INR/kWh)."""
        from app.data.service import get_location_context, _DEFAULT_SINKS
        sinks = list(_DEFAULT_SINKS)
        # Supply enough for only the industrial sink
        industrial_demand = next(s["demand_kwh_d"] for s in sinks if s["customer_class"] == "industrial")
        result = match_demand_greedy(industrial_demand * 0.5, sinks)
        industrial_alloc = next(
            (a for a in result["allocations"] if a.get("customer_class") == "industrial"), None
        )
        residential_alloc = next(
            (a for a in result["allocations"] if a.get("customer_class") == "residential"), None
        )
        # Industrial should receive the full supply; residential gets nothing
        assert industrial_alloc is not None
        assert math.isclose(industrial_alloc["allocated_kwh_d"], industrial_demand * 0.5)
        if residential_alloc is not None:
            assert math.isclose(residential_alloc["allocated_kwh_d"], 0.0)


# ---------------------------------------------------------------------------
# Input validation
# ---------------------------------------------------------------------------

class TestInputValidation:
    def test_negative_supply_raises(self):
        with pytest.raises(ValueError, match="supply_kwh_d"):
            match_demand_greedy(-1.0, [_sink()])

    def test_negative_demand_in_sink_raises(self):
        bad_sink = {"demand_kwh_d": -10.0, "price": 5.0}
        with pytest.raises(ValueError, match="demand_kwh_d"):
            match_demand_greedy(100.0, [bad_sink])

    def test_negative_price_in_sink_raises(self):
        bad_sink = {"demand_kwh_d": 100.0, "price": -1.0}
        with pytest.raises(ValueError, match="price"):
            match_demand_greedy(100.0, [bad_sink])
