"""
FastAPI router for the Waste-Potential pathways screening module.

Exposes one endpoint:

  POST /pathways/compare  — Coarse feasibility screening + MC uncertainty for
                            a list of waste treatment pathways.

Error handling (mirrors decision/router.py conventions):
  Physical or logical rejections → HTTP 422 Unprocessable Entity.
  Unexpected server-side errors  → HTTP 500.

Design decisions:
  - The endpoint runs the deterministic screening pass first, then the Monte
    Carlo pass.  Results are merged before returning so the frontend receives
    a single coherent list.
  - No database access in this layer — all inputs come from the request body.
  - The router does NOT perform LP allocation (that is the optimizer's job).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .compare import evaluate_pathways
from .mc_compare import merge_mc_into_results, run_mc_compare
from .schemas import PathwayCompareRequest, PathwayResult

router = APIRouter(prefix="/pathways", tags=["Pathways Screening"])


@router.post(
    "/compare",
    response_model=list[PathwayResult],
    summary="Screen and compare waste treatment pathways",
    description=(
        "Runs a coarse feasibility screening pass followed by a Monte Carlo "
        "uncertainty analysis for each requested pathway. "
        "Returns one PathwayResult per pathway. "
        "Rejected pathways have feasible=False with populated reasons. "
        "Does NOT perform LP allocation — use POST /decision/optimize for "
        "strict physical allocation."
    ),
)
def compare_pathways(request: PathwayCompareRequest) -> list[PathwayResult]:
    """POST /pathways/compare — pathway screening + MC uncertainty.

    Raises HTTP 422 if:
      - Any per-pathway data triggers a ValueError (e.g. negative capex).
      - An unknown emission factor key is supplied in operator_overrides.

    Raises HTTP 500 for unexpected errors.
    """
    try:
        # 1 — Deterministic screening
        results = evaluate_pathways(
            request,
            region=request.region,
            operator_overrides=request.operator_overrides,
        )

        # 2 — Monte Carlo uncertainty pass
        mc_results = run_mc_compare(
            request,
            region=request.region,
            operator_overrides=request.operator_overrides,
        )

        # 3 — Merge MC stats into PathwayResult objects (warnings + status)
        merged = merge_mc_into_results(results, mc_results)

        return merged

    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected pathway screening error: {exc}",
        ) from exc
