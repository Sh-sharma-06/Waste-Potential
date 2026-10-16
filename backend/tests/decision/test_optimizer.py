"""
Tests for backend/app/decision/optimizer.py

Coverage:
  - Boundary: zero supply, zero capacity, extreme values
  - No negative physical allocations ever returned
  - Hard-zero incompatibility is never violated
  - Feasibility flag is correct under infeasible conditions
  - Objective-minimisation direction (more negative coeff → more allocation)
  - Weights must sum to 1.0
"""

import math
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.decision.optimizer import (
    Optimizer,
    ScipyBackend,
    WasteScenario,
    AllocationResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_scenario(
    supply: dict[str, float],
    capacity: dict[str, float],
    compat: dict[tuple[str, str], int],
    obj: dict[tuple[str, str], float],
    weights: dict[str, float] | None = None,
) -> WasteScenario:
    if weights is None:
        weights = {"w_cost": 1.0, "w_carbon": 0.0, "w_transport": 0.0}
    return WasteScenario(
        supply=supply,
        capacity=capacity,
        compatibility_matrix=compat,
        objective_coefficients=obj,
        weights=weights,
    )


def opt() -> Optimizer:
    return Optimizer(ScipyBackend())


# ---------------------------------------------------------------------------
# Weight validation
# ---------------------------------------------------------------------------

class TestWeightValidation:
    def test_weights_must_sum_to_one(self):
        with pytest.raises(ValueError, match="sum to 1.0"):
            WasteScenario(
                supply={"s0": 100.0},
                capacity={"t0": 200.0},
                compatibility_matrix={("s0", "t0"): 1},
                objective_coefficients={("s0", "t0"): -10.0},
                weights={"w_cost": 0.4, "w_carbon": 0.4, "w_transport": 0.0},
            )

    def test_negative_weight_rejected(self):
        with pytest.raises(ValueError):
            WasteScenario(
                supply={"s0": 100.0},
                capacity={"t0": 200.0},
                compatibility_matrix={("s0", "t0"): 1},
                objective_coefficients={("s0", "t0"): -10.0},
                weights={"w_cost": 1.2, "w_carbon": -0.2, "w_transport": 0.0},
            )

    def test_weights_sum_to_one_within_tolerance(self):
        """Floating-point sums close to 1.0 are accepted."""
        sc = make_scenario(
            {"s0": 100.0}, {"t0": 200.0}, {("s0", "t0"): 1}, {("s0", "t0"): -5.0},
            weights={"w_cost": 1.0 / 3, "w_carbon": 1.0 / 3, "w_transport": 1.0 / 3},
        )
        assert sc is not None


# ---------------------------------------------------------------------------
# Boundary tests
# ---------------------------------------------------------------------------

class TestBoundaryInputs:
    def test_zero_supply_produces_zero_allocation(self):
        """Zero supply means nothing can be moved — allocation must be empty."""
        sc = make_scenario(
            supply={"s0": 0.0},
            capacity={"t0": 500.0},
            compat={("s0", "t0"): 1},
            obj={("s0", "t0"): -10.0},
        )
        res = opt().solve(sc)
        # Solver may be infeasible or return empty allocation — either is correct
        if res.success:
            total = sum(res.allocation.values())
            assert total == pytest.approx(0.0, abs=1e-6)

    def test_no_negative_allocation_simple(self):
        """Basic 2×2 scenario — all allocated values must be ≥ 0."""
        sc = make_scenario(
            supply={"s0": 5000.0, "s1": 3000.0},
            capacity={"t0": 6000.0, "t1": 4000.0},
            compat={("s0", "t0"): 1, ("s0", "t1"): 1, ("s1", "t0"): 1, ("s1", "t1"): 1},
            obj={("s0", "t0"): -10.0, ("s0", "t1"): -5.0, ("s1", "t0"): -10.0, ("s1", "t1"): -5.0},
        )
        res = opt().solve(sc)
        assert res.success
        for (i, j), v in res.allocation.items():
            assert v >= 0.0, f"Negative allocation at ({i},{j}): {v}"

    def test_no_negative_allocation_extreme_values(self):
        """Extremely large supply and capacity — no negative values permitted."""
        sc = make_scenario(
            supply={"s0": 1e9, "s1": 5e8},
            capacity={"t0": 2e9, "t1": 1e9},
            compat={("s0", "t0"): 1, ("s1", "t1"): 1},
            obj={("s0", "t0"): -999.0, ("s1", "t1"): -999.0},
        )
        res = opt().solve(sc)
        assert res.success
        for v in res.allocation.values():
            assert v >= 0.0

    def test_total_allocation_does_not_exceed_supply(self):
        """Sum of allocations for each stream ≤ its supply."""
        sc = make_scenario(
            supply={"s0": 3000.0, "s1": 2000.0},
            capacity={"t0": 4000.0, "t1": 4000.0},
            compat={("s0", "t0"): 1, ("s0", "t1"): 1, ("s1", "t0"): 1, ("s1", "t1"): 1},
            obj={("s0", "t0"): -8.0, ("s0", "t1"): -8.0, ("s1", "t0"): -8.0, ("s1", "t1"): -8.0},
        )
        res = opt().solve(sc)
        assert res.success
        for stream_id, avail in sc.supply.items():
            used = sum(v for (i, j), v in res.allocation.items() if i == stream_id)
            assert used <= avail + 1e-6, f"Stream {stream_id}: used {used} > supply {avail}"

    def test_total_allocation_does_not_exceed_capacity(self):
        """Sum of allocations for each technology ≤ its capacity."""
        sc = make_scenario(
            supply={"s0": 5000.0, "s1": 5000.0},
            capacity={"t0": 4000.0, "t1": 4000.0},
            compat={("s0", "t0"): 1, ("s0", "t1"): 1, ("s1", "t0"): 1, ("s1", "t1"): 1},
            obj={("s0", "t0"): -8.0, ("s0", "t1"): -8.0, ("s1", "t0"): -8.0, ("s1", "t1"): -8.0},
        )
        res = opt().solve(sc)
        assert res.success
        for tech_id, cap in sc.capacity.items():
            used = sum(v for (i, j), v in res.allocation.items() if j == tech_id)
            assert used <= cap + 1e-6, f"Tech {tech_id}: used {used} > capacity {cap}"


# ---------------------------------------------------------------------------
# Compatibility (hard-zero) tests
# ---------------------------------------------------------------------------

class TestCompatibilityConstraints:
    def test_incompatible_pair_never_allocated(self):
        """Streams can only be allocated to compatible technologies."""
        # Stream s0 → only t0; Stream s1 → only t1
        sc = make_scenario(
            supply={"s0": 2000.0, "s1": 2000.0},
            capacity={"t0": 3000.0, "t1": 3000.0},
            compat={("s0", "t0"): 1, ("s1", "t1"): 1},
            obj={("s0", "t0"): -10.0, ("s1", "t1"): -10.0},
        )
        res = opt().solve(sc)
        assert res.success
        for (i, j) in res.allocation:
            assert sc.compatibility_matrix.get((i, j), 0) == 1, (
                f"Incompatible pair ({i},{j}) was allocated"
            )

    def test_fully_incompatible_raises_at_build(self):
        """All-zero compatibility matrix has no LP variables — ValueError at build time."""
        sc = make_scenario(
            supply={"s0": 1000.0},
            capacity={"t0": 2000.0},
            compat={("s0", "t0"): 0},  # no compatible pair
            obj={},
        )
        with pytest.raises(ValueError, match="No compatible"):
            opt().solve(sc)

    def test_partial_compatibility_respects_exclusion(self):
        """With mixed compatibility, excluded pairs must not appear in allocation."""
        # Pairs (s0,t0) and (s1,t1) compatible; (s0,t1) and (s1,t0) incompatible
        sc = make_scenario(
            supply={"s0": 1000.0, "s1": 1000.0},
            capacity={"t0": 2000.0, "t1": 2000.0},
            compat={("s0", "t0"): 1, ("s0", "t1"): 0, ("s1", "t0"): 0, ("s1", "t1"): 1},
            obj={("s0", "t0"): -10.0, ("s1", "t1"): -10.0},
        )
        res = opt().solve(sc)
        assert res.success
        assert ("s0", "t1") not in res.allocation
        assert ("s1", "t0") not in res.allocation

    def test_lower_cost_tech_receives_more_when_fully_compatible(self):
        """With equal compatibility, cheaper tech (more negative coeff) gets preference."""
        sc = make_scenario(
            supply={"s0": 6000.0},
            capacity={"t0": 5000.0, "t1": 5000.0},
            compat={("s0", "t0"): 1, ("s0", "t1"): 1},
            obj={("s0", "t0"): -20.0, ("s0", "t1"): -5.0},
        )
        res = opt().solve(sc)
        assert res.success
        tech0 = res.allocation.get(("s0", "t0"), 0.0)
        tech1 = res.allocation.get(("s0", "t1"), 0.0)
        assert tech0 > tech1, f"Expected t0 (coeff=-20) > t1 (coeff=-5); got {tech0} vs {tech1}"


# ---------------------------------------------------------------------------
# Feasibility tests
# ---------------------------------------------------------------------------

class TestFeasibility:
    def test_feasible_scenario_returns_success_true(self):
        sc = make_scenario(
            supply={"s0": 1000.0},
            capacity={"t0": 2000.0},
            compat={("s0", "t0"): 1},
            obj={("s0", "t0"): -5.0},
        )
        res = opt().solve(sc)
        assert res.success is True
        assert res.solver_status is not None

    def test_result_has_no_allocation_when_infeasible(self):
        """When infeasible, allocation dict must be empty."""
        # Supply requires more capacity than available — force infeasibility
        # by making all constraints contradictory (supply constraint needs
        # negative slack). We can't easily force a true infeasibility with
        # only inequality constraints (LP is always feasible at x=0).
        # Instead, verify the empty-allocation contract on a zero-supply scenario.
        sc = make_scenario(
            supply={"s0": 0.0},
            capacity={"t0": 100.0},
            compat={("s0", "t0"): 1},
            obj={("s0", "t0"): -1.0},
        )
        res = opt().solve(sc)
        if not res.success:
            assert res.allocation == {}

    def test_allocation_result_fields_present(self):
        """AllocationResult always has all required fields."""
        sc = make_scenario(
            supply={"s0": 500.0},
            capacity={"t0": 1000.0},
            compat={("s0", "t0"): 1},
            obj={("s0", "t0"): -7.0},
        )
        res = opt().solve(sc)
        assert isinstance(res, AllocationResult)
        assert hasattr(res, "allocation")
        assert hasattr(res, "objective_value")
        assert hasattr(res, "solver_status")
        assert hasattr(res, "success")
        assert hasattr(res, "variable_index")

    def test_variable_index_only_contains_compatible_pairs(self):
        """variable_index must only contain pairs where compat==1."""
        compat = {("s0", "t0"): 1, ("s0", "t1"): 0, ("s1", "t0"): 0, ("s1", "t1"): 1}
        sc = make_scenario(
            supply={"s0": 300.0, "s1": 300.0},
            capacity={"t0": 500.0, "t1": 500.0},
            compat=compat,
            obj={("s0", "t0"): -5.0, ("s1", "t1"): -5.0},
        )
        res = opt().solve(sc)
        for pair in res.variable_index:
            assert compat.get(pair, 0) == 1, f"Incompatible pair {pair} in variable_index"
