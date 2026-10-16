"""
Multi-objective scoring for the Waste-Potential decision module.

Algorithm:
  1. Accept a list of feasible AllocationScenarioMetrics (one per scenario).
  2. Apply Min-Max normalisation across all scenarios for each of the three
     core metrics (cost, carbon, transport_distance) so that each normalised
     value is in [0.0, 1.0], where 0.0 = best (lowest) and 1.0 = worst (highest).
  3. Compute a weighted composite score per scenario:
       score = (w_cost * norm_cost) + (w_carbon * norm_carbon)
               + (w_transport * norm_transport)
     where the weights are operator-supplied and must sum to 1.0.

The normalised metrics and composite score are attached to a ScoredScenario
result and passed downstream to pareto.py for Pareto filtering.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional


# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------

@dataclass
class ObjectiveWeights:
    """Operator-supplied normalised weights for the three objectives.

    Constraints enforced at construction:
      - All weights ≥ 0.0
      - w_cost + w_carbon + w_transport == 1.0  (within 1e-6 tolerance)
    """
    w_cost: float
    w_carbon: float
    w_transport: float

    def __post_init__(self) -> None:
        if self.w_cost < 0 or self.w_carbon < 0 or self.w_transport < 0:
            raise ValueError(
                f"All objective weights must be ≥ 0. "
                f"Got w_cost={self.w_cost}, w_carbon={self.w_carbon}, "
                f"w_transport={self.w_transport}."
            )
        total = self.w_cost + self.w_carbon + self.w_transport
        if not math.isclose(total, 1.0, abs_tol=1e-6):
            raise ValueError(
                f"Objective weights must sum to 1.0, got {total:.8f}. "
                f"w_cost={self.w_cost}, w_carbon={self.w_carbon}, "
                f"w_transport={self.w_transport}."
            )


@dataclass
class AllocationScenarioMetrics:
    """Raw (un-normalised) performance metrics for a single feasible scenario.

    Attributes
    ----------
    scenario_id:
        Unique identifier for the scenario (e.g. a weight-vector label or UUID).
    total_cost:
        Total annualised cost across all allocations (£/year or $/year).
        Lower is better.
    total_carbon:
        Net GHG delta (kgCO2e/year). Negative means emission reduction.
        Lower (more negative) is better.
    total_transport_distance:
        Total tonne-km of road transport across all allocations.
        Lower is better.
    allocation:
        The underlying allocation dict {(stream_id, tech_id): tonnes/yr}
        carried through for downstream use. Optional — set to None if not
        needed at the scoring stage.
    """
    scenario_id: str
    total_cost: float
    total_carbon: float
    total_transport_distance: float
    allocation: Optional[dict[tuple[int, int], float]] = None


@dataclass
class ScoredScenario:
    """A scenario with normalised metrics and a composite weighted score.

    Attributes
    ----------
    scenario_id:
        Copied from AllocationScenarioMetrics.
    raw:
        The original un-normalised metrics.
    norm_cost:
        Min-Max normalised cost in [0.0, 1.0].
    norm_carbon:
        Min-Max normalised carbon in [0.0, 1.0].
    norm_transport:
        Min-Max normalised transport distance in [0.0, 1.0].
    composite_score:
        Weighted composite: w_cost*norm_cost + w_carbon*norm_carbon
        + w_transport*norm_transport. Range [0.0, 1.0]. Lower is better.
    """
    scenario_id: str
    raw: AllocationScenarioMetrics
    norm_cost: float
    norm_carbon: float
    norm_transport: float
    composite_score: float


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------

class MultiObjectiveScorer:
    """Applies Min-Max normalisation and weighted composite scoring across a
    population of feasible allocation scenarios.

    Usage
    -----
    >>> scorer = MultiObjectiveScorer()
    >>> scored = scorer.score(scenarios, weights)
    """

    @staticmethod
    def _minmax_normalise(values: list[float]) -> list[float]:
        """Normalise a list of values to [0.0, 1.0] using Min-Max scaling.

        When all values are identical (range == 0) every normalised value is
        set to 0.0 — i.e. all scenarios are equally "best" on that metric.
        """
        if not values:
            return []
        lo = min(values)
        hi = max(values)
        span = hi - lo
        if span == 0.0:
            return [0.0] * len(values)
        return [(v - lo) / span for v in values]

    def score(
        self,
        scenarios: list[AllocationScenarioMetrics],
        weights: ObjectiveWeights,
    ) -> list[ScoredScenario]:
        """Score a list of scenarios.

        Parameters
        ----------
        scenarios:
            List of feasible AllocationScenarioMetrics. Must be non-empty.
        weights:
            Operator-supplied objective weights. Must sum to 1.0.

        Returns
        -------
        List of ScoredScenario in the same order as *scenarios*, each
        decorated with normalised metrics and a composite score.

        Raises
        ------
        ValueError
            If *scenarios* is empty.
        """
        if not scenarios:
            raise ValueError("scenarios list must not be empty.")

        raw_costs = [s.total_cost for s in scenarios]
        raw_carbons = [s.total_carbon for s in scenarios]
        raw_transports = [s.total_transport_distance for s in scenarios]

        norm_costs = self._minmax_normalise(raw_costs)
        norm_carbons = self._minmax_normalise(raw_carbons)
        norm_transports = self._minmax_normalise(raw_transports)

        result: list[ScoredScenario] = []
        for i, s in enumerate(scenarios):
            nc = norm_costs[i]
            ncarb = norm_carbons[i]
            nt = norm_transports[i]
            composite = (
                weights.w_cost * nc
                + weights.w_carbon * ncarb
                + weights.w_transport * nt
            )
            result.append(ScoredScenario(
                scenario_id=s.scenario_id,
                raw=s,
                norm_cost=nc,
                norm_carbon=ncarb,
                norm_transport=nt,
                composite_score=composite,
            ))

        return result
