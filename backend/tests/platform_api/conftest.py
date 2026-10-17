"""Shared fixtures for platform tests."""

from __future__ import annotations

import pytest

from app.core_engine.engine import simulate
from app.core_engine.params import Params
from app.schemas.simulation import SimResponse, SimResults

_RESULTS = SimResults(**simulate(Params()))


@pytest.fixture
def make_run():
    """Factory for valid SimResponse runs with a given id."""

    def _make(run_id: str = "run-001", status: str = "illustrative_estimate") -> SimResponse:
        return SimResponse(
            id=run_id,
            inputs={"total_mass_kg_d": 1000.0},
            params={"hrt_days": 30.0},
            results=_RESULTS,
            model_version="v0.1",
            audit_hash="abc123",
            status=status,
            defaults_used_unvalidated=["hrt_days"],
        )

    return _make
