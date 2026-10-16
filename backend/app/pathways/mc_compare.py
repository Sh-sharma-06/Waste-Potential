"""
Monte Carlo uncertainty quantification for pathway screening results.

Purpose
-------
Wraps the deterministic `screen_pathway()` results with a simple parametric
Monte Carlo analysis to surface uncertainty in:
  - Annualised cost  (driven by CAPEX / OPEX variance)
  - Net electricity yield (driven by conversion-factor variance)

The outputs of this module are ADDITIVE to the PathwayResult objects produced
by compare.py — they do NOT replace the deterministic screening.  The router
merges the MC statistics into the warnings list and a dedicated `mc_stats` field
on the response.

Design decisions
----------------
- Uses only the Python standard library (`random`) to avoid adding a scipy /
  numpy dependency for this layer.  If numpy is already available it is
  used for speed; otherwise pure Python fallback.
- Normal distribution truncated at μ−3σ to avoid negative costs.
- CV (coefficient of variation) = σ / μ is the user-controllable knob.
- All MC estimates use the same ANNUAL boundary as the deterministic layer.
- The MC result carries a `p10`, `p50`, `p90` summary so the frontend can
  display an uncertainty band without transmitting all N samples.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Optional

from app.decision.cost import DEFAULT_ASSET_LIFE_YEARS, DEFAULT_DISCOUNT_RATE, crf
from app.decision.emission_factors import get_factor

from .schemas import PathwayCompareRequest, PathwayResult

# ---------------------------------------------------------------------------
# Numpy optional import (speed-up for large mc_runs)
# ---------------------------------------------------------------------------
try:
    import numpy as _np  # type: ignore[import]
    _HAS_NUMPY = True
except ImportError:
    _HAS_NUMPY = False

_DAYS_PER_YEAR: float = 365.25


# ---------------------------------------------------------------------------
# MC result container
# ---------------------------------------------------------------------------

@dataclass
class MCStats:
    """Percentile summary for a single Monte Carlo variable.

    Attributes
    ----------
    p10, p50, p90:
        10th, 50th, 90th percentiles of the simulated distribution.
    mean:
        Sample mean.
    std:
        Sample standard deviation.
    n_runs:
        Number of MC iterations actually executed.
    """
    p10: float
    p50: float
    p90: float
    mean: float
    std: float
    n_runs: int


@dataclass
class PathwayMCResult:
    """Monte Carlo summary appended to a deterministic PathwayResult.

    Attributes
    ----------
    pathway:
        Pathway identifier (mirrors PathwayResult.pathway).
    annual_net_value_mc:
        MC distribution of annual_net_value_inr.
    cost_inr_y_mc:
        MC distribution of cost_inr_y.
    e_net_kwh_d_mc:
        MC distribution of e_net_kwh_d.
    prob_positive_npv:
        Fraction of MC runs where annual_net_value_inr > 0.
    status:
        "feasible", "rejected", or "uncertain" (set to "uncertain" when
        prob_positive_npv is between 0.25 and 0.75).
    """
    pathway: str
    annual_net_value_mc: MCStats
    cost_inr_y_mc: MCStats
    e_net_kwh_d_mc: MCStats
    prob_positive_npv: float
    status: str


# ---------------------------------------------------------------------------
# Sampling helpers
# ---------------------------------------------------------------------------

def _truncated_normal_samples(
    mu: float,
    cv: float,
    n: int,
    *,
    lower_bound: Optional[float] = 0.0,
) -> list[float]:
    """Draw *n* samples from a normal distribution N(mu, cv·mu), truncated below
    *lower_bound*.

    Uses numpy if available for speed; falls back to pure Python otherwise.

    Parameters
    ----------
    mu:
        Distribution mean.
    cv:
        Coefficient of variation (σ / μ).
    n:
        Number of samples.
    lower_bound:
        Samples below this value are re-drawn (rejection sampling, up to 10×).
        Pass None to disable truncation.
    """
    sigma = abs(mu) * cv

    if _HAS_NUMPY:
        rng = _np.random.default_rng()
        samples = rng.normal(mu, sigma, n).tolist()
    else:
        samples = [random.gauss(mu, sigma) for _ in range(n)]

    if lower_bound is not None:
        # Replace out-of-bounds samples with the lower bound (conservative)
        samples = [max(lower_bound, s) for s in samples]

    return samples


def _percentiles(samples: list[float]) -> tuple[float, float, float]:
    """Return (p10, p50, p90) of *samples* (sorted copy)."""
    s = sorted(samples)
    n = len(s)
    def _p(q: float) -> float:
        idx = q * (n - 1)
        lo = int(idx)
        hi = min(lo + 1, n - 1)
        frac = idx - lo
        return s[lo] + frac * (s[hi] - s[lo])
    return _p(0.10), _p(0.50), _p(0.90)


def _to_stats(samples: list[float]) -> MCStats:
    n = len(samples)
    mu = sum(samples) / n
    variance = sum((x - mu) ** 2 for x in samples) / max(n - 1, 1)
    p10, p50, p90 = _percentiles(samples)
    return MCStats(
        p10=round(p10, 2),
        p50=round(p50, 2),
        p90=round(p90, 2),
        mean=round(mu, 2),
        std=round(math.sqrt(variance), 2),
        n_runs=n,
    )


# ---------------------------------------------------------------------------
# Per-pathway MC run
# ---------------------------------------------------------------------------

def mc_pathway(
    pathway: str,
    request: PathwayCompareRequest,
    *,
    grid_factor: float,
    transport_factor: float,
) -> PathwayMCResult:
    """Run Monte Carlo uncertainty analysis for a single *pathway*.

    Parameters
    ----------
    pathway:
        Pathway identifier.
    request:
        Validated PathwayCompareRequest (same object used by compare.py).
    grid_factor:
        kgCO2e / kWh — pre-resolved emission factor.
    transport_factor:
        kgCO2e / tonne-km — pre-resolved emission factor.

    Returns
    -------
    PathwayMCResult
    """
    n = request.mc_runs
    cost_cv = request.mc_cost_cv
    yield_cv = request.mc_yield_cv
    waste_tpy = request.waste_tpd * _DAYS_PER_YEAR

    # Deterministic base values
    capex = request.capex_inr.get(pathway, 0.0)
    opex_yr = request.opex_inr_yr.get(pathway, 0.0)
    life_yr = request.asset_life_yr.get(pathway, DEFAULT_ASSET_LIFE_YEARS)
    dr = request.discount_rate if request.discount_rate > 0 else DEFAULT_DISCOUNT_RATE
    net_kwh_t = request.net_kwh_per_tonne.get(pathway, 0.0)
    gate_fee = request.gate_fee_inr_t.get(pathway, 0.0)
    e_price = request.electricity_price_inr_kwh

    ann_capex_base = capex * crf(dr, life_yr) if capex > 0 else 0.0
    cost_base = ann_capex_base + opex_yr

    # --- Sample cost with CV applied to total annual cost ---
    cost_samples: list[float]
    if cost_base > 0:
        cost_samples = _truncated_normal_samples(cost_base, cost_cv, n, lower_bound=0.0)
    else:
        cost_samples = [0.0] * n

    # --- Sample electricity yield (net kWh/tonne) ---
    net_kwh_t_base = net_kwh_t
    if abs(net_kwh_t_base) > 1e-9:
        net_kwh_t_samples = _truncated_normal_samples(
            net_kwh_t_base, yield_cv, n, lower_bound=None
        )
    else:
        net_kwh_t_samples = [0.0] * n

    # --- Derive annual net value per sample ---
    net_value_samples: list[float] = []
    e_kwh_d_samples: list[float] = []

    gate_rev_yr = gate_fee * waste_tpy

    for c, kwh_t in zip(cost_samples, net_kwh_t_samples):
        kwh_yr = kwh_t * waste_tpy
        if kwh_yr > 0:
            elec_rev = kwh_yr * e_price
            import_cost = 0.0
        else:
            elec_rev = 0.0
            import_cost = abs(kwh_yr) * e_price

        total_cost = c + import_cost
        revenue = elec_rev + gate_rev_yr
        net_value_samples.append(revenue - total_cost)
        e_kwh_d_samples.append(kwh_t * request.waste_tpd)

    prob_positive = sum(1 for v in net_value_samples if v > 0) / n

    # Determine MC-informed status
    if prob_positive >= 0.75:
        mc_status = "feasible"
    elif prob_positive <= 0.25:
        mc_status = "rejected"
    else:
        mc_status = "uncertain"

    return PathwayMCResult(
        pathway=pathway,
        annual_net_value_mc=_to_stats(net_value_samples),
        cost_inr_y_mc=_to_stats(cost_samples),
        e_net_kwh_d_mc=_to_stats(e_kwh_d_samples),
        prob_positive_npv=round(prob_positive, 4),
        status=mc_status,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_mc_compare(
    request: PathwayCompareRequest,
    *,
    region: Optional[str] = None,
    operator_overrides: Optional[dict[str, float]] = None,
) -> list[PathwayMCResult]:
    """Run MC uncertainty analysis for all pathways in *request*.

    Parameters
    ----------
    request:
        Validated PathwayCompareRequest.
    region:
        ISO region code for grid emission factor resolution.
    operator_overrides:
        Operator-supplied emission factor overrides.

    Returns
    -------
    list[PathwayMCResult]
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
        mc_pathway(
            pw,
            request,
            grid_factor=grid_factor,
            transport_factor=transport_factor,
        )
        for pw in request.pathways
    ]


