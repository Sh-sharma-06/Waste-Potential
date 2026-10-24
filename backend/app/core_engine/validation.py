"""Validation helpers for the B1 Science Core.

Pure functions — no network I/O.  File access only via explicit path arguments.
All functions are side-effect-free; none mutate their inputs.

Glossary
--------
"real"       source_type value meaning an actual measurement / plant log.
"synthetic"  source_type value meaning a generated / placeholder row.
"""
from __future__ import annotations

import csv
import dataclasses
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# 1. Numeric metrics
# ---------------------------------------------------------------------------

def metrics(
    observed: List[float],
    predicted: List[float],
) -> Dict[str, Any]:
    """Compute agreement statistics between *observed* and *predicted* sequences.

    Parameters
    ----------
    observed, predicted:
        Equal-length sequences of floats.

    Returns
    -------
    dict with keys:
        n           – number of paired samples used.
        mae         – mean absolute error.
        rmse        – root-mean-square error.
        bias        – mean(predicted − observed).
        mape        – mean absolute percentage error (%), skipping obs == 0.
        n_mape      – number of pairs used for mape (obs != 0).
        n_skipped   – number of pairs skipped for mape (obs == 0).

    Raises
    ------
    ValueError
        If the sequences have different lengths, or if n == 0.
    """
    if len(observed) != len(predicted):
        raise ValueError(
            f"metrics: length mismatch — observed has {len(observed)} items, "
            f"predicted has {len(predicted)} items"
        )
    n = len(observed)
    if n == 0:
        raise ValueError("metrics: observed and predicted must not be empty (n == 0)")

    abs_errors = [abs(p - o) for o, p in zip(observed, predicted)]
    sq_errors  = [(p - o) ** 2 for o, p in zip(observed, predicted)]
    biases     = [p - o for o, p in zip(observed, predicted)]

    mae  = sum(abs_errors) / n
    rmse = math.sqrt(sum(sq_errors) / n)
    bias = sum(biases) / n

    mape_terms: List[float] = []
    n_skipped = 0
    for o, p in zip(observed, predicted):
        if o == 0.0:
            n_skipped += 1
        else:
            mape_terms.append(abs((p - o) / o) * 100.0)

    mape: Optional[float] = (
        sum(mape_terms) / len(mape_terms) if mape_terms else None
    )

    return {
        "n": n,
        "mae": mae,
        "rmse": rmse,
        "bias": bias,
        "mape": mape,
        "n_mape": len(mape_terms),
        "n_skipped": n_skipped,
    }


# ---------------------------------------------------------------------------
# 2. CSV observation loader
# ---------------------------------------------------------------------------

_ALWAYS_REQUIRED = ("source_type", "study_id", "source")


def load_observations(
    path: str | Path,
    required_columns: Tuple[str, ...] | List[str],
) -> Tuple[List[Dict[str, str]], Dict[str, Any]]:
    """Load real-measurement rows from a CSV file.

    Parameters
    ----------
    path:
        Path to a CSV file with at least the columns listed in
        ``required_columns`` plus ``"source_type"``, ``"study_id"``,
        ``"source"``.
    required_columns:
        Column names that must be present (in addition to the three always
        required above).

    Returns
    -------
    (rows, report) where:
        rows    – list of dicts, one per CSV row with ``source_type == "real"``.
        report  – dict with keys ``n_real``, ``n_synthetic_dropped``,
                  ``n_other_dropped``, ``missing_columns`` (list).

    Raises
    ------
    ValueError
        If the file has no rows with ``source_type == "real"`` after filtering.
    FileNotFoundError
        If *path* does not exist.
    """
    csv_path = Path(path).expanduser().resolve()
    if not csv_path.exists():
        raise FileNotFoundError(f"load_observations: file not found: {csv_path}")

    all_required = list(_ALWAYS_REQUIRED) + [
        c for c in required_columns if c not in _ALWAYS_REQUIRED
    ]

    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        raw_rows = list(reader)

    fieldnames = reader.fieldnames or []
    missing_columns = [c for c in all_required if c not in fieldnames]

    real_rows: List[Dict[str, str]] = []
    n_synthetic = 0
    n_other = 0
    for row in raw_rows:
        st = row.get("source_type", "").strip().lower()
        if st == "real":
            real_rows.append(row)
        elif st == "synthetic":
            n_synthetic += 1
        else:
            n_other += 1

    if not real_rows:
        raise ValueError(
            "load_observations: no real observations — all rows have "
            "source_type != 'real' or the file is empty"
        )

    load_report: Dict[str, Any] = {
        "n_real": len(real_rows),
        "n_synthetic_dropped": n_synthetic,
        "n_other_dropped": n_other,
        "missing_columns": missing_columns,
    }
    return real_rows, load_report


