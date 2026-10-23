"""Simulation orchestration: SimRequest → SimResponse (non-ML path).

Pipeline (contract confirmed by P1):
  1. Build Params with dataclasses.replace(Params(), ...), lowest to highest:
       Params() defaults
       → P3 stream data (only when location_id is given)
       → explicit top-level request fields
       → [ML yield — not implemented; use_ml_yield=True is rejected]
       → explicit ``overrides`` (always win)
  2. simulate(params), validated with SimResults.
  3. rule_warnings(...) → warnings_detail; defaults_used(params) →
     defaults_used_unvalidated.
  4. audit_hash over inputs/params/model_version/results; run id = hash[:12].
  5. Save to the run store (identical runs reuse the stored run).

All physics comes from app.core_engine; this module only maps and records.
Input problems raise SimulationInputError (a ValueError), which the router
maps to HTTP 422. Nothing is stored unless the whole pipeline succeeds.
"""

from __future__ import annotations

import dataclasses
import math
from typing import Any, Optional

from app.core_engine import Params, defaults_used, rule_warnings, simulate
from app.data.service import get_location_context, get_stream
from app.schemas.simulation import (
    RuleWarningModel,
    SimRequest,
    SimResponse,
    SimResults,
)

from .audit import compute_audit_hash, run_id_from_hash
from .runs import RunIdCollisionError, RunStore, get_run_store

ENGINE_MODEL_VERSION = "engine-0.2"
SUPPORTED_PROCESS = "anaerobic_digestion"

# Top-level SimRequest field → Params field (confirmed by P1).
REQUEST_FIELD_MAP: dict[str, str] = {
    "waste_mass_kg_day": "total_mass_kg_d",
    "organic_fraction": "organic_fraction",
    "suitable_fraction": "suitable_fraction",
}

# P3 stream field → Params field. Only same-named, same-basis fields are
# mapped; whole-stream moisture_fraction is deliberately NOT mapped.
STREAM_FIELD_MAP: dict[str, str] = {
    "total_mass_kg_d": "total_mass_kg_d",
    "organic_fraction": "organic_fraction",
}

# Derived at stream priority: ts_fraction = 1 − organic_moisture_fraction
# (moisture of the organic component; same relation as P1's pathways adapter).
ORGANIC_MOISTURE_FIELD = "organic_moisture_fraction"
TS_FRACTION_FIELD = "ts_fraction"

# P3 values that are known placeholders, not site data. Besides this fixed
# set, any field whose P3 meta.source_id is in PLACEHOLDER_SOURCE_IDS counts.
PLACEHOLDER_STREAM_FIELDS = frozenset({"total_mass_kg_d"})
PLACEHOLDER_SOURCE_IDS = frozenset({"placeholder_general"})

# Statuses that already say "not empirical"; a run that uses placeholder
# stream data is never reported with any other status.
NON_EMPIRICAL_STATUSES = frozenset({"illustrative_estimate", "extrapolation"})
PLACEHOLDER_STATUS = "illustrative_estimate"

MASS_FIELD = "total_mass_kg_d"
# Matches SimRequest.waste_mass_kg_day's le=1e6 bound (kept in sync by a test).
MAX_MASS_KG_D = 1_000_000.0


class SimulationInputError(ValueError):
    """The request cannot be simulated as given (maps to HTTP 422)."""


def _require_finite(name: str, value: Any) -> None:
    if isinstance(value, (int, float)) and not math.isfinite(value):
        raise SimulationInputError(f"{name} must be a finite number, got {value!r}")


def _check_supported(req: SimRequest) -> None:
    if req.process != SUPPORTED_PROCESS:
        raise SimulationInputError(
            f"process {req.process!r} is not supported; only "
            f"{SUPPORTED_PROCESS!r} can be simulated"
        )
    if req.use_ml_yield:
        raise SimulationInputError(
            "use_ml_yield=true is not supported yet: ML yield integration is "
            "pending (no confirmed feedstock source or trained model). "
            "Omit use_ml_yield, or set y_biogas_nm3_per_kg_vs in overrides."
        )


def _require_unit_fraction(name: str, value: Any) -> float:
    """Return *value* as a float if it is a finite number in [0, 1]."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SimulationInputError(f"{name} must be a number, got {value!r}")
    _require_finite(name, value)
    if not 0.0 <= value <= 1.0:
        raise SimulationInputError(f"{name} must be in [0, 1], got {value!r}")
    return float(value)


def _derived_ts_fraction(stream: dict[str, Any]) -> Optional[float]:
    """ts_fraction from the stream's organic moisture, or None if absent."""
    if ORGANIC_MOISTURE_FIELD not in stream:
        return None
    moisture = _require_unit_fraction(
        f"location stream {ORGANIC_MOISTURE_FIELD}",
        stream[ORGANIC_MOISTURE_FIELD]["value"],
    )
    return _require_unit_fraction(
        f"{TS_FRACTION_FIELD} derived from {ORGANIC_MOISTURE_FIELD}", 1.0 - moisture
    )


