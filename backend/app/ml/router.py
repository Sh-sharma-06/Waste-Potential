"""FastAPI routes for the trained yield model: POST /ml/yield and GET /ml/models.

There is no fallback: with no trained bundle, /ml/yield returns 503 and never a number.
"""

import math
import numbers

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.core_engine.params import Params
from app.ml.registry.store import ModelBundle, NoTrainedModelError, load_bundle
from app.ml.yield_model.ceiling import ceiling_with_lignin
from app.ml.yield_model.feedstocks import (
    FEEDSTOCK_NAMES,
    MissingFeedstockError,
    UnknownFeedstockError,
    normalise_feedstock,
)
from app.ml.yield_model.predict import estimate
from app.ml.yield_model.units import ch4_to_biogas, convert_to_vs_yield
from app.schemas.common import ErrorBody
from app.schemas.ml_yield import (
    GAS_BASIS,
    CeilingCheck,
    MlModelInfo,
    MlModelsResponse,
    MlYieldRequest,
    MlYieldResponse,
)

router = APIRouter(prefix="/ml", tags=["ML"])

NO_MODEL_DETAIL = (
    "No trained model: /ml/yield is off until a yield model has been trained on real data."
)


def _is_finite_number(value) -> bool:
    return (
        isinstance(value, numbers.Real)
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _describe(bundle: ModelBundle) -> MlModelInfo:
    return MlModelInfo(
        model_version=str(bundle.model_version),
        synthetic=bool(bundle.synthetic),
        feedstocks_seen=[str(f) for f in bundle.feedstocks_seen],
        training_data_hash=str(bundle.training_data_hash),
        metrics={k: float(v) for k, v in bundle.metrics.items() if _is_finite_number(v)},
        metadata={
            k: v
            for k, v in bundle.metadata.items()
            if isinstance(v, (str, bool)) or _is_finite_number(v)
        },
    )


@router.post(
    "/yield",
    response_model=MlYieldResponse,
    response_model_exclude_none=True,
    responses={
        422: {"model": ErrorBody, "description": "Unknown feedstock or invalid composition."},
        503: {"model": ErrorBody, "description": "No trained model."},
    },
)
def predict_yield(req: MlYieldRequest):
    # 1. Feedstock label (single source of truth: feedstocks.FEEDSTOCK_NAMES).
    try:
        feedstock = normalise_feedstock(req.feedstock)
    except MissingFeedstockError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if feedstock not in FEEDSTOCK_NAMES:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown feedstock '{req.feedstock}'. Supported: {', '.join(FEEDSTOCK_NAMES)}",
        )

    # 2. Optional composition (all-or-nothing); the ceiling is a METHANE bound per kg VS.
    ceiling = None
    shares = (req.carb, req.protein, req.lipid)
    if any(v is not None for v in shares):
        if any(v is None for v in shares):
            raise HTTPException(
                status_code=422,
                detail="Composition needs carb, protein and lipid together (lignin is optional).",
            )
        try:
            ceiling = ceiling_with_lignin(req.carb, req.protein, req.lipid, req.lignin or 0.0)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    elif req.lignin is not None:
        raise HTTPException(
            status_code=422, detail="lignin was given without carb, protein and lipid."
        )

    # 3. Methane fraction: request value, else the engine's own default (never hardcoded here).
    if req.ch4_fraction is None:
        frac = Params().ch4_fraction
        source = "default_illustrative"
    else:
        frac = req.ch4_fraction
        source = "request"

    # 4. Bundle. Returned directly, not raised: app.errors replaces the detail of
    #    every raised 5xx HTTPException with a generic message.
    try:
        bundle = load_bundle()
    except NoTrainedModelError:
        return JSONResponse(status_code=503, content={"detail": NO_MODEL_DETAIL})

    # 5. Prediction.
    operating = {
        "hrt_days": req.hrt_days,
        "temperature_c": req.temperature_c,
        "olr": req.olr,
        "c_n": req.c_n,
    }
    try:
        est = estimate(feedstock, operating, bundle=bundle, ch4_fraction=frac)
    except (MissingFeedstockError, UnknownFeedstockError) as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    # 6. Conversion happens only in units.py. The bundle currently predicts biogas
    #    (see predict.py); if it is retrained on methane, change gas_type to "ch4".
    conv = convert_to_vs_yield(
        est.y_biogas_nm3_per_kg_vs, "per_kg_vs", ch4_fraction=frac, gas_type="biogas"
    )
    y_ch4 = conv.y_ch4_nm3_per_kg_vs
    y_biogas = conv.y_biogas_nm3_per_kg_vs

    warnings = []
    if source == "default_illustrative":
        warnings.append(
            f"ch4_fraction not supplied: used the illustrative default {frac} from Params(). "
            "Pass ch4_fraction to match your run."
        )
    if bundle.synthetic:
        warnings.append("This model was trained on SYNTHETIC data and is not for decisions.")
    if est.extrapolation_flag:
        warnings.append(
            "extrapolation_flag is set: the kinetic baseline was used instead of the ML "
            "residual, and the interval is widened."
        )

    # 7. Ceiling check (methane basis, before biogas conversion). Only with a composition.
    ceiling_check = None
    interval_low = est.interval_low
    if ceiling is not None:
        clipped = y_ch4 > ceiling
        ceiling_check = CeilingCheck(
            ceiling_ch4_nm3_per_kg_vs=ceiling,
            y_ch4_before_clip_nm3_per_kg_vs=y_ch4,
            clipped=clipped,
        )
        if clipped:
            y_ch4 = ceiling
            y_biogas = ch4_to_biogas(y_ch4, frac)
            interval_low = min(interval_low, y_biogas)
            warnings.append(
                "Predicted methane exceeded the Buswell ceiling for the supplied "
                "composition and was clipped to it."
            )

    return MlYieldResponse(
        y_biogas_nm3_per_kg_vs=y_biogas,
        y_kinetic_nm3_per_kg_vs=est.y_kinetic_nm3_per_kg_vs,
        interval_low=interval_low,
        interval_high=est.interval_high,
        extrapolation_flag=est.extrapolation_flag,
        model_version=est.model_version,
        basis=est.basis,
        y_ch4_nm3_per_kg_vs=y_ch4,
        ch4_fraction_used=frac,
        ch4_fraction_source=source,
        gas_basis=GAS_BASIS,
        warnings=warnings,
        ceiling_check=ceiling_check,
    )


@router.get("/models", response_model=MlModelsResponse, response_model_exclude_none=True)
def list_models():
    try:
        bundle = load_bundle()
    except NoTrainedModelError:
        return MlModelsResponse(status="no_trained_model", models=[], detail=NO_MODEL_DETAIL)
    return MlModelsResponse(status="ok", models=[_describe(bundle)])