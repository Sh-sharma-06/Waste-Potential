"""Machine Learning and Computer Vision Schemas for Part B2.

All models forbid extra fields per project-wide contract conventions.
All yields are in Nm3 biogas per kg VS.

NOTE FOR P5 (Platform Owner):
When populating backend/app/schemas/common.py:
1. Provide a base model with `model_config = ConfigDict(extra="forbid")`.
2. Provide standard ErrorBody schema: `{"detail": str}`.
3. Once common.py is defined, schemas/ml.py can inherit its base configuration
   from common.py without modifying the public field contracts.
"""

from typing import List, Literal, Optional
from pydantic import BaseModel, ConfigDict, Field


class BaseSchema(BaseModel):
    """Base schema forbidding extra/unknown fields."""
    model_config = ConfigDict(extra="forbid")


class YieldRequest(BaseSchema):
    """Request model for hybrid yield prediction endpoint (/api/ml/yield).

    Operating conditions and feedstock descriptors for yield prediction.
    """
    feedstock: str = Field(
        ...,
        description="Feedstock name (e.g., 'food', 'manure', 'crop', 'mixed').",
        examples=["food"]
    )
    hrt_days: float = Field(
        ...,
        gt=0,
        description="Hydraulic Retention Time in days.",
        examples=[30.0]
    )
    temperature_c: float = Field(
        ...,
        gt=0,
        lt=100,
        description="Operating temperature in degrees Celsius.",
        examples=[37.0]
    )
    olr: float = Field(
        ...,
        gt=0,
        description="Organic Loading Rate in kg VS / (m3 * day).",
        examples=[3.5]
    )
    c_n: float = Field(
        ...,
        gt=0,
        description="Carbon-to-Nitrogen ratio.",
        examples=[25.0]
    )


class YieldEstimate(BaseSchema):
    """Authoritative response model for yield prediction.

    All yields are strictly on a volatile-solids basis (Nm3 biogas per kg VS).
    If inputs extrapolate outside training bounds, extrapolation_flag is set to True,
    and y_biogas_nm3_per_kg_vs falls back to y_kinetic_nm3_per_kg_vs.
    """
    y_biogas_nm3_per_kg_vs: float = Field(
        ...,
        ge=0,
        description="Predicted biogas yield in Nm3 per kg VS (kinetic fallback if extrapolation_flag is True)."
    )
    y_kinetic_nm3_per_kg_vs: float = Field(
        ...,
        ge=0,
        description="L1 Chen-Hashimoto kinetic physics baseline yield in Nm3 per kg VS."
    )
    interval_low: float = Field(
        ...,
        ge=0,
        description="Lower bound of uncertainty interval (Nm3 biogas per kg VS)."
    )
    interval_high: float = Field(
        ...,
        ge=0,
        description="Upper bound of uncertainty interval (Nm3 biogas per kg VS)."
    )
    extrapolation_flag: bool = Field(
        ...,
        description="True if input features fall outside the validated training domain."
    )
    model_version: str = Field(
        ...,
        description="Semantic version or identifier of the yield model used."
    )
    basis: Literal["per kg VS"] = Field(
        default="per kg VS",
        description="Mass basis confirmation; immutable requirement of the platform."
    )


class Detection(BaseSchema):
    """Bounding box detection and class identification for a single waste object."""
    box: List[float] = Field(
        ...,
        min_length=4,
        max_length=4,
        description="Bounding box coordinates [x_min, y_min, x_max, y_max] normalized or in pixels."
    )
    class_name: str = Field(
        ...,
        description="Detected waste classification category (e.g. plastic bottle, metal can, glass, paper)."
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Model confidence score for the detected object."
    )


class DetectResponse(BaseSchema):
    """Response model for waste detection endpoint (/api/vision/detect)."""
    detections: List[Detection] = Field(
        default_factory=list,
        description="List of detected waste items in the analyzed image."
    )
    model_version: str = Field(
        ...,
        description="Identifier or version tag of the YOLO detection weights used."
    )
    timestamp: str = Field(
        ...,
        description="ISO 8601 timestamp of when inference was executed."
    )
