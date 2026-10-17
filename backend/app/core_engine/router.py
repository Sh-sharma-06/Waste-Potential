"""core_engine APIRouter — simulation parameters, uncertainty, and validation summary.

Mounted by P5 at /api/v1 (no prefix here).

Endpoints
---------
GET  /parameters                            List registry entries, optional status filter.
POST /simulations/{run_id}/uncertainty      Monte Carlo over a stored run's Params.
GET  /validation/summary                    Counts by status + limitations list.
"""
from __future__ import annotations

import dataclasses
from typing import Any, Dict, List, Optional, Protocol

from fastapi import APIRouter, Depends, HTTPException

from app.schemas.simulation import (
    ParameterEntryModel,
    UncertaintyRequest,
    UncertaintyResult,
    _SensitivityItem,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Run-store Protocol + dependency
# ---------------------------------------------------------------------------

class RunReader(Protocol):
    """Read-only access to stored simulation runs."""

    def get(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Return the run dict for *run_id*, or None if not found."""
        ...


class _InMemoryRunReader:
    """Fallback in-memory store — populated by tests via module-level dict."""

    def get(self, run_id: str) -> Optional[Dict[str, Any]]:
        return _IN_MEMORY_RUNS.get(run_id)


# Module-level store used by the in-memory reader (tests write directly here)
_IN_MEMORY_RUNS: Dict[str, Dict[str, Any]] = {}


def get_run_reader() -> RunReader:
    """FastAPI dependency.  Tries app.platform.runs.get_run lazily; falls back to
    an in-memory dict so the router works in tests without any DB setup."""
    try:
        from app.platform.runs import get_run as _platform_get  # type: ignore[import]

        class _PlatformReader:
            def get(self, run_id: str) -> Optional[Dict[str, Any]]:
                return _platform_get(run_id)

        return _PlatformReader()
    except (ImportError, AttributeError):
        return _InMemoryRunReader()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _params_from_run(run: Dict[str, Any]):
    """Rebuild a Params instance from *run["params"]*.

    Converts composition from list → tuple before construction.
    """
    from app.core_engine.params import Params

    raw: Dict[str, Any] = dict(run.get("params", {}))
    comp = raw.get("composition")
    if isinstance(comp, list):
        raw["composition"] = tuple(comp)

    # Only pass recognised Params fields (ignore extra keys from runs)
    valid_fields = {f.name for f in dataclasses.fields(Params)}
    filtered = {k: v for k, v in raw.items() if k in valid_fields}

    return dataclasses.replace(Params(), **filtered)


# ---------------------------------------------------------------------------
# 1. GET /parameters
# ---------------------------------------------------------------------------

@router.get(
    "/parameters",
    response_model=List[ParameterEntryModel],
    summary="List parameter registry entries",
    description=(
        "Returns rows from docs/parameter_registry.csv. "
        "Pass `?status=illustrative_estimate` (or any status string) to filter."
    ),
)
def list_parameters(status: Optional[str] = None) -> List[ParameterEntryModel]:
    from app.core_engine.registry import all_entries

    entries = all_entries()
    if status is not None:
        entries = [e for e in entries if e.status == status]

    return [
        ParameterEntryModel(
            name=e.name,
            value=e.value,
            unit=e.unit,
            mass_basis=e.mass_basis,
            status=e.status,
            source=e.source,
            uncertainty=e.uncertainty,
            model_version=e.model_version,
            description=e.description,
        )
        for e in entries
    ]


# ---------------------------------------------------------------------------
# 2. POST /simulations/{run_id}/uncertainty
# ---------------------------------------------------------------------------

@router.post(
    "/simulations/{run_id}/uncertainty",
    response_model=UncertaintyResult,
    summary="Monte Carlo uncertainty for a stored run",
    description=(
        "Loads the stored run, rebuilds Params from run['params'], "
        "calls run_mc(params, n=..., seed=...) and returns the result. "
        "Returns 404 for an unknown run_id."
    ),
)
def run_uncertainty(
    run_id: str,
    body: UncertaintyRequest,
    reader: RunReader = Depends(get_run_reader),
) -> UncertaintyResult:
    run = reader.get(run_id)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail=f"Run '{run_id}' not found.",
        )

    try:
        params = _params_from_run(run)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Could not rebuild Params from stored run: {exc}",
        )

    from app.core_engine.montecarlo import run_mc

    try:
        mc = run_mc(params, n=body.n, seed=body.seed)
    except (ValueError, TypeError) as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Monte Carlo failed: {exc}",
        )

    return UncertaintyResult(
        n=mc["n"],
        seed=mc["seed"],
        median=mc["median"],
        p2_5=mc["p2_5"],
        p97_5=mc["p97_5"],
        p_net_nonpositive=mc["p_net_nonpositive"],
        runs_with_warnings=mc["runs_with_warnings"],
        sensitivity=[
            _SensitivityItem(
                input=s["input"],
                abs_spearman=s["abs_spearman"],
            )
            for s in mc["sensitivity"]
        ],
        distributions=mc["distributions"],
        assumptions_note=mc["assumptions_note"],
    )


# ---------------------------------------------------------------------------
# 3. GET /validation/summary
# ---------------------------------------------------------------------------

@router.get(
    "/validation/summary",
    summary="Parameter validation summary",
    description=(
        "Returns parameter counts by status, number of unvalidated defaults, "
        "the fixed limitations list, and an empirical-validation placeholder."
    ),
)
def validation_summary() -> Dict[str, Any]:
    from app.core_engine.registry import all_entries, defaults_used
    from app.core_engine.params import Params
    from app.core_engine.validation import _LIMITATIONS

    entries = all_entries()
    by_status: Dict[str, int] = {}
    for e in entries:
        by_status[e.status] = by_status.get(e.status, 0) + 1

    n_unvalidated = len(defaults_used(Params()))

    return {
        "parameter_counts_by_status": by_status,
        "n_unvalidated_defaults": n_unvalidated,
        "limitations": _LIMITATIONS,
        "empirical_validation": "pending",
        "predicted_vs_observed": [],
    }
