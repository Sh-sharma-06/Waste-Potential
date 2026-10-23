"""Request/response schemas for POST /ml/yield and GET /ml/models.

Additive to schemas/ml.py: YieldRequest and YieldEstimate are left unchanged.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import Field

from app.schemas.common import BaseSchema
from app.schemas.ml import YieldEstimate, YieldRequest

GAS_BASIS = "Nm3 at 0 C, 1 atm, dry, per kg VS"


class MlYieldRequest(YieldRequest):
    """YieldRequest plus optional methane fraction and optional composition."""

    ch4_fraction: Optional[float] = Field(
        default=None,
        gt=0,
        le=1,
        description="Volumetric CH4 fraction in biogas. If absent, the engine default "
        "from Params() is used and reported as 'default_illustrative'.",
    )
    carb: Optional[float] = Field(default=None, ge=0, le=1, description="Carbohydrate share of VS.")
    protein: Optional[float] = Field(default=None, ge=0, le=1, description="Protein share of VS.")
    lipid: Optional[float] = Field(default=None, ge=0, le=1, description="Lipid share of VS.")
    lignin: Optional[float] = Field(
        default=None, ge=0, lt=1, description="Lignin share of VS (contributes zero to the ceiling)."
    )


class CeilingCheck(BaseSchema):
    """Buswell methane ceiling check; only returned when a composition is supplied."""

    ceiling_ch4_nm3_per_kg_vs: float
    y_ch4_before_clip_nm3_per_kg_vs: float
    clipped: bool


class MlYieldResponse(YieldEstimate):
    """YieldEstimate plus methane yield, the fraction used and its source."""

    y_ch4_nm3_per_kg_vs: float = Field(..., ge=0, description="Methane yield, Nm3 CH4 per kg VS.")
    ch4_fraction_used: float
    ch4_fraction_source: Literal["request", "default_illustrative"]
    gas_basis: str = GAS_BASIS
    warnings: List[str] = Field(default_factory=list)
    ceiling_check: Optional[CeilingCheck] = None


class MlModelInfo(BaseSchema):
    model_version: str
    synthetic: bool
    feedstocks_seen: List[str]
    training_data_hash: str
    metrics: Dict[str, float] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MlModelsResponse(BaseSchema):
    status: Literal["ok", "no_trained_model"]
    models: List[MlModelInfo] = Field(default_factory=list)
    detail: Optional[str] = None