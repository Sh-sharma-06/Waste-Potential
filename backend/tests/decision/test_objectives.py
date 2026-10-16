"""
Tests for backend/app/decision/objectives.py and pareto.py

Coverage:
  MultiObjectiveScorer:
  - Min-Max normalisation: best value → 0.0, worst → 1.0
  - Min-Max normalisation: all-equal range → all 0.0
  - Composite score: correct weighted formula
  - Composite score: in [0.0, 1.0] for valid weights
  - Empty scenarios list → ValueError
  - ObjectiveWeights: rejects weights that don't sum to 1.0
  - ObjectiveWeights: rejects negative weights

  ParetoFilter:
  - _dominates: correct pairwise dominance logic
  - Dominated scenario is excluded from front
  - Non-dominated scenarios are retained
  - Pareto front sorted ascending by composite_score
  - Empty input → empty result
  - Single scenario → always on the Pareto front
  - All-identical scenarios → all on the Pareto front (no dominance)
"""

import math
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.decision.objectives import (
    AllocationScenarioMetrics,
    MultiObjectiveScorer,
    ObjectiveWeights,
    ScoredScenario,
)
from app.decision.pareto import ParetoFilter, ParetoResult, _dominates


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_metrics(
    sid: str,
    cost: float,
    carbon: float,
    transport: float,
) -> AllocationScenarioMetrics:
    return AllocationScenarioMetrics(
        scenario_id=sid,
        total_cost=cost,
        total_carbon=carbon,
        total_transport_distance=transport,
    )


def equal_weights() -> ObjectiveWeights:
    return ObjectiveWeights(w_cost=1 / 3, w_carbon=1 / 3, w_transport=1 / 3)


def cost_only_weights() -> ObjectiveWeights:
    return ObjectiveWeights(w_cost=1.0, w_carbon=0.0, w_transport=0.0)


@pytest.fixture
def scorer() -> MultiObjectiveScorer:
    return MultiObjectiveScorer()


@pytest.fixture
def pf() -> ParetoFilter:
    return ParetoFilter()


# ---------------------------------------------------------------------------
# ObjectiveWeights validation
# ---------------------------------------------------------------------------

class TestObjectiveWeights:
    def test_valid_equal_weights(self):
        w = ObjectiveWeights(1 / 3, 1 / 3, 1 / 3)
        assert w is not None

    def test_valid_single_objective(self):
        w = ObjectiveWeights(1.0, 0.0, 0.0)
        assert w is not None

    def test_weights_not_summing_to_one_raises(self):
        with pytest.raises(ValueError, match="sum to 1.0"):
            ObjectiveWeights(0.4, 0.4, 0.4)

    def test_negative_weight_raises(self):
        with pytest.raises(ValueError, match="≥ 0"):
            ObjectiveWeights(1.2, -0.2, 0.0)

    def test_all_zero_raises(self):
        with pytest.raises(ValueError, match="sum to 1.0"):
            ObjectiveWeights(0.0, 0.0, 0.0)


# ---------------------------------------------------------------------------
# Min-Max normalisation
# ---------------------------------------------------------------------------

