"""
Pareto front filter for the Waste-Potential decision module.

Algorithm (strict Pareto dominance over three objectives):
  1. Compare every pair of ScoredScenario objects using their RAW metrics
     (cost, carbon, transport_distance) — not the normalised values, since
     dominance is a property of the original objective space.
  2. Scenario A dominates scenario B if and only if:
       - A is strictly better OR equal in ALL three metrics, AND
       - A is strictly better in AT LEAST ONE metric.
     "Better" means numerically lower (all three objectives are minimised).
  3. A scenario is "non-dominated" (Pareto-optimal) if no other scenario
     in the population dominates it.
  4. Return only the non-dominated set — the Pareto front.

The filter operates on ScoredScenario objects (output of objectives.py) so
that composite scores and normalised values are carried through to the result.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple

from .objectives import AllocationScenarioMetrics, ScoredScenario


# ---------------------------------------------------------------------------
# Dominance check
# ---------------------------------------------------------------------------

def _dominates(a: AllocationScenarioMetrics, b: AllocationScenarioMetrics) -> bool:
    """Return True iff scenario *a* dominates scenario *b*.

    A dominates B when:
      - a.total_cost          ≤ b.total_cost
      - a.total_carbon        ≤ b.total_carbon
      - a.total_transport     ≤ b.total_transport
      AND at least one of the above is strictly less than (<).

    All three objectives are treated as "lower is better".
    """
    at_least_one_strictly_better = False

    for a_val, b_val in (
        (a.total_cost, b.total_cost),
        (a.total_carbon, b.total_carbon),
        (a.total_transport_distance, b.total_transport_distance),
    ):
        if a_val > b_val:
            # A is worse in this metric — cannot dominate B
            return False
        if a_val < b_val:
            at_least_one_strictly_better = True

    return at_least_one_strictly_better


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class ParetoResult:
    """Result of a Pareto filtering operation.

    Attributes
    ----------
    pareto_front:
        Non-dominated scenarios (the Pareto front), sorted ascending by
        composite_score so the "most balanced" solution appears first.
    dominated:
        Scenarios that were filtered out because at least one other scenario
        dominates them.
    n_total:
        Total number of input scenarios evaluated.
    n_pareto:
        Number of non-dominated scenarios returned.
    """
    pareto_front: list[ScoredScenario]
    dominated: list[ScoredScenario]
    n_total: int
    n_pareto: int


# ---------------------------------------------------------------------------
# Pareto filter
# ---------------------------------------------------------------------------

class ParetoFilter:
    """Filters a population of scored scenarios to the Pareto-optimal front.

    Usage
    -----
    >>> pf = ParetoFilter()
    >>> result = pf.filter(scored_scenarios)
    >>> front = result.pareto_front
    """

    def filter(self, scenarios: list[ScoredScenario]) -> ParetoResult:
        """Return the non-dominated (Pareto-optimal) subset of *scenarios*.

        Parameters
        ----------
        scenarios:
            List of ScoredScenario objects produced by MultiObjectiveScorer.
            May be empty — returns an empty ParetoResult in that case.

        Returns
        -------
        ParetoResult with pareto_front sorted by composite_score ascending
        (lowest score = best balanced trade-off is first).
        """
        if not scenarios:
            return ParetoResult(
                pareto_front=[],
                dominated=[],
                n_total=0,
                n_pareto=0,
            )

        n = len(scenarios)
        is_dominated = [False] * n

        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                if is_dominated[i]:
                    # Already marked — no need to check further dominators
                    break
                if _dominates(scenarios[j].raw, scenarios[i].raw):
                    is_dominated[i] = True

        pareto_front = [s for k, s in enumerate(scenarios) if not is_dominated[k]]
        dominated = [s for k, s in enumerate(scenarios) if is_dominated[k]]

        # Sort the front by composite_score ascending (best balanced first)
        pareto_front.sort(key=lambda s: s.composite_score)

        return ParetoResult(
            pareto_front=pareto_front,
            dominated=dominated,
            n_total=n,
            n_pareto=len(pareto_front),
        )
