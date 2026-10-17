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
# mapped; whole-stream moisture is deliberately NOT mapped to ts_fraction.
STREAM_FIELD_MAP: dict[str, str] = {
    "total_mass_kg_d": "total_mass_kg_d",
    "organic_fraction": "organic_fraction",
}

# P3 values that are known placeholders, not site data.
PLACEHOLDER_STREAM_FIELDS = frozenset({"total_mass_kg_d"})

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


def _location_data(location_id: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Return (params from stream, stream, context) for *location_id*."""
    stream = get_stream(location_id)
    context = get_location_context(location_id)
    values = {
        params_field: stream[stream_field]["value"]
        for stream_field, params_field in STREAM_FIELD_MAP.items()
        if stream_field in stream
    }
    return values, stream, context


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
            "placeholder_fields": sorted(PLACEHOLDER_STREAM_FIELDS & set(stream_values)),
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


def _build_notes(
    sources: dict[str, str], location_notes: Optional[dict[str, Any]]
) -> dict[str, Any]:
    caveats: list[str] = []
    if sources.get(MASS_FIELD) == "location_stream":
        caveats.append(
            f"{MASS_FIELD} comes from the P3 location stream, which is currently "
            "a placeholder default, not measured site data."
        )
    return {
        "orchestrator": {"model_version": ENGINE_MODEL_VERSION, "ml_yield": "not_used"},
        "param_sources": dict(sorted(sources.items())),
        "location": location_notes,
        "caveats": caveats,
    }


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

    inputs = req.model_dump(mode="json")
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
        status=results.status,
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
