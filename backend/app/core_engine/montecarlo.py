"""
montecarlo.py — Uncertainty quantification for the B1 Science Core.

Runs engine.simulate() N times with inputs sampled from probability
distributions, returning percentile statistics, the fraction of runs with
non-positive net electricity, Spearman-rank sensitivity indices, and
an echo of the distribution metadata.

All results contain only plain Python floats/ints/strings/lists/dicts so
that json.dumps(result) works without a custom encoder.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from app.core_engine.engine import simulate
from app.core_engine.params import Params

# ---------------------------------------------------------------------------
# Validated field names (built once at import time)
# ---------------------------------------------------------------------------
_PARAMS_FIELDS: frozenset = frozenset(
    f.name for f in dataclasses.fields(Params)
)


# ===========================================================================
# Dist dataclass
# ===========================================================================

@dataclass(frozen=True)
class Dist:
    """Description of a probability distribution for one Params field.

    Attributes
    ----------
    kind:
        One of ``"triangular"``, ``"normal"``, ``"uniform"``, ``"lognormal"``.
    args:
        Parameters for the chosen distribution:
        - triangular: (low, mode, high)
        - normal:     (mu, sigma)
        - uniform:    (low, high)
        - lognormal:  (mu_log, sigma_log)  — e.g. (np.log(0.15), 0.3)
    evidence:
        Free-text provenance note. Must not be empty.
    assumed:
        True when this distribution has not been validated against real data.
    clip:
        Optional (lo, hi) hard bounds applied after sampling (e.g. (0.50, 0.70)
        to keep a normal distribution within a physical range). None = no clip.
    """
    kind: str
    args: tuple
    evidence: str
    assumed: bool
    clip: Optional[Tuple[float, float]] = None

    _VALID_KINDS = frozenset({"triangular", "normal", "uniform", "lognormal"})

    def __post_init__(self) -> None:
        if self.kind not in self._VALID_KINDS:
            raise ValueError(
                f"Dist.kind must be one of {sorted(self._VALID_KINDS)}; got '{self.kind}'."
            )
        if not self.evidence or not self.evidence.strip():
            raise ValueError("Dist.evidence must not be empty.")

        if self.kind == "triangular":
            if len(self.args) != 3:
                raise ValueError("triangular requires args=(low, mode, high).")
            low, mode, high = self.args
            if not (low <= mode <= high):
                raise ValueError(
                    f"triangular requires low <= mode <= high; got ({low}, {mode}, {high})."
                )
            if not (low < high):
                raise ValueError(
                    f"triangular requires low < high; got low={low}, high={high}."
                )

        elif self.kind == "normal":
            if len(self.args) != 2:
                raise ValueError("normal requires args=(mu, sigma).")
            _, sigma = self.args
            if sigma <= 0:
                raise ValueError(f"normal requires sigma > 0; got {sigma}.")

        elif self.kind == "uniform":
            if len(self.args) != 2:
                raise ValueError("uniform requires args=(low, high).")
            low, high = self.args
            if not (low < high):
                raise ValueError(
                    f"uniform requires low < high; got low={low}, high={high}."
                )

        elif self.kind == "lognormal":
            if len(self.args) != 2:
                raise ValueError("lognormal requires args=(mu_log, sigma_log).")
            _, sigma_log = self.args
            if sigma_log <= 0:
                raise ValueError(f"lognormal requires sigma_log > 0; got {sigma_log}.")


# ===========================================================================
# default_dists
# ===========================================================================

_EVIDENCE = "placeholder, replace with literature/plant data"


def default_dists() -> Dict[str, Dist]:
    """Return the 9 assumed prior distributions for key Params fields.

    All entries have ``assumed=True`` and a placeholder evidence string.
    Distribution parameters are taken from the parameter_registry uncertainty
    column (see docs/parameter_registry.csv).
    """
    return {
        "y_biogas_nm3_per_kg_vs": Dist(
            kind="triangular", args=(0.35, 0.55, 0.80),
            evidence=_EVIDENCE, assumed=True,
        ),
        "ts_fraction": Dist(
            kind="triangular", args=(0.20, 0.27, 0.35),
            evidence=_EVIDENCE, assumed=True,
        ),
        "suitable_fraction": Dist(
            kind="triangular", args=(0.65, 0.80, 0.90),
            evidence=_EVIDENCE, assumed=True,
        ),
        "eta_el": Dist(
            kind="triangular", args=(0.30, 0.35, 0.40),
            evidence=_EVIDENCE, assumed=True,
        ),
        "ch4_fraction": Dist(
            kind="normal", args=(0.60, 0.03),
            evidence=_EVIDENCE, assumed=True, clip=(0.50, 0.70),
        ),
        "availability": Dist(
            kind="triangular", args=(0.80, 0.90, 0.96),
            evidence=_EVIDENCE, assumed=True,
        ),
        "vs_of_ts": Dist(
            kind="triangular", args=(0.80, 0.88, 0.94),
            evidence=_EVIDENCE, assumed=True,
        ),
        "aux_mix_kwh_m3_d": Dist(
            kind="lognormal", args=(math.log(0.15), 0.3),
            evidence=_EVIDENCE, assumed=True,
        ),
        "ch4_slip": Dist(
            kind="uniform", args=(0.005, 0.03),
            evidence=_EVIDENCE, assumed=True,
        ),
    }


# ===========================================================================
# Internal sampling helpers
# ===========================================================================

def _sample(rng: np.random.Generator, dist: Dist, n: int) -> np.ndarray:
    """Draw *n* samples from *dist* using *rng*."""
    if dist.kind == "triangular":
        low, mode, high = dist.args
        # numpy triangular uses (left, mode, right)
        samples = rng.triangular(low, mode, high, size=n)

    elif dist.kind == "normal":
        mu, sigma = dist.args
        samples = rng.normal(mu, sigma, size=n)

    elif dist.kind == "uniform":
        low, high = dist.args
        samples = rng.uniform(low, high, size=n)

    elif dist.kind == "lognormal":
        mu_log, sigma_log = dist.args
        samples = rng.lognormal(mu_log, sigma_log, size=n)

    else:  # pragma: no cover
        raise ValueError(f"Unknown kind: {dist.kind}")

    if dist.clip is not None:
        samples = np.clip(samples, dist.clip[0], dist.clip[1])

    return samples


def _spearman_r(x: np.ndarray, y: np.ndarray) -> float:
    """Spearman rank correlation between x and y.  Returns 0.0 for constant columns."""
    if np.std(x) == 0 or np.std(y) == 0:
        return 0.0
    # Use scipy if available, otherwise fall back to numpy ranks.
    try:
        from scipy.stats import spearmanr
        r, _ = spearmanr(x, y)
        return float(0.0 if np.isnan(r) else r)
    except ImportError:
        rx = np.argsort(np.argsort(x)).astype(float)
        ry = np.argsort(np.argsort(y)).astype(float)
        rx -= rx.mean(); ry -= ry.mean()
        denom = np.sqrt((rx ** 2).sum() * (ry ** 2).sum())
        return float(0.0 if denom == 0 else (rx * ry).sum() / denom)


# ===========================================================================
# run_mc
# ===========================================================================

def run_mc(
    params: Params,
    dists: Optional[Dict[str, Dist]] = None,
    n: int = 2000,
    seed: int = 42,
) -> Dict[str, Any]:
    """Run a Monte Carlo simulation over ``engine.simulate`` and return statistics.

    Parameters
    ----------
    params:
        Base Params instance.  Fields not covered by *dists* keep their default
        values on every run.
    dists:
        Dict mapping Params field names to :class:`Dist` objects.  ``None``
        uses :func:`default_dists`.
    n:
        Number of simulation runs.  Must be >= 10.
    seed:
        Random seed for reproducibility.

    Returns
    -------
    dict
        Keys: n, seed, median, p2_5, p97_5, p_net_nonpositive,
        runs_with_warnings, sensitivity, distributions, assumptions_note.
        All numeric values are plain Python floats.

    Raises
    ------
    ValueError
        If n < 10, dists is empty, or dists contains unknown Params field names.
    """
    if n < 10:
        raise ValueError(f"n must be >= 10; got {n}.")

    if dists is None:
        dists = default_dists()

    if len(dists) == 0:
        raise ValueError("dists must contain at least one distribution.")

    unknown = set(dists.keys()) - _PARAMS_FIELDS
    if unknown:
        raise ValueError(
            f"Unknown Params field names in dists: {sorted(unknown)}. "
            f"Valid names: {sorted(_PARAMS_FIELDS)}."
        )

    rng = np.random.default_rng(seed)

    # Sample all distributions up-front (n × len(dists) draws, deterministic)
    param_names = list(dists.keys())
    samples: Dict[str, np.ndarray] = {
        name: _sample(rng, dists[name], n) for name in param_names
    }

    # Run engine for each sample
    e_net_values: List[float] = []
    runs_with_warnings = 0

    for i in range(n):
        overrides = {name: float(samples[name][i]) for name in param_names}
        p_i = dataclasses.replace(params, **overrides)
        result = simulate(p_i)
        e_net_values.append(float(result["e_net_kwh_d"]))
        if result["warnings"]:
            runs_with_warnings += 1

    e_net_arr = np.array(e_net_values, dtype=float)

    # Percentile statistics
    median   = float(np.median(e_net_arr))
    p2_5     = float(np.percentile(e_net_arr, 2.5))
    p97_5    = float(np.percentile(e_net_arr, 97.5))
    p_nonpos = float(np.mean(e_net_arr <= 0))

    # Spearman sensitivity (abs correlation with e_net)
    sensitivity = []
    for name in param_names:
        r = _spearman_r(samples[name], e_net_arr)
        sensitivity.append({"input": name, "abs_spearman": float(abs(r))})
    sensitivity.sort(key=lambda x: x["abs_spearman"], reverse=True)

    # Echo distributions (plain-Python, JSON-safe)
    distributions = {
        name: {
            "kind": d.kind,
            "args": list(d.args),
            "evidence": d.evidence,
            "assumed": d.assumed,
            "clip": list(d.clip) if d.clip is not None else None,
        }
        for name, d in dists.items()
    }

    # Assumptions note (required when any dist is assumed)
    any_assumed = any(d.assumed for d in dists.values())
    assumptions_note = (
        "One or more input distributions are flagged as assumed. "
        "The credible interval is only as credible as the distributions and "
        "is not a measure of model accuracy."
        if any_assumed else ""
    )

    return {
        "n": int(n),
        "seed": int(seed),
        "median": median,
        "p2_5": p2_5,
        "p97_5": p97_5,
        "p_net_nonpositive": p_nonpos,
        "runs_with_warnings": int(runs_with_warnings),
        "sensitivity": sensitivity,
        "distributions": distributions,
        "assumptions_note": assumptions_note,
    }
