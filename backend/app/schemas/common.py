"""
common.py — Shared Pydantic v2 base model for all schema modules.

NOTE: This file is owned by Part B5 (Platform). It is defined here as a
minimal placeholder so B1 schemas can import from it now. B5 should replace
or extend _Base when building the full platform layer.
"""

from pydantic import BaseModel, ConfigDict


class _Base(BaseModel):
    """Shared base: rejects extra fields by default."""
    model_config = ConfigDict(extra="forbid")
