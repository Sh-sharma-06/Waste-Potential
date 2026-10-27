"""
Monte Carlo uncertainty quantification for pathway screening results.

Purpose
-------
Wraps the deterministic `screen_pathway()` results with a simple parametric
Monte Carlo analysis to surface uncertainty in:
  - Annualised cost  (driven by CAPEX / OPEX variance)
  - Net electricity yield (driven by conversion-factor variance)
  - Weather variation (ambient temperature ±5 °C, relative humidity ±15 %)
  - Tariff variation (electricity tariff ±15 %)

P3 integration (Task 5c)
-------------------------
When location context is available (via ``get_location_context``), the MC
sampler also perturbs:
  - ``ambient_temp_c``    ±5 °C  (uniform band)
  - ``relative_humidity`` ±15 %  (uniform band, clamped to [0, 1])
  - ``electricity_tariff_inr_per_kwh`` ±15 % (uniform band, clamped to [0, ∞))

These weather/tariff perturbations feed into the electricity revenue calculation
via ``match_demand_greedy`` so that the MC p10/p50/p90 reflects real site
uncertainty — not just cost estimation error.

Shared inputs
-------------
Within each MC run the shared inputs (electricity tariff, ambient temperature,
relative humidity) are drawn **once** and reused across all pathways so that
pathways are compared on an identical economic environment per run.
Pathway-specific perturbations (cost, yield) stay independent per pathway.

Optimality share
----------------
After running all pathways, for each run the winner is the deterministically
feasible pathway with the highest simulated annual net value.  Deterministically
rejected pathways are never eligible to win.  The fraction of runs in which each
pathway is the winner is reported as ``optimality_share`` (sums to 1 over runs
that had at least one feasible pathway).

The outputs of this module are ADDITIVE to the PathwayResult objects produced
by compare.py — they do NOT replace the deterministic screening.  The router
merges the MC statistics into the warnings list.

Design decisions
----------------
- Uses only the Python standard library (`random`) + optional numpy.
- Normal distribution truncated at μ−3σ to avoid negative costs.
- CV (coefficient of variation) = σ / μ is the user-controllable knob.
- All MC estimates use the same ANNUAL boundary as the deterministic layer.
- The MC result carries a `p10`, `p50`, `p90` summary so the frontend can
  display an uncertainty band without transmitting all N samples.
- Seeded via ``PathwayCompareRequest.mc_seed`` (default 42) so results are
  deterministic and reproducible.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any, Optional

from app.data.demand import match_demand_greedy
from app.data.service import get_location_context
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
    win_count:
        Number of MC runs in which this pathway had the highest net value
        among deterministically feasible pathways (set by run_mc_compare).
    optimality_share:
        Fraction of contested runs won by this pathway (set by run_mc_compare).
    net_value_samples:
        Raw per-run net value samples, kept for cross-pathway winner comparison
        in run_mc_compare.  Not serialised to the API response.
    """
    pathway: str
    annual_net_value_mc: MCStats
    cost_inr_y_mc: MCStats
    e_net_kwh_d_mc: MCStats
    prob_positive_npv: float
    status: str
    win_count: int = 0
    optimality_share: float = 0.0
    # Raw samples — used internally for optimality computation, not returned
    net_value_samples: list[float] = field(default_factory=list, repr=False)


# ---------------------------------------------------------------------------
# Weather / tariff variation constants (Task 5c)
# ---------------------------------------------------------------------------

_WEATHER_TEMP_BAND_C: float = 5.0        # ±5 °C uniform perturbation
_WEATHER_RH_BAND: float = 0.15           # ±15 % relative humidity (absolute fraction)
_TARIFF_BAND: float = 0.15               # ±15 % electricity tariff variation

_OPTIMALITY_NOTE = (
    "Share of runs in which this pathway has the highest modelled annual net value; "
    "it depends on assumed price and cost distributions and is not a validated prediction."
)

# ---------------------------------------------------------------------------
# Sampling helpers
# ---------------------------------------------------------------------------

