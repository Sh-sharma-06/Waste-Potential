"""Tests for GET /catalog/{process_id} (app/pathways/router.py + catalog_loader.py).

Covers:
  - 404 for an unknown process_id.
  - Default scaling: waste_kg=1000 → multiplier 1.0 (inputs unchanged).
  - Custom scaling: waste_kg=500 → multiplier 0.5 (numeric inputs halved).
  - Custom scaling: waste_kg=2000 → multiplier 2.0 (numeric inputs doubled).
  - Null and string input values are left untouched regardless of scaling.
  - scale_inputs() unit tests (no HTTP layer).
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.pathways.router import router
from app.pathways.catalog_loader import scale_inputs

URL = "/pathways/catalog"


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client():
    return TestClient(_app())


# ---------------------------------------------------------------------------
# 1. 404 for unknown process
# ---------------------------------------------------------------------------

def test_unknown_process_returns_404(client):
    resp = client.get(f"{URL}/nonexistent_process")
    assert resp.status_code == 404
    assert "nonexistent_process" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 2. Default scaling (waste_kg=1000 → multiplier 1.0, inputs unchanged)
# ---------------------------------------------------------------------------

def test_default_scaling_no_change(client):
    resp = client.get(f"{URL}/anaerobic_digestion")
    assert resp.status_code == 200
    data = resp.json()

    # At 1000 kg the inputs should be the same as in the catalog.
    assert data["inputs"]["organic_waste_kg"] == pytest.approx(1000.0)
    assert data["inputs"]["water_kg"] == pytest.approx(200.0)
    assert data["inputs"]["electricity_kwh"] == pytest.approx(50.0)


def test_default_scaling_explicit_1000(client):
    resp = client.get(f"{URL}/anaerobic_digestion?waste_kg=1000")
    assert resp.status_code == 200
    data = resp.json()
    assert data["inputs"]["organic_waste_kg"] == pytest.approx(1000.0)


# ---------------------------------------------------------------------------
# 3. Custom scaling: waste_kg=500 → multiplier 0.5
# ---------------------------------------------------------------------------

def test_half_scale_halves_numeric_inputs(client):
    resp = client.get(f"{URL}/anaerobic_digestion?waste_kg=500")
    assert resp.status_code == 200
    data = resp.json()

    assert data["inputs"]["organic_waste_kg"] == pytest.approx(500.0)
    assert data["inputs"]["water_kg"] == pytest.approx(100.0)
    assert data["inputs"]["electricity_kwh"] == pytest.approx(25.0)


# ---------------------------------------------------------------------------
# 4. Custom scaling: waste_kg=2000 → multiplier 2.0
# ---------------------------------------------------------------------------

def test_double_scale_doubles_numeric_inputs(client):
    resp = client.get(f"{URL}/pyrolysis?waste_kg=2000")
    assert resp.status_code == 200
    data = resp.json()

    assert data["inputs"]["dry_waste_kg"] == pytest.approx(2000.0)
    assert data["inputs"]["electricity_kwh"] == pytest.approx(160.0)
    assert data["inputs"]["heat_kwh"] == pytest.approx(240.0)


# ---------------------------------------------------------------------------
# 5. Non-numeric inputs (null, string) are untouched
# ---------------------------------------------------------------------------

def test_null_input_value_untouched(client):
    # anaerobic_digestion has inoculum_kg: null
    resp = client.get(f"{URL}/anaerobic_digestion?waste_kg=500")
    assert resp.status_code == 200
    assert resp.json()["inputs"]["inoculum_kg"] is None


def test_string_input_value_untouched(client):
    # pyrolysis has catalyst_label: "none" (a string)
    resp = client.get(f"{URL}/pyrolysis?waste_kg=500")
    assert resp.status_code == 200
    assert resp.json()["inputs"]["catalyst_label"] == "none"


# ---------------------------------------------------------------------------
# 6. Non-input fields are not scaled
# ---------------------------------------------------------------------------

def test_non_input_fields_not_scaled(client):
    resp = client.get(f"{URL}/composting?waste_kg=500")
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Composting"
    assert data["category"] == "biological"
    # outputs are NOT scaled
    assert data["outputs"]["compost_kg"] == pytest.approx(400.0)


# ---------------------------------------------------------------------------
# 7. scale_inputs() unit tests (no HTTP layer)
# ---------------------------------------------------------------------------

_SAMPLE = {
    "name": "Test Process",
    "category": "test",
    "inputs": {
        "waste_kg": 1000.0,
        "water_kg": 200,
        "tag": "raw",
        "optional": None,
    },
    "outputs": {"product_kg": 800.0},
}


def test_scale_inputs_multiplier_one():
    result = scale_inputs(_SAMPLE, 1000.0)
    assert result["inputs"]["waste_kg"] == pytest.approx(1000.0)
    assert result["inputs"]["water_kg"] == pytest.approx(200.0)


def test_scale_inputs_half():
    result = scale_inputs(_SAMPLE, 500.0)
    assert result["inputs"]["waste_kg"] == pytest.approx(500.0)
    assert result["inputs"]["water_kg"] == pytest.approx(100.0)


def test_scale_inputs_double():
    result = scale_inputs(_SAMPLE, 2000.0)
    assert result["inputs"]["waste_kg"] == pytest.approx(2000.0)
    assert result["inputs"]["water_kg"] == pytest.approx(400.0)


def test_scale_inputs_leaves_string_untouched():
    result = scale_inputs(_SAMPLE, 500.0)
    assert result["inputs"]["tag"] == "raw"


def test_scale_inputs_leaves_null_untouched():
    result = scale_inputs(_SAMPLE, 500.0)
    assert result["inputs"]["optional"] is None


def test_scale_inputs_does_not_mutate_original():
    original_val = _SAMPLE["inputs"]["waste_kg"]
    scale_inputs(_SAMPLE, 500.0)
    assert _SAMPLE["inputs"]["waste_kg"] == original_val


def test_scale_inputs_does_not_scale_outputs():
    result = scale_inputs(_SAMPLE, 500.0)
    assert result["outputs"]["product_kg"] == pytest.approx(800.0)


def test_scale_inputs_no_inputs_key():
    process = {"name": "Empty", "category": "test"}
    result = scale_inputs(process, 500.0)
    assert result["inputs"] == {}