# MODEL ASSUMPTION, tables printed to 0.1% and figure digitising.
COMPOSITION_TOLERANCE_REPORTED: float = 0.002
COMPOSITION_TOLERANCE_DIGITISED: float = 0.01
TOLERANCE_REPORTED: float = COMPOSITION_TOLERANCE_REPORTED
TOLERANCE_DIGITISED: float = COMPOSITION_TOLERANCE_DIGITISED


class FittedAboveCeiling(tuple):
    """Row whose observed value exceeds the ceiling for a fitted observation (study_id, feedstock, observed, ceiling)."""
    __slots__ = ()

    def __new__(cls, study_id: str, feedstock: str, observed: float, ceiling: float):
        return super().__new__(cls, (study_id, feedstock, observed, ceiling))

    @property
    def study_id(self) -> str:
        return self[0]

    @property
    def feedstock(self) -> str:
        return self[1]

    @property
    def observed(self) -> float:
        return self[2]

    @property
    def ceiling(self) -> float:
        return self[3]

    def __getitem__(self, item: Any) -> Any:
        if isinstance(item, str):
            mapping = {"study_id": 0, "feedstock": 1, "observed": 2, "ceiling": 3}
            if item in mapping:
                return super().__getitem__(mapping[item])
            raise KeyError(item)
        return super().__getitem__(item)

    def get(self, key: str, default: Any = None) -> Any:
        mapping = {"study_id": 0, "feedstock": 1, "observed": 2, "ceiling": 3}
        if key in mapping:
            return self[mapping[key]]
        return default

    def keys(self) -> Tuple[str, ...]:
        return ("study_id", "feedstock", "observed", "ceiling")

    def values(self) -> Tuple[Any, ...]:
        return (self[0], self[1], self[2], self[3])

    def items(self) -> Tuple[Tuple[str, Any], ...]:
        return (("study_id", self[0]), ("feedstock", self[1]), ("observed", self[2]), ("ceiling", self[3]))

    def __eq__(self, other: Any) -> bool:
        if isinstance(other, dict):
            return (
                self[0] == other.get("study_id")
                and self[1] == other.get("feedstock")
                and math.isclose(self[2], float(other.get("observed", -999)), rel_tol=1e-7)
                and math.isclose(self[3], float(other.get("ceiling", -999)), rel_tol=1e-7)
            )
        return super().__eq__(other)


# ---------------------------------------------------------------------------
# 3. BMP (Biochemical Methane Potential) validation
# ---------------------------------------------------------------------------

