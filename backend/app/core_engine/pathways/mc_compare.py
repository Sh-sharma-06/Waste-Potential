"""mc_compare.py — Monte Carlo comparison across all five waste-to-energy pathways.

Samples market, feedstock, demand-sink, and (optionally) weather uncertainty inputs,
calls compare_pathways (or compare_with_demand when sinks are supplied) on each run,
and returns win-probability, percentile net values, feasible share, expected regret,
and Spearman sensitivity indices.

All default distributions are ILLUSTRATIVE — assumed=True, evidence="placeholder".
All numeric outputs are plain Python floats (JSON serialisable without a custom encoder).

Core sampled inputs (always active)
------------------------------------
electricity_tariff_inr_per_kwh   LocationContext
compost_price_inr_per_kg         LocationContext
moisture_fraction                Feedstock
lhv_dry_mj_per_kg                Feedstock
eta_el                           sensitivity index (incineration efficiency)
capex_multiplier                 scalar applied to every pathway's capex_inr
transport_cost_inr_per_t_km      LocationContext

Sink sampled inputs (active when sinks are supplied)
-----------------------------------------------------
sink_demand_multiplier    multiplier on each sink's demand_kwh_d  (clipped > 0)
sink_price_multiplier     multiplier on each sink's price_inr_per_kwh (clipped > 0)

Weather sampled input (active when weather is supplied and weather_enabled=True)
---------------------------------------------------------------------------------
rainfall_mm_d    WeatherContext.rainfall_mm_d used in feedstock moisture adjustment

Units
-----
annual_net_value_inr  INR / year
win_probability       fraction [0, 1]  — sums to 1.0 over runs with any feasible pathway
feasible_share        fraction [0, 1]
expected_regret_inr_y INR / year  (mean over runs of best_feasible_net - this_net)
"""
from __future__ import annotations

import dataclasses
import math
from typing import Any, Dict, List, Optional

import numpy as np

from app.core_engine.montecarlo import Dist, _sample
from .feedstock import Feedstock
from .feasibility import PATHWAYS
from .compare import (
    LocationContext,
    PathwayCosts,
    _DEFAULT_COSTS,
    compare_pathways,
)

# ---------------------------------------------------------------------------
# Evidence string shared by all illustrative placeholder distributions
# ---------------------------------------------------------------------------
_EVIDENCE = "placeholder, replace with literature/plant data"

# ---------------------------------------------------------------------------
# Named groups of sampled inputs
# ---------------------------------------------------------------------------
_CORE_INPUT_NAMES: tuple = (
    "electricity_tariff_inr_per_kwh",
    "compost_price_inr_per_kg",
    "moisture_fraction",
    "lhv_dry_mj_per_kg",
    "eta_el",
    "capex_multiplier",
    "transport_cost_inr_per_t_km",
)

_SINK_INPUT_NAMES: tuple = (
    "sink_demand_multiplier",
    "sink_price_multiplier",
)

_WEATHER_INPUT_NAMES: tuple = (
    "rainfall_mm_d",
)

# Full set — exposed for tests / introspection
_INPUT_NAMES: tuple = _CORE_INPUT_NAMES + _SINK_INPUT_NAMES + _WEATHER_INPUT_NAMES


# ---------------------------------------------------------------------------
# default_compare_dists
# ---------------------------------------------------------------------------