class TestMinMaxNormalisation:
    def test_lowest_value_maps_to_zero(self, scorer):
        scenarios = [
            make_metrics("A", 100, -500, 200),
            make_metrics("B", 300, -100, 400),
            make_metrics("C", 200, -300, 300),
        ]
        w = cost_only_weights()
        scored = scorer.score(scenarios, w)
        # A has lowest cost → norm_cost == 0.0
        a = next(s for s in scored if s.scenario_id == "A")
        assert a.norm_cost == pytest.approx(0.0)

    def test_highest_value_maps_to_one(self, scorer):
        scenarios = [
            make_metrics("A", 100, -500, 200),
            make_metrics("B", 300, -100, 400),
        ]
        w = cost_only_weights()
        scored = scorer.score(scenarios, w)
        b = next(s for s in scored if s.scenario_id == "B")
        assert b.norm_cost == pytest.approx(1.0)

    def test_all_equal_values_map_to_zero(self, scorer):
        """When all values are identical, every norm is 0.0 (range == 0 case)."""
        scenarios = [make_metrics(str(i), 100.0, -200.0, 50.0) for i in range(4)]
        w = equal_weights()
        scored = scorer.score(scenarios, w)
        for s in scored:
            assert s.norm_cost == pytest.approx(0.0)
            assert s.norm_carbon == pytest.approx(0.0)
            assert s.norm_transport == pytest.approx(0.0)

    def test_normalised_values_in_zero_to_one(self, scorer):
        scenarios = [make_metrics(str(i), i * 10.0, -i * 50.0, i * 5.0) for i in range(1, 6)]
        w = equal_weights()
        scored = scorer.score(scenarios, w)
        for s in scored:
            assert 0.0 <= s.norm_cost <= 1.0
            assert 0.0 <= s.norm_carbon <= 1.0
            assert 0.0 <= s.norm_transport <= 1.0

    def test_midpoint_maps_correctly(self, scorer):
        """With three equally spaced values, the middle one should normalise to 0.5."""
        scenarios = [
            make_metrics("LO", 100.0, 0.0, 0.0),
            make_metrics("MID", 200.0, 0.0, 0.0),
            make_metrics("HI", 300.0, 0.0, 0.0),
        ]
        w = cost_only_weights()
        scored = scorer.score(scenarios, w)
        mid = next(s for s in scored if s.scenario_id == "MID")
        assert mid.norm_cost == pytest.approx(0.5, rel=1e-9)


# ---------------------------------------------------------------------------
# Composite score
# ---------------------------------------------------------------------------

class TestCompositeScore:
    def test_composite_score_formula(self, scorer):
        """Verify: score = w_cost·norm_cost + w_carbon·norm_carbon + w_transport·norm_transport."""
        scenarios = [
            make_metrics("A", 100.0, -500.0, 200.0),
            make_metrics("B", 200.0, -300.0, 100.0),
        ]
        w = ObjectiveWeights(0.5, 0.3, 0.2)
        scored = scorer.score(scenarios, w)
        for s in scored:
            expected = (
                w.w_cost * s.norm_cost
                + w.w_carbon * s.norm_carbon
                + w.w_transport * s.norm_transport
            )
            assert math.isclose(s.composite_score, expected, rel_tol=1e-9)

    def test_composite_score_in_zero_to_one(self, scorer):
        scenarios = [make_metrics(str(i), i * 7.0, -i * 30.0, i * 12.0) for i in range(1, 8)]
        w = equal_weights()
        scored = scorer.score(scenarios, w)
        for s in scored:
            assert 0.0 <= s.composite_score <= 1.0, (
                f"Composite score out of range: {s.composite_score}"
            )

    def test_best_scenario_has_lowest_composite_score(self, scorer):
        """Scenario with best (lowest) values on all objectives should have score ≈ 0."""
        scenarios = [
            make_metrics("BEST", 100.0, -500.0, 50.0),
            make_metrics("WORST", 500.0, -100.0, 400.0),
        ]
        w = equal_weights()
        scored = scorer.score(scenarios, w)
        best = next(s for s in scored if s.scenario_id == "BEST")
        worst = next(s for s in scored if s.scenario_id == "WORST")
        assert best.composite_score < worst.composite_score

    def test_empty_scenarios_raises(self, scorer):
        with pytest.raises(ValueError):
            scorer.score([], equal_weights())

    def test_single_scenario_score_is_zero(self, scorer):
        """Single scenario has range=0 on all metrics → all norms = 0 → score = 0."""
        scored = scorer.score([make_metrics("X", 999.0, -999.0, 999.0)], equal_weights())
        assert scored[0].composite_score == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Pareto dominance logic
# ---------------------------------------------------------------------------

