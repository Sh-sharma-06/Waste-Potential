"""FastAPI router for platform endpoints.

  POST /simulations     — run the non-ML simulation pipeline and store the run.
  GET  /runs            — stored runs, newest first (``limit`` 1–100, default 20).
  GET  /runs/{run_id}   — one stored run, 404 if unknown.

Other /simulations/... routes (e.g. uncertainty) belong to core_engine (P1).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas.common import ErrorBody
from app.schemas.simulation import SimRequest, SimResponse

from .orchestrator import SimulationInputError, run_simulation
from .runs import RunStore, get_run_store

router = APIRouter(tags=["Platform"])


@router.post(
    "/simulations",
    response_model=SimResponse,
    responses={
        422: {
            "description": (
                "Request validation failed (detail is a list), or the inputs "
                "cannot be simulated (detail is a string): missing waste mass, "
                "invalid or non-finite parameters, unsupported process, or "
                "use_ml_yield=true (ML yield not yet supported)."
            ),
        },
    },
    summary="Run a simulation",
)
def create_simulation(
    request: SimRequest, store: RunStore = Depends(get_run_store)
) -> SimResponse:
    """Identical requests return the same stored run (same id and audit_hash)."""
    try:
        return run_simulation(request, store=store)
    except SimulationInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/runs", response_model=list[SimResponse], summary="List stored runs")
def list_runs(
    limit: int = Query(20, ge=1, le=100, description="Maximum runs to return."),
    store: RunStore = Depends(get_run_store),
) -> list[SimResponse]:
    return store.list(limit=limit)


@router.get(
    "/runs/{run_id}",
    response_model=SimResponse,
    responses={404: {"model": ErrorBody, "description": "Run not found."}},
    summary="Get a stored run",
)
def get_run(run_id: str, store: RunStore = Depends(get_run_store)) -> SimResponse:
    run = store.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"Run {run_id!r} not found")
    return run
