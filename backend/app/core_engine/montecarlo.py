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

# Fraction-valued Params fields that must be clipped to [0, 1] after sampling.
_FRACTION_FIELDS: frozenset = frozenset({
    "ts_fraction", "vs_of_ts", "suitable_fraction", "eta_el",
    "ch4_fraction", "availability", "ch4_slip",
})

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
# recentred_dists
# ===========================================================================

def recentred_dists(
    params: Params,
    base: Optional[Dict[str, "Dist"]] = None,
) -> Dict[str, "Dist"]:
    """Return distributions from *base* recentred on the values in *params*.

    For each parameter name in *base*:
    - Let *d* be the default value (``Params().<name>``) and *v* the run value
      (``getattr(params, name)``).
    - If ``v == d``: return the Dist unchanged.
    - If ``v == 0`` or ``d == 0``: **omit** the parameter (it will be held
      fixed at the run value by the caller).
    - Otherwise scale by ``r = v / d``:
        - triangular: ``(low*r, mode*r, high*r)``
        - uniform:    ``(low*r, high*r)``
        - normal:     ``(mu*r, sigma*r)``
        - lognormal:  ``(mu_log + ln(r), sigma_log)``
        - clip bounds scaled by ``r`` (if present).
      Appends `` | recentred on run value`` to the evidence string.

    Parameters
    ----------
    params:
        The run's Params instance whose values are used as new centres.
    base:
        The base dict of Dist objects to recentre.  Defaults to
        ``default_dists()``.

    Returns
    -------
    dict[str, Dist]
        A new dict containing recentred (or unchanged) Dist objects.
        Parameters that cannot be scaled (``v == 0`` or ``d == 0``) are
        omitted so the caller can hold them fixed.
    """
    if base is None:
        base = default_dists()

    defaults = Params()
    result: Dict[str, Dist] = {}

    for name, dist in base.items():
        d = getattr(defaults, name)  # default value
        v = getattr(params, name)    # run value

        # Cannot scale: leave out entirely so caller holds it fixed.
        if v == 0 or d == 0:
            continue

        # No change needed.
        if v == d:
            result[name] = dist
            continue

        r = v / d
        new_evidence = dist.evidence + " | recentred on run value"

        if dist.kind == "triangular":
            low, mode, high = dist.args
            new_args: tuple = (low * r, mode * r, high * r)
        elif dist.kind == "uniform":
            low, high = dist.args
            new_args = (low * r, high * r)
        elif dist.kind == "normal":
            mu, sigma = dist.args
            new_args = (mu * r, sigma * r)
        elif dist.kind == "lognormal":
            mu_log, sigma_log = dist.args
            new_args = (mu_log + math.log(r), sigma_log)
        else:  # pragma: no cover
            result[name] = dist
            continue

        new_clip: Optional[Tuple[float, float]] = None
        if dist.clip is not None:
            new_clip = (dist.clip[0] * r, dist.clip[1] * r)

        result[name] = Dist(
            kind=dist.kind,
            args=new_args,
            evidence=new_evidence,
            assumed=dist.assumed,
            clip=new_clip,
        )

    return result


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
    recentre: bool = True,
) -> Dict[str, Any]:
    """Run a Monte Carlo simulation over ``engine.simulate`` and return statistics.

    Parameters
    ----------
    params:
        Base Params instance.  Fields not covered by *dists* keep their
        values on every run.
    dists:
        Dict mapping Params field names to :class:`Dist` objects.
        - ``None`` + ``recentre=True``  → :func:`recentred_dists(params)`
        - ``None`` + ``recentre=False`` → :func:`default_dists` (old behaviour)
        - Caller-supplied dict          → used exactly as given (no recentring).
    n:
        Number of simulation runs.  Must be >= 10.
    seed:
        Random seed for reproducibility.
    recentre:
        When *dists* is ``None`` and this is ``True`` (default), use
        :func:`recentred_dists` so the distributions are centred on *params*
        rather than on the hard-coded defaults.

    Returns
    -------
    dict
        Keys: n, seed, median, p2_5, p97_5, p_net_nonpositive,
        runs_with_warnings, sensitivity, distributions, assumptions_note,
        centred_on, fixed_inputs, recentred, clipped_samples.
        All numeric values are plain Python floats.

    Raises
    ------
    ValueError
        If n < 10, dists is empty, or dists contains unknown Params field names.
    """
    if n < 10:
        raise ValueError(f"n must be >= 10; got {n}.")

    # Determine whether we applied recentring and which params are fixed.
    caller_supplied = dists is not None
    fixed_inputs: List[str] = []

    if dists is None:
        if recentre:
            dists = recentred_dists(params)
            _recentred = True
            # Parameters in default_dists that were omitted (v==0 or d==0)
            # are held fixed at the run value.
            all_default_names = set(default_dists().keys())
            fixed_inputs = sorted(all_default_names - set(dists.keys()))
        else:
            dists = default_dists()
            _recentred = False
    else:
        _recentred = False

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

    # Clip fraction-valued parameters to [0, 1] and count clipped samples.
    clipped_samples = 0
    for name in param_names:
        if name in _FRACTION_FIELDS:
            arr = samples[name]
            clipped = np.clip(arr, 0.0, 1.0)
            clipped_samples += int(np.sum(clipped != arr))
            samples[name] = clipped

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
    centred_note = (
        " Distributions are centred on the stored run values."
        if _recentred else
        " Distributions are centred on hard-coded prior defaults, not the run values."
        if not caller_supplied else ""
    )
    assumptions_note = (
        (
            "One or more input distributions are flagged as assumed. "
            "The credible interval is only as credible as the distributions and "
            "is not a measure of model accuracy."
            if any_assumed else ""
        ) + centred_note
    ).strip()

    # centred_on: echo the sampled parameter value from the run
    centred_on: Dict[str, float] = {
        name: float(getattr(params, name)) for name in param_names
    }

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
        "centred_on": centred_on,
        "fixed_inputs": fixed_inputs,
        "recentred": bool(_recentred),
        "clipped_samples": int(clipped_samples),
    }