def default_compare_dists(
    include_sink: bool = True,
    include_weather: bool = False,
) -> Dict[str, Dist]:
    """Return assumed prior distributions for the MC-compare sampled inputs.

    All distributions have ``assumed=True`` and a placeholder evidence string.
    All numeric values are ILLUSTRATIVE — source=TBD, status="illustrative".

    Parameters
    ----------
    include_sink:
        When True (default) include ``sink_demand_multiplier`` and
        ``sink_price_multiplier`` distributions.
    include_weather:
        When True include ``rainfall_mm_d`` distribution.

    Returns
    -------
    dict
        Keys depend on flags; always contains the seven core input names.
    """
    d: Dict[str, Dist] = {
        "electricity_tariff_inr_per_kwh": Dist(
            kind="triangular", args=(4.0, 7.0, 12.0),
            evidence=_EVIDENCE, assumed=True,
        ),
        "compost_price_inr_per_kg": Dist(
            kind="triangular", args=(0.5, 2.0, 5.0),
            evidence=_EVIDENCE, assumed=True,
        ),
        "moisture_fraction": Dist(
            kind="triangular", args=(0.30, 0.55, 0.75),
            evidence=_EVIDENCE, assumed=True,
            clip=(0.0, 0.99),
        ),
        "lhv_dry_mj_per_kg": Dist(
            kind="triangular", args=(6.0, 12.0, 20.0),
            evidence=_EVIDENCE, assumed=True,
            clip=(0.0, None),   # no finite upper bound; clipped at draw time
        ),
        "eta_el": Dist(
            kind="triangular", args=(0.18, 0.22, 0.28),
            evidence=_EVIDENCE, assumed=True,
            clip=(0.01, 1.0),
        ),
        "capex_multiplier": Dist(
            kind="triangular", args=(0.7, 1.0, 1.5),
            evidence=_EVIDENCE, assumed=True,
            clip=(0.01, None),
        ),
        "transport_cost_inr_per_t_km": Dist(
            kind="triangular", args=(2.0, 5.0, 10.0),
            evidence=_EVIDENCE, assumed=True,
            clip=(0.0, None),
        ),
    }

    if include_sink:
        d["sink_demand_multiplier"] = Dist(
            kind="triangular", args=(0.5, 1.0, 2.0),
            evidence=_EVIDENCE, assumed=True,
            clip=(0.01, None),
        )
        d["sink_price_multiplier"] = Dist(
            kind="triangular", args=(0.7, 1.0, 1.5),
            evidence=_EVIDENCE, assumed=True,
            clip=(0.01, None),
        )

    if include_weather:
        d["rainfall_mm_d"] = Dist(
            kind="triangular", args=(0.0, 5.0, 30.0),
            evidence=_EVIDENCE, assumed=True,
            clip=(0.0, None),
        )

    return d


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _draw_samples(
    rng: np.random.Generator,
    dists: Dict[str, Dist],
    n: int,
) -> Dict[str, np.ndarray]:
    """Draw *n* samples per distribution; handles unbounded upper clips."""
    out: Dict[str, np.ndarray] = {}
    for name, dist in dists.items():
        if dist.clip is not None and dist.clip[1] is None:
            unclipped = dataclasses.replace(dist, clip=None)
            raw = _sample(rng, unclipped, n)
            raw = np.clip(raw, dist.clip[0], None)
            out[name] = raw
        else:
            out[name] = _sample(rng, dist, n)
    return out


def _build_context(
    base: LocationContext,
    tariff: float,
    compost_price: float,
    transport: float,
) -> LocationContext:
    return LocationContext(
        electricity_tariff_inr_per_kwh=max(0.0, tariff),
        compost_price_inr_per_kg=max(0.0, compost_price),
        heat_price_inr_per_kwh=base.heat_price_inr_per_kwh,
        nearest_buyer_km=base.nearest_buyer_km,
        transport_cost_inr_per_t_km=max(0.0, transport),
        grid_available=base.grid_available,
        facilities=list(base.facilities),
    )


def _build_feedstock(
    base: Feedstock,
    moisture: float,
    lhv_dry: float,
) -> Feedstock:
    """Perturb moisture and LHV while keeping composition fractions summing to 1."""
    moisture = min(max(moisture, 0.0), 0.99)
    lhv_dry  = max(lhv_dry, 0.0)
    s = (base.organic_fraction + base.plastic_fraction
         + base.paper_fraction + base.other_fraction)
    scale = (1.0 / s) if s > 0 else 1.0
    return dataclasses.replace(
        base,
        moisture_fraction=moisture,
        lhv_dry_mj_per_kg=lhv_dry,
        organic_fraction=base.organic_fraction * scale,
        plastic_fraction=base.plastic_fraction * scale,
        paper_fraction=base.paper_fraction * scale,
        other_fraction=base.other_fraction * scale,
    )