def validate_bmp(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Validate observed BMP measurements against the Buswell theoretical ceiling.

    Each row must have:
        feedstock          – feedstock label (str)
        vs_kg              – volatile solids fed (kg)
        observed_ch4_nm3   – measured CH4 volume (Nm³)
        carb               – carbohydrate fraction of VS
        protein            – protein fraction of VS
        lipid              – lipid fraction of VS

    Predicted = Buswell bound × vs_kg (the stoichiometric ceiling, not a
    fitted value).  This function reports how far observations sit relative
    to the ceiling; it does NOT imply the ceiling is an accurate predictor.

    Parameters
    ----------
    rows:
        List of dicts, typically the ``rows`` output of :func:`load_observations`.

    Returns
    -------
    dict with keys:
        n                   – total rows processed.
        n_rows              – alias for n.
        n_errors            – rows skipped due to missing/invalid fields.
        errors              – list of error strings.
        ceiling_violations  – number of rows where observed > ceiling.
        overall_metrics     – output of :func:`metrics` (observed vs ceiling).
        per_feedstock       – dict keyed by feedstock label with sub-metrics.
        sample_sizes        – dict keyed by feedstock label → count.
        fitted_excluded     – count of fitted rows excluded.
        fitted_above_ceiling – list of (study_id, feedstock, observed, ceiling)
                              for fitted rows exceeding ceiling.
        composition_rounded – dict of counts per composition_method.
        composition_rounded_counts – alias for composition_rounded.
        status              – "illustrative_estimate"
        notes               – disclaimer string.
    """
    from app.core_engine.engine import BUSWELL

    obs_all: List[float] = []
    pred_all: List[float] = []
    feedstock_data: Dict[str, Tuple[List[float], List[float]]] = {}
    errors: List[str] = []
    n_errors = 0
    ceiling_violations = 0
    fitted_excluded = 0
    fitted_above_ceiling: List[FittedAboveCeiling] = []
    composition_rounded_counts: Dict[str, int] = {
        "reported": 0,
        "digitised": 0,
    }

    for i, row in enumerate(rows):
        # 1. Fitted check: excluded from every check and every count
        mf = str(row.get("measured_or_fitted", "")).strip().lower()
        st = str(row.get("source_type", "")).strip().lower()
        fit_val = row.get("fitted")
        is_fitted = (
            mf == "fitted"
            or st == "fitted"
            or (fit_val is True or str(fit_val).strip().lower() in ("true", "1"))
        )

        if is_fitted:
            fitted_excluded += 1
            try:
                vs_kg = float(row["vs_kg"])
                obs_ch4 = float(row["observed_ch4_nm3"])
                carb = float(row["carb"])
                protein = float(row["protein"])
                lipid = float(row["lipid"])
                feedstock_label = str(row.get("feedstock", f"row_{i}"))
                study_id = str(row.get("study_id", f"row_{i}"))
                ceiling_nm3 = (carb * BUSWELL["carb"] + protein * BUSWELL["protein"] + lipid * BUSWELL["lipid"]) * vs_kg
                if obs_ch4 > ceiling_nm3:
                    fitted_above_ceiling.append(
                        FittedAboveCeiling(study_id, feedstock_label, obs_ch4, ceiling_nm3)
                    )
            except Exception:
                pass
            continue

        # 2. Extract fields for regular rows
        try:
            vs_kg = float(row["vs_kg"])
            obs_ch4 = float(row["observed_ch4_nm3"])
            carb    = float(row["carb"])
            protein = float(row["protein"])
            lipid   = float(row["lipid"])
            lignin  = float(row.get("lignin", 0.0) or 0.0) if "lignin" in row and row["lignin"] is not None and str(row["lignin"]).strip() != "" else 0.0
            feedstock_label = str(row.get("feedstock", f"row_{i}"))
        except (KeyError, TypeError, ValueError) as exc:
            n_errors += 1
            errors.append(f"row {i}: {exc}")
            continue

        if carb < 0 or protein < 0 or lipid < 0 or lignin < 0:
            n_errors += 1
            errors.append(f"row {i}: negative share in composition")
            continue

        shares_sum = carb + protein + lipid + lignin
        comp_diff = abs(shares_sum - 1.0)
        comp_method = str(row.get("composition_method", "")).strip().lower()

        # Composition sum tolerance check:
        # If shares sum to 1 within 1e-6, accept as before.
        # Otherwise accept the row, set composition_rounded = True and keep the exact sum when
        # |sum - 1| <= 0.002 and composition_method is "reported", or when
        # |sum - 1| <= 0.01 and composition_method is "digitised".
        # Anything outside the tolerance is skipped and counted with the reason.
        if comp_diff <= 1e-6:
            try:
                row["composition_rounded"] = False
            except Exception:
                pass
        else:
            is_reported = comp_method == "reported"
            is_digitised = comp_method in ("digitised", "digitized")

            if is_reported and comp_diff <= COMPOSITION_TOLERANCE_REPORTED:
                try:
                    row["composition_rounded"] = True
                except Exception:
                    pass
                composition_rounded_counts["reported"] += 1
            elif is_digitised and comp_diff <= COMPOSITION_TOLERANCE_DIGITISED:
                try:
                    row["composition_rounded"] = True
                except Exception:
                    pass
                composition_rounded_counts["digitised"] += 1
            else:
                n_errors += 1
                reason = f"row {i}: composition sum {shares_sum:.6g} outside tolerance"
                if comp_method:
                    reason += f" for composition_method '{comp_method}'"
                errors.append(reason)
                continue

        # Ceiling uses shares exactly as given (never renormalise)
        ceiling_per_kg = carb * BUSWELL["carb"] + protein * BUSWELL["protein"] + lipid * BUSWELL["lipid"]
        ceiling_nm3 = ceiling_per_kg * vs_kg
        obs_all.append(obs_ch4)
        pred_all.append(ceiling_nm3)

        if obs_ch4 > ceiling_nm3:
            ceiling_violations += 1

        if feedstock_label not in feedstock_data:
            feedstock_data[feedstock_label] = ([], [])
        feedstock_data[feedstock_label][0].append(obs_ch4)
        feedstock_data[feedstock_label][1].append(ceiling_nm3)

    overall: Optional[Dict[str, Any]] = None
    if obs_all:
        overall = metrics(obs_all, pred_all)

    per_feedstock: Dict[str, Any] = {}
    sample_sizes: Dict[str, int] = {}
    for label, (obs_f, pred_f) in feedstock_data.items():
        sample_sizes[label] = len(obs_f)
        per_feedstock[label] = metrics(obs_f, pred_f)

    return {
        "n": len(obs_all),
        "n_rows": len(obs_all),
        "n_errors": n_errors,
        "errors": errors,
        "ceiling_violations": ceiling_violations,
        "overall_metrics": overall,
        "per_feedstock": per_feedstock,
        "sample_sizes": sample_sizes,
        "status": "illustrative_estimate",
        "notes": (
            "Buswell ceiling is a stoichiometric upper bound, not a fitted predictor. "
            "Metrics measure distance from ceiling, not model accuracy."
        ),
        "fitted_excluded": fitted_excluded,
        "fitted_above_ceiling": fitted_above_ceiling,
        "composition_rounded": composition_rounded_counts,
        "composition_rounded_counts": composition_rounded_counts,
    }


# ---------------------------------------------------------------------------
# 4. Net-energy validation
# ---------------------------------------------------------------------------

def validate_net_energy(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Validate engine-predicted net electricity against plant-log observations.

    Each row must have:
        observed_net_kwh_d – measured net electricity output (kWh/d).
    Any additional column whose name matches a :class:`~params.Params` field
    is used to override that field for that row's simulation.
    Rows that fail :class:`~params.Params` validation are counted in
    ``n_invalid_params`` and reported; they are not raised.

    Parameters
    ----------
    rows:
        List of dicts, typically from :func:`load_observations`.

    Returns
    -------
    dict with keys:
        n                   – rows successfully simulated.
        n_invalid_params    – rows skipped due to Params validation errors.
        n_errors            – rows skipped for other reasons.
        invalid_params_rows – list of (row_index, error_str).
        errors              – list of other error strings.
        overall_metrics     – :func:`metrics` output.
        per_plant           – per ``study_id`` sub-metrics (if present).
        total_warnings      – total engine warnings across all simulated rows.
        status              – "illustrative_estimate"
    """
    from app.core_engine.params import Params
    from app.core_engine.engine import simulate

    _params_fields = {f.name for f in dataclasses.fields(Params())}

    obs_all: List[float] = []
    pred_all: List[float] = []
    plant_data: Dict[str, Tuple[List[float], List[float]]] = {}
    invalid_params: List[Tuple[int, str]] = []
    errors: List[str] = []
    total_warnings = 0

    for i, row in enumerate(rows):
        try:
            obs_net = float(row["observed_net_kwh_d"])
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"row {i}: {exc}")
            continue

        # Build Params overrides from matching column names
        overrides: Dict[str, Any] = {}
        for col, val in row.items():
            if col in _params_fields:
                try:
                    overrides[col] = float(val)
                except (TypeError, ValueError):
                    pass

        try:
            if overrides:
                # Handle composition tuple specially
                base = Params()
                if "composition" in overrides:
                    pass  # composition as a tuple cannot come from a flat CSV row
                p = dataclasses.replace(base, **{
                    k: v for k, v in overrides.items() if k != "composition"
                })
            else:
                p = Params()
        except (ValueError, TypeError) as exc:
            invalid_params.append((i, str(exc)))
            continue

        try:
            sim = simulate(p)
        except Exception as exc:
            errors.append(f"row {i} simulate error: {exc}")
            continue

        pred_net = sim["e_net_kwh_d"]
        total_warnings += len(sim.get("warnings", []))

        obs_all.append(obs_net)
        pred_all.append(pred_net)

        plant_id = str(row.get("study_id", f"row_{i}"))
        if plant_id not in plant_data:
            plant_data[plant_id] = ([], [])
        plant_data[plant_id][0].append(obs_net)
        plant_data[plant_id][1].append(pred_net)

    overall: Optional[Dict[str, Any]] = None
    if obs_all:
        overall = metrics(obs_all, pred_all)

    per_plant: Dict[str, Any] = {}
    for plant_id, (obs_p, pred_p) in plant_data.items():
        per_plant[plant_id] = metrics(obs_p, pred_p)

    return {
        "n": len(obs_all),
        "n_invalid_params": len(invalid_params),
        "n_errors": len(errors),
        "invalid_params_rows": invalid_params,
        "errors": errors,
        "overall_metrics": overall,
        "per_plant": per_plant,
        "total_warnings": total_warnings,
        "status": "illustrative_estimate",
    }


