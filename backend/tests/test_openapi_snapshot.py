"""test_openapi_snapshot.py — fail if the live OpenAPI schema differs from the snapshot.

Regenerate with:
    python backend/scripts/dump_openapi.py
    git add docs/openapi.snapshot.json
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]  # backend/tests/ → backend/ → Waste-Potential/
_SNAPSHOT = _REPO / "docs" / "openapi.snapshot.json"

_REGEN_MSG = (
    "OpenAPI schema does not match docs/openapi.snapshot.json — "
    "run python backend/scripts/dump_openapi.py and commit the snapshot"
)


def test_openapi_matches_snapshot():
    from app.main import create_app

    live = create_app().openapi()
    live_text = json.dumps(live, indent=2, sort_keys=True)

    assert _SNAPSHOT.exists(), (
        f"Snapshot not found at {_SNAPSHOT}. Run python backend/scripts/dump_openapi.py"
    )
    snapshot_text = _SNAPSHOT.read_text(encoding="utf-8").rstrip("\n")

    assert live_text == snapshot_text, _REGEN_MSG