def _build_costs(
    base_costs: Optional[Dict[str, PathwayCosts]],
    capex_mult: float,
) -> Dict[str, PathwayCosts]:
    out: Dict[str, PathwayCosts] = {}
    for pw in PATHWAYS:
        if base_costs and pw in base_costs:
            pc = base_costs[pw]
        else:
            d = _DEFAULT_COSTS[pw]
            pc = PathwayCosts(
                capex_inr=d["capex_inr"],
                opex_inr_per_t=d["opex_inr_per_t"],
                life_years=d["life_years"],
                discount_rate=d["discount_rate"],
            )
        out[pw] = dataclasses.replace(pc, capex_inr=pc.capex_inr * max(capex_mult, 0.0))
    return out


def _perturb_sinks(base_sinks: list, demand_mult: float, price_mult: float) -> list:
    """Scale each sink's demand and price by their respective multipliers."""
    dm = max(0.0, demand_mult)
    pm = max(0.0, price_mult)
    return [
        dataclasses.replace(
            s,
            demand_kwh_d=s.demand_kwh_d * dm,
            price_inr_per_kwh=s.price_inr_per_kwh * pm,
        )
        for s in base_sinks
    ]


def _spearman_r(x: np.ndarray, y: np.ndarray) -> float:
    """Spearman rank correlation; returns 0.0 (not NaN) for constant columns."""
    if np.std(x) == 0 or np.std(y) == 0:
        return 0.0
    try:
        from scipy.stats import spearmanr
        r, _ = spearmanr(x, y)
        return float(0.0 if (r is None or np.isnan(r)) else r)
    except ImportError:
        rx = np.argsort(np.argsort(x)).astype(float)
        ry = np.argsort(np.argsort(y)).astype(float)
        rx -= rx.mean(); ry -= ry.mean()
        denom = math.sqrt(float((rx ** 2).sum() * (ry ** 2).sum()))
        return float(0.0 if denom == 0 else float((rx * ry).sum()) / denom)


def _echo_dists(dists: Dict[str, Dist]) -> Dict[str, Any]:
    """Return a JSON-safe echo of all distributions used."""
    out: Dict[str, Any] = {}
    for name, d in dists.items():
        clip_s = None
        if d.clip is not None:
            clip_s = [d.clip[0], d.clip[1] if d.clip[1] is not None else None]
        out[name] = {
            "kind": d.kind,
            "args": list(d.args),
            "evidence": d.evidence,
            "assumed": d.assumed,
            "clip": clip_s,
        }
    return out


# ---------------------------------------------------------------------------
# run_mc_compare — public entry point
# ---------------------------------------------------------------------------