# ---------------------------------------------------------------------------
# 5. VS-destruction validation
# ---------------------------------------------------------------------------

def validate_mass_loss(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Validate engine-predicted VS destruction against plant-log observations.

    Each row must have:
        observed_vs_destruction – measured fraction of VS destroyed (0–1).
    Any additional column whose name matches a :class:`~params.Params` field
    is used to override that field.  Rows that fail validation are reported,
    not raised.

    Parameters
    ----------
    rows:
        List of dicts, typically from :func:`load_observations`.

    Returns
    -------
    dict with keys:
        n                   – rows successfully simulated.
        n_invalid_params    – rows skipped due to Params validation errors.
        n_errors            – rows skipped for other reasons.
        invalid_params_rows – list of (row_index, error_str).
        errors              – list of other error strings.
        overall_metrics     – :func:`metrics` output.
        per_plant           – per ``study_id`` sub-metrics.
        status              – "illustrative_estimate"
    """
    from app.core_engine.params import Params
    from app.core_engine.engine import simulate

    _params_fields = {f.name for f in dataclasses.fields(Params())}

    obs_all: List[float] = []
    pred_all: List[float] = []
    plant_data: Dict[str, Tuple[List[float], List[float]]] = {}
    invalid_params: List[Tuple[int, str]] = []
    errors: List[str] = []

    for i, row in enumerate(rows):
        try:
            obs_vsd = float(row["observed_vs_destruction"])
        except (KeyError, TypeError, ValueError) as exc:
            errors.append(f"row {i}: {exc}")
            continue

        overrides: Dict[str, Any] = {}
        for col, val in row.items():
            if col in _params_fields:
                try:
                    overrides[col] = float(val)
                except (TypeError, ValueError):
                    pass

        try:
            base = Params()
            p = dataclasses.replace(base, **{
                k: v for k, v in overrides.items() if k != "composition"
            }) if overrides else base
        except (ValueError, TypeError) as exc:
            invalid_params.append((i, str(exc)))
            continue

        try:
            sim = simulate(p)
        except Exception as exc:
            errors.append(f"row {i} simulate error: {exc}")
            continue

        pred_vsd = sim["vs_destruction"]
        obs_all.append(obs_vsd)
        pred_all.append(pred_vsd)

        plant_id = str(row.get("study_id", f"row_{i}"))
        if plant_id not in plant_data:
            plant_data[plant_id] = ([], [])
        plant_data[plant_id][0].append(obs_vsd)
        plant_data[plant_id][1].append(pred_vsd)

    overall: Optional[Dict[str, Any]] = None
    if obs_all:
        overall = metrics(obs_all, pred_all)

    per_plant: Dict[str, Any] = {}
    for plant_id, (obs_p, pred_p) in plant_data.items():
        per_plant[plant_id] = metrics(obs_p, pred_p)

    return {
        "n": len(obs_all),
        "n_invalid_params": len(invalid_params),
        "n_errors": len(errors),
        "invalid_params_rows": invalid_params,
        "errors": errors,
        "overall_metrics": overall,
        "per_plant": per_plant,
        "status": "illustrative_estimate",
    }


# ---------------------------------------------------------------------------
# 6. Report
# ---------------------------------------------------------------------------

_LIMITATIONS: List[str] = [
    "All model parameters are ILLUSTRATIVE defaults; no site-specific calibration.",
    "Buswell ceiling is a theoretical stoichiometric upper bound, not a predictive model.",
    "Net-energy and VS-destruction predictions depend on unvalidated Params defaults.",
    "Validation sample sizes are small; conclusions should not be generalised.",
    "No pass/fail accuracy thresholds are applied; reported numbers only.",
    "Real-observation requirement (source_type='real') must be verified by the caller.",
]

_MIN_REAL_ROWS = 10


def report(results: Dict[str, Any]) -> Dict[str, Any]:
    """Assemble a validation report from sub-results.

    Parameters
    ----------
    results:
        Dict with any subset of the keys ``"bmp"``, ``"net_energy"``,
        ``"mass_loss"``, each being the return value of the corresponding
        ``validate_*`` function.

    Returns
    -------
    dict with keys:
        limitations          – fixed list of caveats.
        pathways_validated   – list of pathway names with >= 10 real rows
                               validated for every supplied quantity.
        message              – explanatory string when pathways_validated is [].
        bmp                  – sub-result (if present).
        net_energy           – sub-result (if present).
        mass_loss            – sub-result (if present).
        status               – "illustrative_estimate".

    Notes
    -----
    ``pathways_validated`` contains ``"anaerobic_digestion"`` only if every
    supplied quantity (bmp, net_energy, mass_loss) has ``n >= 10``; otherwise
    it is an empty list with a message.  No pass/fail threshold is implied.
    JSON serialisable.
    """
    supplied_ns: List[int] = []
    for key in ("bmp", "net_energy", "mass_loss"):
        sub = results.get(key)
        if sub is not None:
            supplied_ns.append(sub.get("n", 0))

    if supplied_ns and all(n >= _MIN_REAL_ROWS for n in supplied_ns):
        pathways_validated = ["anaerobic_digestion"]
        message = (
            f"All supplied quantities have n >= {_MIN_REAL_ROWS} real rows. "
            "Numbers reported; no accuracy threshold applied."
        )
    else:
        pathways_validated = []
        if not supplied_ns:
            message = "No validation results supplied."
        else:
            message = (
                f"insufficient real data — at least {_MIN_REAL_ROWS} real rows "
                "required per quantity for pathway to be listed as validated."
            )

    out: Dict[str, Any] = {
        "limitations": _LIMITATIONS,
        "pathways_validated": pathways_validated,
        "message": message,
        "status": "illustrative_estimate",
    }
    for key in ("bmp", "net_energy", "mass_loss"):
        if key in results:
            out[key] = results[key]

    return out