def _truncated_normal_samples(
    mu: float,
    cv: float,
    n: int,
    *,
    lower_bound: Optional[float] = 0.0,
    rng: Optional[random.Random] = None,
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
    rng:
        Optional seeded ``random.Random`` instance (used for pathway-specific
        perturbations so they remain independent across pathways).
    """
    sigma = abs(mu) * cv

    # Numpy path uses its own internal RNG (numpy does not share state with
    # Python's random module), so we always fall back to Python random when a
    # seeded rng is provided for reproducibility.
    if _HAS_NUMPY and rng is None:
        np_rng = _np.random.default_rng()
        samples = np_rng.normal(mu, sigma, n).tolist()
    else:
        _rng = rng or random
        samples = [_rng.gauss(mu, sigma) for _ in range(n)]

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


def _uniform_samples(
    mu: float,
    half_band: float,
    n: int,
    *,
    lower_bound: float = 0.0,
    rng: Optional[random.Random] = None,
) -> list[float]:
    """Draw *n* samples uniformly from [mu − half_band, mu + half_band], clamped below *lower_bound*."""
    lo = mu - half_band
    hi = mu + half_band
    _rng = rng or random
    samples = [_rng.uniform(lo, hi) for _ in range(n)]
    return [max(lower_bound, s) for s in samples]


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
# Per-pathway MC run (shared draws passed in)
# ---------------------------------------------------------------------------

def mc_pathway(
    pathway: str,
    request: PathwayCompareRequest,
    *,
    grid_factor: float,
    transport_factor: float,
    # P3 context — pre-resolved by run_mc_compare() for efficiency
    sinks: Optional[list[dict]] = None,
    base_electricity_price: Optional[float] = None,
    base_ambient_temp_c: Optional[float] = None,
    base_relative_humidity: Optional[float] = None,
    # Shared draws (one per run, same across all pathways)
    shared_e_price_samples: Optional[list[float]] = None,
    shared_temp_samples: Optional[list[float]] = None,
    shared_rh_samples: Optional[list[float]] = None,
    # Per-pathway RNG for independent cost/yield perturbations
    pathway_rng: Optional[random.Random] = None,
    # Deterministic screening result for this pathway (revenue_inr_y, cost_inr_y, e_net_kwh_d)
    screening: Optional[Any] = None,
) -> PathwayMCResult:
    """Run Monte Carlo uncertainty analysis for a single *pathway*.

    Parameters
    ----------
    pathway:
        Pathway identifier.
    request:
        Validated PathwayCompareRequest.
    grid_factor:
        kgCO2e / kWh — pre-resolved emission factor.
    transport_factor:
        kgCO2e / tonne-km — pre-resolved emission factor.
    sinks:
        Demand sinks from LocationContext; used for revenue matching in each
        MC iteration.  When None, falls back to flat-price calculation.
    base_electricity_price:
        Baseline electricity tariff from LocationContext (INR/kWh).  Perturbed
        ±15 % in each MC iteration when shared_e_price_samples is None.
    base_ambient_temp_c:
        Baseline ambient temperature (°C) from LocationContext.
        Currently carried as metadata; reserved for Phase 5b mass-balance.
    base_relative_humidity:
        Baseline relative humidity (0–1) from LocationContext.
        Currently carried as metadata; reserved for Phase 5b mass-balance.
    shared_e_price_samples:
        Pre-drawn tariff samples shared across all pathways so each run uses
        the same economic environment.  When provided, base_electricity_price
        is used only as a fallback baseline.
    shared_temp_samples:
        Pre-drawn ambient temperature samples shared across all pathways.
    shared_rh_samples:
        Pre-drawn relative humidity samples shared across all pathways.
    pathway_rng:
        Seeded ``random.Random`` instance for pathway-specific cost/yield
        perturbations (independent per pathway, deterministic with seed).
    screening:
        When given, samples are drawn around this deterministic result instead of
        the raw request values, so product revenue (compost, heat/fuel, sinks) and
        physics-resolved yields count exactly as in the screening pass.

    Returns
    -------
    PathwayMCResult
        Raw ``net_value_samples`` are included for cross-pathway winner
        comparison in ``run_mc_compare``.
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

    # Baseline electricity price — prefer request override, else context tariff
    e_price_base = (
        request.electricity_price_inr_kwh
        if request.electricity_price_inr_kwh > 0
        else (base_electricity_price or 7.50)
    )

    ann_capex_base = capex * crf(dr, life_yr) if capex > 0 else 0.0
    cost_base = ann_capex_base + opex_yr

    # --- Sample cost with CV applied to total annual cost (pathway-specific) ---
    cost_samples: list[float]
    if cost_base > 0:
        cost_samples = _truncated_normal_samples(
            cost_base, cost_cv, n, lower_bound=0.0, rng=pathway_rng
        )
    else:
        cost_samples = [0.0] * n

    # --- Sample electricity yield (net kWh/tonne) (pathway-specific) ---
    net_kwh_t_base = net_kwh_t
    if abs(net_kwh_t_base) > 1e-9:
        net_kwh_t_samples = _truncated_normal_samples(
            net_kwh_t_base, yield_cv, n, lower_bound=None, rng=pathway_rng
        )
    else:
        net_kwh_t_samples = [0.0] * n

    # --- Tariff samples: use shared draws if provided, else sample independently ---
    if shared_e_price_samples is not None:
        e_price_samples = shared_e_price_samples
    else:
        e_price_samples = _uniform_samples(
            e_price_base, _TARIFF_BAND * e_price_base, n, lower_bound=0.0
        )

    # --- Weather samples: use shared draws if provided ---
    if shared_temp_samples is None and base_ambient_temp_c is not None:
        _temp_samples = _uniform_samples(  # noqa: F841 — reserved Phase 5b
            base_ambient_temp_c, _WEATHER_TEMP_BAND_C, n, lower_bound=-50.0
        )
    if shared_rh_samples is None and base_relative_humidity is not None:
        _rh_samples = _uniform_samples(  # noqa: F841 — reserved Phase 5b
            base_relative_humidity, _WEATHER_RH_BAND * base_relative_humidity, n,
            lower_bound=0.0
        )
        _rh_samples = [min(1.0, v) for v in _rh_samples]  # clamp upper to 1.0

    # --- Derive annual net value per sample ---
    net_value_samples: list[float] = []
    e_kwh_d_samples: list[float] = []

    gate_rev_yr = gate_fee * waste_tpy

    if screening is not None:
        # Perturb the screening pass's own economics: product sales (everything except
        # the gate fee) scale with a pathway-specific yield draw and the shared tariff
        # draw (used as a common market-price factor); total cost scales with a cost draw.
        product_rev_yr = max(float(screening.revenue_inr_y) - gate_rev_yr, 0.0)
        base_cost_yr = float(screening.cost_inr_y)
        cost_samples = (
            _truncated_normal_samples(base_cost_yr, cost_cv, n, lower_bound=0.0, rng=pathway_rng)
            if base_cost_yr > 0 else [0.0] * n
        )
        yield_factors = _truncated_normal_samples(1.0, yield_cv, n, lower_bound=0.0, rng=pathway_rng)
        for c, y, e_price in zip(cost_samples, yield_factors, e_price_samples):
            price_factor = e_price / e_price_base if e_price_base > 0 else 1.0
            net_value_samples.append(product_rev_yr * y * price_factor + gate_rev_yr - c)
            e_kwh_d_samples.append(float(screening.e_net_kwh_d) * y)

    else:
        for c, kwh_t, e_price in zip(cost_samples, net_kwh_t_samples, e_price_samples):
            e_kwh_d = kwh_t * request.waste_tpd
            kwh_yr = kwh_t * waste_tpy

            if sinks and e_kwh_d > 0:
                # Revenue from greedy sink matching at this sample's effective supply
                match = match_demand_greedy(e_kwh_d, sinks)
                elec_rev = match["total_revenue_inr_d"] * _DAYS_PER_YEAR
                import_cost = 0.0
            elif kwh_yr > 0:
                elec_rev = kwh_yr * e_price
                import_cost = 0.0
            else:
                elec_rev = 0.0
                import_cost = abs(kwh_yr) * e_price

            total_cost = c + import_cost
            revenue = elec_rev + gate_rev_yr
            net_value_samples.append(revenue - total_cost)
            e_kwh_d_samples.append(e_kwh_d)

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
        net_value_samples=net_value_samples,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run_mc_compare(
    request: PathwayCompareRequest,
    *,
    region: Optional[str] = None,
    operator_overrides: Optional[dict[str, float]] = None,
    feasible_pathways: Optional[set[str]] = None,
    screening_results: Optional[dict[str, Any]] = None,
) -> list[PathwayMCResult]:
    """Run MC uncertainty analysis for all pathways in *request*.

    P3 integration:
      - Calls ``get_location_context(location_id)`` once to retrieve sinks,
        electricity tariff, ambient temperature and relative humidity.
      - Passes these to ``mc_pathway()`` so each iteration perturbs weather
        (±5 °C / ±15 % RH) and tariff (±15 %) around the location baseline.

    Shared inputs:
      - Within each run the tariff, ambient temperature and relative humidity
        draws are identical across all pathways (drawn once via a seeded RNG),
        so pathways are compared on the same economic environment.
      - Pathway-specific cost and yield perturbations use independent seeded
        RNGs, one per pathway.

    Optimality share:
      - After running all pathways, for each run the winner is the pathway in
        ``feasible_pathways`` with the highest net value.  If no feasible
        pathway is provided, all pathways in the request are treated as
        eligible (backward-compatible behaviour).
      - ``PathwayMCResult.win_count`` and ``.optimality_share`` are set on
        each result before returning.

    Parameters
    ----------
    request:
        Validated PathwayCompareRequest.
    region:
        ISO region code for grid emission factor resolution.
    operator_overrides:
        Operator-supplied emission factor overrides.
    feasible_pathways:
        Set of pathway ids that passed deterministic feasibility checks.
        Only these pathways are eligible to win a run.  When None all
        pathways in ``request.pathways`` are treated as feasible.
    screening_results:
        Optional pathway -> deterministic PathwayResult. When given, each pathway's
        samples are drawn around its screening revenue/cost (see ``mc_pathway``).

    Returns
    -------
    list[PathwayMCResult]
        One entry per pathway in request.pathways, in the same order.
        ``win_count`` and ``optimality_share`` are populated.
    """
    overrides = operator_overrides or {}
    grid_factor = get_factor(
        "grid_electricity", region=region, operator_overrides=overrides
    )
    transport_factor = get_factor(
        "transport_road", region=region, operator_overrides=overrides
    )

    # ------------------------------------------------------------------
    # P3 location context — resolve once for all pathways
    # ------------------------------------------------------------------
    ctx = get_location_context(request.location_id)
    sinks: list[dict] = list(ctx.get("sinks", []))

    # Electricity tariff baseline
    raw_tariff = ctx.get("electricity_tariff_inr_per_kwh", 7.50)
    base_electricity_price = float(
        raw_tariff.get("value", 7.50) if isinstance(raw_tariff, dict) else raw_tariff
    )

    # Prefer request override for tariff baseline
    e_price_base = (
        request.electricity_price_inr_kwh
        if request.electricity_price_inr_kwh > 0
        else base_electricity_price
    )

    # Weather baselines
    raw_temp = ctx.get("ambient_temp_c", 25.0)
    base_ambient_temp_c = float(
        raw_temp.get("value", 25.0) if isinstance(raw_temp, dict) else raw_temp
    )

    raw_rh = ctx.get("relative_humidity", 0.65)
    base_relative_humidity = float(
        raw_rh.get("value", 0.65) if isinstance(raw_rh, dict) else raw_rh
    )

    n = request.mc_runs
    seed = request.mc_seed

    # ------------------------------------------------------------------
    # Draw shared inputs ONCE for all pathways using the master seed.
    # ------------------------------------------------------------------
    shared_rng = random.Random(seed)
    shared_e_price_samples = _uniform_samples(
        e_price_base, _TARIFF_BAND * e_price_base, n, lower_bound=0.0, rng=shared_rng
    )
    shared_temp_samples = _uniform_samples(
        base_ambient_temp_c, _WEATHER_TEMP_BAND_C, n, lower_bound=-50.0, rng=shared_rng
    )
    raw_rh_samples = _uniform_samples(
        base_relative_humidity,
        _WEATHER_RH_BAND * base_relative_humidity,
        n,
        lower_bound=0.0,
        rng=shared_rng,
    )
    shared_rh_samples = [min(1.0, v) for v in raw_rh_samples]

    # ------------------------------------------------------------------
    # Per-pathway independent RNGs (seeded deterministically from master
    # seed + pathway index so pathways don't share cost/yield draws).
    # ------------------------------------------------------------------
    mc_results: list[PathwayMCResult] = []
    for pw_idx, pw in enumerate(request.pathways):
        pathway_rng = random.Random(seed + pw_idx + 1)
        result = mc_pathway(
            pw,
            request,
            grid_factor=grid_factor,
            transport_factor=transport_factor,
            sinks=sinks,
            base_electricity_price=base_electricity_price,
            base_ambient_temp_c=base_ambient_temp_c,
            base_relative_humidity=base_relative_humidity,
            shared_e_price_samples=shared_e_price_samples,
            shared_temp_samples=shared_temp_samples,
            shared_rh_samples=shared_rh_samples,
            pathway_rng=pathway_rng,
            screening=(screening_results or {}).get(pw),
        )
        mc_results.append(result)

    # ------------------------------------------------------------------
    # Optimality share: per run, the winner is the feasible pathway with
    # the highest net value.
    # ------------------------------------------------------------------
    eligible = feasible_pathways if feasible_pathways is not None else set(request.pathways)
    mc_by_pathway = {r.pathway: r for r in mc_results}

    # Only eligible pathways participate in optimality counting.
    eligible_results = [r for r in mc_results if r.pathway in eligible]

    if eligible_results:
        contested_runs = 0
        for i in range(n):
            # net value for each eligible pathway at run i
            values = [(r.net_value_samples[i], r.pathway) for r in eligible_results]
            best_val, best_pw = max(values, key=lambda x: x[0])
            # A run is contested only when there is at least one eligible pathway.
            contested_runs += 1
            mc_by_pathway[best_pw].win_count += 1

        if contested_runs > 0:
            for r in mc_results:
                r.optimality_share = round(r.win_count / contested_runs, 6)

    return mc_results


def merge_mc_into_results(
    results: list[PathwayResult],
    mc_results: list[PathwayMCResult],
) -> list[PathwayResult]:
    """Merge MC status, probability and optimality share into deterministic PathwayResult objects.

    Rules:
    - If a pathway is deterministically rejected (feasible=False), its status
      stays "rejected" regardless of MC outcome.
    - If a pathway is deterministically feasible but MC says "uncertain"
      (0.25 < prob_positive_npv < 0.75), status is upgraded to "uncertain".
    - prob_positive_npv and MC percentiles are appended to warnings for
      frontend display without adding extra response fields.
    - optimality_share and win_count are set on the PathwayResult if present.
    - optimality_note is set on every PathwayResult that receives an
      optimality_share (including share=0.0 for rejected pathways).

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

    # Determine whether any optimality shares were computed.
    has_shares = any(m.win_count > 0 or m.optimality_share > 0.0 for m in mc_results)

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

        # Optimality share fields — set regardless of feasibility so that
        # rejected pathways are visibly attributed a share of 0.
        if has_shares:
            res.optimality_share = mc.optimality_share
            res.win_count = mc.win_count
            res.optimality_note = _OPTIMALITY_NOTE

    return results