def run_mc_compare(
    feedstock: Feedstock,
    context: LocationContext,
    sinks: Optional[list] = None,
    costs: Optional[Dict[str, PathwayCosts]] = None,
    dists: Optional[Dict[str, Dist]] = None,
    n: int = 1000,
    seed: int = 42,
    weather=None,
    weather_enabled: bool = False,
) -> Dict[str, Any]:
    """Monte Carlo comparison across all five waste-to-energy pathways.

    On each run the following inputs are sampled from probability distributions
    and used to construct perturbed inputs to the pathway comparison engine.

    Core inputs (always sampled)
    ----------------------------
    ``electricity_tariff_inr_per_kwh``, ``compost_price_inr_per_kg``,
    ``moisture_fraction``, ``lhv_dry_mj_per_kg``, ``eta_el``,
    ``capex_multiplier``, ``transport_cost_inr_per_t_km``.

    Sink inputs (sampled when *sinks* is not None and non-empty)
    ------------------------------------------------------------
    ``sink_demand_multiplier`` — multiplied into each sink's ``demand_kwh_d``.
    ``sink_price_multiplier``  — multiplied into each sink's ``price_inr_per_kwh``.

    Weather input (sampled when *weather* is not None and *weather_enabled* is True)
    ---------------------------------------------------------------------------------
    ``rainfall_mm_d`` — used by the moisture-adjustment formula.

    ``compare_with_demand`` is called when *sinks* are provided; otherwise
    ``compare_pathways`` is used.

    Parameters
    ----------
    feedstock:
        Base :class:`~feedstock.Feedstock`; ``moisture_fraction`` and
        ``lhv_dry_mj_per_kg`` are perturbed per run.
    context:
        Base :class:`~compare.LocationContext`; ``electricity_tariff_inr_per_kwh``,
        ``compost_price_inr_per_kg``, and ``transport_cost_inr_per_t_km`` are
        perturbed per run.
    sinks:
        Optional list of :class:`~demand.DemandSink` instances.  When non-empty,
        ``compare_with_demand`` is used and sink demand/price are perturbed.
    costs:
        Optional per-pathway :class:`~compare.PathwayCosts` base values.
        ``capex_inr`` is scaled by ``capex_multiplier`` on each run.
    dists:
        Optional overrides for any sampled-input distribution.  Unrecognised
        keys raise :exc:`ValueError`.  Missing keys fall back to
        :func:`default_compare_dists`.
    n:
        Monte Carlo runs.  Must be >= 10.
    seed:
        Random seed for reproducibility (deterministic per seed).
    weather:
        Optional :class:`~weather.WeatherContext`.  Required together with
        ``weather_enabled=True`` to activate rainfall sampling.
    weather_enabled:
        When True and *weather* is not None, ``rainfall_mm_d`` is sampled and
        feedstock moisture is adjusted before each run.

    Returns
    -------
    dict
        ``n``, ``seed``
            Echoed inputs.
        ``win_probability`` dict[str, float]
            Fraction of runs each pathway ranked first among feasible pathways.
            Sums to 1.0 over runs that contain at least one feasible pathway.
        ``net_value_p2_5``, ``net_value_median``, ``net_value_p97_5``
            Per-pathway percentiles of ``annual_net_value_inr`` [INR/y].
        ``feasible_share`` dict[str, float]
            Fraction of runs in which each pathway is feasible.
        ``expected_regret_inr_y`` dict[str, float]
            Mean over all runs of ``best_feasible_net - this_pathway_net``.
        ``sensitivity`` list[dict]
            Sorted descending by ``abs_spearman``; ``abs_spearman`` is 0.0,
            not NaN, for constant columns.
        ``distributions`` dict
            JSON-safe echo of all distributions used.
        ``assumptions_note`` str
            Non-empty caveat: win probabilities are only as credible as the
            assumed distributions and the illustrative pathway models, not
            validated predictions.

    Raises
    ------
    ValueError
        If ``n < 10`` or *dists* contains an unrecognised key.
    """
    if n < 10:
        raise ValueError(f"n must be >= 10; got {n}.")

    has_sinks   = sinks is not None and len(sinks) > 0
    has_weather = weather is not None and weather_enabled

    # Determine valid input names for this call
    valid_names = set(_CORE_INPUT_NAMES)
    if has_sinks:
        valid_names.update(_SINK_INPUT_NAMES)
    if has_weather:
        valid_names.update(_WEATHER_INPUT_NAMES)

    # Build resolved distributions: defaults first, then caller overrides
    resolved = default_compare_dists(
        include_sink=has_sinks,
        include_weather=has_weather,
    )
    if dists is not None:
        unknown = set(dists.keys()) - valid_names
        if unknown:
            raise ValueError(
                f"dists contains unrecognised input names: {sorted(unknown)}. "
                f"Valid names for this call: {sorted(valid_names)}."
            )
        resolved.update(dists)

    rng = np.random.default_rng(seed)
    samples = _draw_samples(rng, resolved, n)
    active_names = list(resolved.keys())

    # --- Per-run accumulators ---
    net_vals:    Dict[str, List[float]] = {pw: [] for pw in PATHWAYS}
    feas_flags:  Dict[str, List[bool]]  = {pw: [] for pw in PATHWAYS}
    win_counts:  Dict[str, int]         = {pw: 0  for pw in PATHWAYS}
    runs_with_feasible = 0
    best_vals: List[float] = []

    for i in range(n):
        tariff     = float(samples["electricity_tariff_inr_per_kwh"][i])
        compost_p  = float(samples["compost_price_inr_per_kg"][i])
        moisture   = float(samples["moisture_fraction"][i])
        lhv_dry    = float(samples["lhv_dry_mj_per_kg"][i])
        capex_mult = float(samples["capex_multiplier"][i])
        transport  = float(samples["transport_cost_inr_per_t_km"][i])

        ctx_i    = _build_context(context, tariff, compost_p, transport)
        fs_i     = _build_feedstock(feedstock, moisture, lhv_dry)
        costs_i  = _build_costs(costs, capex_mult)

        # Optional weather moisture adjustment
        if has_weather:
            from .weather import WeatherContext, adjust_feedstock_moisture
            rainfall = float(samples["rainfall_mm_d"][i])
            wx_i = dataclasses.replace(weather, rainfall_mm_d=max(0.0, rainfall))
            fs_i, _ = adjust_feedstock_moisture(fs_i, wx_i, enabled=True)

        # Optional sink perturbation
        sinks_i = None
        if has_sinks:
            dm = float(samples["sink_demand_multiplier"][i])
            pm = float(samples["sink_price_multiplier"][i])
            sinks_i = _perturb_sinks(sinks, dm, pm)

        # Run comparison
        if has_sinks:
            from .compare import compare_with_demand
            rows = compare_with_demand(
                fs_i, ctx_i, sinks=sinks_i, costs=costs_i, ad_params=None
            )
        else:
            rows = compare_pathways(fs_i, ctx_i, costs=costs_i, ad_params=None)

        # Identify top feasible pathway
        feasible_rows = [r for r in rows if r["feasible"]]
        if feasible_rows:
            runs_with_feasible += 1
            top = feasible_rows[0]
            win_counts[top["pathway"]] += 1
            best_val = float(top["annual_net_value_inr"])
        else:
            best_val = 0.0
        best_vals.append(best_val)

        for r in rows:
            pw = r["pathway"]
            net_vals[pw].append(float(r["annual_net_value_inr"]))
            feas_flags[pw].append(r["feasible"])

    # --- Aggregate ---
    denom = float(runs_with_feasible) if runs_with_feasible > 0 else 1.0
    win_probability = {pw: float(win_counts[pw]) / denom for pw in PATHWAYS}

    best_arr = np.array(best_vals, dtype=float)

    net_value_p2_5:         Dict[str, float] = {}
    net_value_median:       Dict[str, float] = {}
    net_value_p97_5:        Dict[str, float] = {}
    feasible_share:         Dict[str, float] = {}
    expected_regret_inr_y:  Dict[str, float] = {}

    for pw in PATHWAYS:
        arr = np.array(net_vals[pw], dtype=float)
        net_value_p2_5[pw]        = float(np.percentile(arr, 2.5))
        net_value_median[pw]      = float(np.median(arr))
        net_value_p97_5[pw]       = float(np.percentile(arr, 97.5))
        feasible_share[pw]        = float(np.mean(feas_flags[pw]))
        expected_regret_inr_y[pw] = float(np.mean(best_arr - arr))

    # --- Spearman sensitivity (0.0 for constant columns, never NaN) ---
    sensitivity: List[Dict[str, Any]] = []
    for name in active_names:
        r = _spearman_r(samples[name], best_arr)
        sensitivity.append({"input": name, "abs_spearman": float(abs(r))})
    sensitivity.sort(key=lambda d: d["abs_spearman"], reverse=True)

    assumptions_note = (
        "Win probabilities are only as credible as the assumed distributions "
        "and the illustrative pathway models — they are not validated predictions "
        "and must not be used for investment decisions without replacement of "
        "illustrative parameters with site-specific validated data."
    )

    return {
        "n":                    int(n),
        "seed":                 int(seed),
        "win_probability":      win_probability,
        "net_value_p2_5":       net_value_p2_5,
        "net_value_median":     net_value_median,
        "net_value_p97_5":      net_value_p97_5,
        "feasible_share":       feasible_share,
        "expected_regret_inr_y":expected_regret_inr_y,
        "sensitivity":          sensitivity,
        "distributions":        _echo_dists(resolved),
        "assumptions_note":     assumptions_note,
    }