class TestDominanceCheck:
    def test_strictly_better_all_three_dominates(self):
        a = make_metrics("A", 100, -500, 200)
        b = make_metrics("B", 200, -300, 400)
        assert _dominates(a, b)

    def test_reverse_does_not_dominate(self):
        a = make_metrics("A", 100, -500, 200)
        b = make_metrics("B", 200, -300, 400)
        assert not _dominates(b, a)

    def test_identical_does_not_dominate(self):
        a = make_metrics("A", 100, -200, 150)
        b = make_metrics("B", 100, -200, 150)
        assert not _dominates(a, b)
        assert not _dominates(b, a)

    def test_better_on_two_worse_on_one_does_not_dominate(self):
        """A is better on cost and carbon but worse on transport — no dominance."""
        a = make_metrics("A", 100, -500, 500)   # bad transport
        b = make_metrics("B", 200, -300, 100)   # bad cost and carbon
        assert not _dominates(a, b)
        assert not _dominates(b, a)

    def test_equal_on_two_better_on_one_dominates(self):
        """A equals B on cost and transport but is strictly better on carbon."""
        a = make_metrics("A", 100, -500, 200)
        b = make_metrics("B", 100, -300, 200)
        assert _dominates(a, b)
        assert not _dominates(b, a)


# ---------------------------------------------------------------------------
# Pareto filter
# ---------------------------------------------------------------------------

class TestParetoFilter:
    def test_dominated_scenario_excluded(self, scorer, pf):
        scenarios = [
            make_metrics("A", 100, -500, 200),   # dominates B
            make_metrics("B", 200, -300, 400),   # dominated by A
            make_metrics("C", 50, -200, 300),    # non-dominated (worse carbon)
        ]
        scored = scorer.score(scenarios, equal_weights())
        result = pf.filter(scored)
        front_ids = {s.scenario_id for s in result.pareto_front}
        dominated_ids = {s.scenario_id for s in result.dominated}
        assert "B" in dominated_ids, f"B should be dominated; front={front_ids}"
        assert "A" in front_ids
        assert "C" in front_ids

    def test_all_non_dominated_when_trade_offs_exist(self, scorer, pf):
        """Four scenarios with trade-offs — none dominates any other."""
        scenarios = [
            make_metrics("P1", 100, -100, 500),
            make_metrics("P2", 200, -300, 300),
            make_metrics("P3", 400, -500, 100),
            make_metrics("P4", 300, -200, 200),
        ]
        scored = scorer.score(scenarios, equal_weights())
        result = pf.filter(scored)
        assert result.n_pareto == 4
        assert result.dominated == []

    def test_pareto_front_sorted_by_composite_score(self, scorer, pf):
        scenarios = [
            make_metrics(str(i), i * 50.0, -i * 100.0, i * 30.0) for i in range(1, 6)
        ]
        scored = scorer.score(scenarios, equal_weights())
        result = pf.filter(scored)
        scores = [s.composite_score for s in result.pareto_front]
        assert scores == sorted(scores), "Pareto front must be sorted ascending by composite_score"

    def test_empty_input_returns_empty_result(self, pf):
        result = pf.filter([])
        assert result.n_total == 0
        assert result.n_pareto == 0
        assert result.pareto_front == []
        assert result.dominated == []

    def test_single_scenario_always_on_front(self, scorer, pf):
        scenarios = [make_metrics("ONLY", 100.0, -200.0, 50.0)]
        scored = scorer.score(scenarios, cost_only_weights())
        result = pf.filter(scored)
        assert result.n_pareto == 1
        assert result.pareto_front[0].scenario_id == "ONLY"

    def test_all_identical_are_all_non_dominated(self, scorer, pf):
        """Identical scenarios can't dominate each other — all are on the front."""
        scenarios = [make_metrics(str(i), 100.0, -200.0, 50.0) for i in range(5)]
        scored = scorer.score(scenarios, equal_weights())
        result = pf.filter(scored)
        assert result.n_pareto == 5
        assert result.dominated == []

    def test_n_pareto_plus_n_dominated_equals_n_total(self, scorer, pf):
        scenarios = [
            make_metrics("A", 100, -500, 200),
            make_metrics("B", 200, -300, 400),
            make_metrics("C", 150, -400, 300),
            make_metrics("D", 50, -200, 600),
        ]
        scored = scorer.score(scenarios, equal_weights())
        result = pf.filter(scored)
        assert result.n_pareto + len(result.dominated) == result.n_total
