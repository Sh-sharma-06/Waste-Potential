"""Shared Pydantic schemas used across all API modules.

All request/response models should inherit from BaseSchema so that unknown
fields are rejected project-wide.
"""

from pydantic import BaseModel, ConfigDict, Field


class BaseSchema(BaseModel):
    """Base schema forbidding extra/unknown fields."""
    model_config = ConfigDict(extra="forbid")


class _Base(BaseSchema):
    """Compatibility alias for the platform's existing base schema."""
    pass


class ErrorBody(BaseSchema):
    """Standard error response body: {"detail": str}."""
    detail: str = Field(..., description="Human-readable error message.")