def _location_data(location_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Return (params from stream, stream, context) for *location_id*."""
    stream = get_stream(location_id)
    context = get_location_context(location_id)
    values = {
        params_field: stream[stream_field]["value"]
        for stream_field, params_field in STREAM_FIELD_MAP.items()
        if stream_field in stream
    }
    ts_fraction = _derived_ts_fraction(stream)
    if ts_fraction is not None:
        values[TS_FRACTION_FIELD] = ts_fraction
    return values, stream, context


# Params field → the P3 stream field its value came from.
_STREAM_SOURCE_FIELD: dict[str, str] = {
    **{params_field: stream_field for stream_field, params_field in STREAM_FIELD_MAP.items()},
    TS_FRACTION_FIELD: ORGANIC_MOISTURE_FIELD,
}


def _stream_meta(stream: dict[str, Any], params_field: str) -> dict[str, Any]:
    entry = stream.get(_STREAM_SOURCE_FIELD[params_field])
    meta = entry.get("meta") if isinstance(entry, dict) else None
    return dict(meta) if isinstance(meta, dict) else {}


def _placeholder_fields(stream: dict[str, Any], stream_values: dict[str, Any]) -> list[str]:
    """Stream-supplied Params fields that are placeholders, not site data."""
    return sorted(
        field
        for field in stream_values
        if field in PLACEHOLDER_STREAM_FIELDS
        or _stream_meta(stream, field).get("source_id") in PLACEHOLDER_SOURCE_IDS
    )


def _derived_fields(stream: dict[str, Any], stream_values: dict[str, Any]) -> dict[str, Any]:
    """Provenance of Params fields computed from (not copied from) the stream."""
    if TS_FRACTION_FIELD not in stream_values:
        return {}
    return {
        TS_FRACTION_FIELD: {
            "source_field": ORGANIC_MOISTURE_FIELD,
            "formula": f"1 - {ORGANIC_MOISTURE_FIELD}",
            "meta": _stream_meta(stream, TS_FRACTION_FIELD),
        }
    }


def resolve_params(
    req: SimRequest,
) -> tuple[Params, dict[str, str], Optional[dict[str, Any]]]:
    """Apply the confirmed precedence and build the final Params.

    Returns (params, param_sources, location_notes). ``param_sources`` maps
    every Params field that was set from something other than the defaults
    to "location_stream", "request" or "override".
    """
    updates: dict[str, Any] = {}
    sources: dict[str, str] = {}
    location_notes: Optional[dict[str, Any]] = None

    if req.location_id is not None:
        stream_values, stream, context = _location_data(req.location_id)
        updates.update(stream_values)
        sources.update({f: "location_stream" for f in stream_values})
        location_notes = {
            "location_id": req.location_id,
            "stream_fields_applied": sorted(stream_values),
            "placeholder_fields": _placeholder_fields(stream, stream_values),
            "derived_fields": _derived_fields(stream, stream_values),
            "stream": stream,
            "context": context,
        }

    for req_field, params_field in REQUEST_FIELD_MAP.items():
        value = getattr(req, req_field)
        if value is not None:
            updates[params_field] = value
            sources[params_field] = "request"

    for name, value in req.overrides.items():
        updates[name] = value
        sources[name] = "override"

    if MASS_FIELD not in updates:
        raise SimulationInputError(
            "waste mass is required: provide waste_mass_kg_day, a location_id, "
            f"or overrides.{MASS_FIELD}"
        )
    for name, value in updates.items():
        _require_finite(name, value)
    # Same bounds as SimRequest.waste_mass_kg_day (gt=0, le=1e6), which an
    # override of total_mass_kg_d would otherwise bypass.
    if updates[MASS_FIELD] <= 0:
        raise SimulationInputError(
            f"{MASS_FIELD} must be > 0, got {updates[MASS_FIELD]!r} "
            f"(from {sources[MASS_FIELD]})"
        )
    if updates[MASS_FIELD] > MAX_MASS_KG_D:
        raise SimulationInputError(
            f"{MASS_FIELD} must be <= {MAX_MASS_KG_D:g}, got {updates[MASS_FIELD]!r} "
            f"(from {sources[MASS_FIELD]})"
        )

    try:
        params = dataclasses.replace(Params(), **updates)
    except (ValueError, TypeError) as exc:
        raise SimulationInputError(f"invalid simulation parameters: {exc}") from exc
    return params, sources, location_notes


def _placeholders_in_use(
    sources: dict[str, str], location_notes: Optional[dict[str, Any]]
) -> list[str]:
    """Placeholder stream fields whose value survived precedence (not
    replaced by a request field or override)."""
    if not location_notes:
        return []
    return [
        field
        for field in location_notes["placeholder_fields"]
        if sources.get(field) == "location_stream"
    ]


def _response_status(
    results_status: str, sources: dict[str, str], location_notes: Optional[dict[str, Any]]
) -> str:
    """The engine's status, except that a run using placeholder stream data
    is never reported as anything stronger than an illustrative estimate."""
    if _placeholders_in_use(sources, location_notes) and results_status not in NON_EMPIRICAL_STATUSES:
        return PLACEHOLDER_STATUS
    return results_status


def _build_notes(
    sources: dict[str, str], location_notes: Optional[dict[str, Any]]
) -> dict[str, Any]:
    caveats: list[str] = []
    for field in _placeholders_in_use(sources, location_notes):
        if field == TS_FRACTION_FIELD:
            caveats.append(
                f"{TS_FRACTION_FIELD} is derived from the P3 location stream's "
                f"{ORGANIC_MOISTURE_FIELD}, which is currently a placeholder "
                "default, not measured site data."
            )
        else:
            caveats.append(
                f"{field} comes from the P3 location stream, which is currently "
                "a placeholder default, not measured site data."
            )
    return {
        "orchestrator": {"model_version": ENGINE_MODEL_VERSION, "ml_yield": "not_used"},
        "param_sources": dict(sorted(sources.items())),
        "location": location_notes,
        "caveats": caveats,
    }


def _build_provenance(
    sources: dict[str, str],
    location_notes: Optional[dict[str, Any]],
) -> dict[str, Any]:
    """Serialisable provenance blob for every param field that drives status/notes.

    Included in ``inputs["provenance"]`` before hashing so that two runs with
    the same numbers but different provenance (e.g. ts_fraction=0.27 from the
    Params default vs ts_fraction=0.27 derived from organic_moisture_fraction)
    produce distinct audit hashes and are stored as separate runs.

    Keys per field:
        kind        — "estimated" / "measured" / "derived" / "request" / "override"
        source_id   — stream source_id, or empty string when not from a stream
        placeholder — True when the value is a placeholder, not site data
        derived_from — the upstream stream field name when the value is derived,
                       or empty string otherwise

    Only fields recorded in ``sources`` are included; Params defaults that were
    not set by the request or stream are omitted (they carry no provenance).
    """
    placeholder_fields: frozenset = frozenset(
        location_notes["placeholder_fields"] if location_notes else []
    )
    derived: dict[str, Any] = (
        location_notes.get("derived_fields", {}) if location_notes else {}
    )
    stream: dict[str, Any] = location_notes.get("stream", {}) if location_notes else {}

    result: dict[str, Any] = {}
    for field, source in sorted(sources.items()):
        if source == "location_stream":
            # Derive kind and source_id from the stream metadata.
            stream_source_field = _STREAM_SOURCE_FIELD.get(field, field)
            entry = stream.get(stream_source_field)
            meta = entry.get("meta", {}) if isinstance(entry, dict) else {}
            kind = meta.get("kind", "estimated")
            source_id = meta.get("source_id", "")
            derived_from = (
                derived[field]["source_field"] if field in derived else ""
            )
        else:
            kind = source          # "request" or "override"
            source_id = ""
            derived_from = ""

        result[field] = {
            "kind": kind,
            "source_id": source_id,
            "placeholder": field in placeholder_fields,
            "derived_from": derived_from,
        }
    return result


def run_simulation(req: SimRequest, store: Optional[RunStore] = None) -> SimResponse:
    """Run the non-ML simulation pipeline and store the completed run."""
    store = store if store is not None else get_run_store()

    _check_supported(req)
    params, sources, location_notes = resolve_params(req)

    try:
        raw = simulate(params)
    except ValueError as exc:
        raise SimulationInputError(f"simulation rejected the inputs: {exc}") from exc
    results = SimResults(**raw)
    for name, value in results.model_dump().items():
        _require_finite(f"result {name}", value)

    # Build the inputs dict and embed provenance before hashing.
    # inputs["provenance"] distinguishes runs with identical numbers but
    # different origin (e.g. placeholder stream vs measured site data).
    inputs = req.model_dump(mode="json")
    inputs["provenance"] = _build_provenance(sources, location_notes)

    params_dict = dataclasses.asdict(params)
    audit_hash = compute_audit_hash(
        inputs, params_dict, ENGINE_MODEL_VERSION, results.model_dump(mode="json")
    )
    run_id = run_id_from_hash(audit_hash)

    # Fast path for repeats; the authoritative check is save_if_absent below.
    existing = store.get(run_id)
    if existing is not None:
        if existing.audit_hash != audit_hash:
            raise RunIdCollisionError(f"run id {run_id!r} already used by a different run")
        return existing

    response = SimResponse(
        id=run_id,
        inputs=inputs,
        params=params_dict,
        results=results,
        notes=_build_notes(sources, location_notes),
        model_version=ENGINE_MODEL_VERSION,
        audit_hash=audit_hash,
        status=_response_status(results.status, sources, location_notes),
        defaults_used_unvalidated=defaults_used(params),
        warnings_detail=[
            RuleWarningModel(**dataclasses.asdict(w))
            for w in rule_warnings(raw, extrapolation_flag=False)
        ],
    )
    # Atomic: a concurrent identical run wins harmlessly; a colliding id with
    # a different audit hash raises instead of overwriting.
    stored, _created = store.save_if_absent(response)
    return stored