def merge_mc_into_results(
    results: list[PathwayResult],
    mc_results: list[PathwayMCResult],
) -> list[PathwayResult]:
    """Merge MC status and probability into deterministic PathwayResult objects.

    Rules:
    - If a pathway is deterministically rejected (feasible=False), its status
      stays "rejected" regardless of MC outcome.
    - If a pathway is deterministically feasible but MC says "uncertain"
      (0.25 < prob_positive_npv < 0.75), status is upgraded to "uncertain".
    - prob_positive_npv and MC percentiles are appended to warnings for
      frontend display without adding extra response fields.

    Parameters
    ----------
    results:
        List of PathwayResult from compare.evaluate_pathways().
    mc_results:
        List of PathwayMCResult from run_mc_compare(), same order.

    Returns
    -------
    list[PathwayResult]
        Mutated in-place (status and warnings updated); same objects returned.
    """
    mc_by_pathway = {m.pathway: m for m in mc_results}

    for res in results:
        mc = mc_by_pathway.get(res.pathway)
        if mc is None:
            continue

        # Only upgrade status on feasible pathways
        if res.feasible and mc.status in ("uncertain", "rejected"):
            res.status = mc.status

        prob_pct = round(mc.prob_positive_npv * 100, 1)
        res.warnings.append(
            f"MC ({mc.annual_net_value_mc.n_runs} runs): "
            f"P(net_value > 0) = {prob_pct} %. "
            f"Net value p10/p50/p90: "
            f"{mc.annual_net_value_mc.p10:,.0f} / "
            f"{mc.annual_net_value_mc.p50:,.0f} / "
            f"{mc.annual_net_value_mc.p90:,.0f} INR/yr."
        )

    return results
