"""test_e2e_smoke.py — Single end-to-end smoke test exercising all major endpoints.

Flow mirrors a real user journey:
  1. GET /geocode          — convert a pincode to lat/lng (Nominatim mocked)
  2. GET /weather          — fetch ambient conditions at those coords (Open-Meteo mocked)
  3. POST /simulations     — run the AD simulation, assert golden values
  4. POST /simulations/{run_id}/uncertainty — assert MC output shape
  5. POST /pathways/compare — assert 7 pathways, optimality shares, outputs structure
  6. GET /pathways/catalog/anaerobic_digestion?waste_kg=1000 — assert dilution_water_kg
  7. GET /buyers           — assert distance_km present, no price field (Places+ORS mocked)

Error paths tested inline:
  - /geocode bad pincode → 422 with {"detail": ...}
  - /geocode timeout → 503 with {"detail": ...}
  - /weather missing param → 422 with {"detail": ...}
  - /buyers unknown product → 422 with {"detail": ...}

NOTE on primary_product / energy_basis
---------------------------------------
The task specification says "every pathway has primary_product and energy_basis".
These keys are present in the output of ``physics_inputs()`` (adapter layer) but
are NOT propagated into ``PathwayResult`` or ``PathwayResult.outputs`` by
``compare.py``.  To assert them through POST /pathways/compare, ``compare.py``
would need to copy those keys into PathwayResult.outputs — which is an app-code
change outside the HARD LIMIT of this task (create only this test file).
Instead this test verifies that every PathwayResult has an ``outputs`` dict
(confirming the physics engine ran) and that every result has the
``model_status`` field (which is fed from the physics engine status).
The ``primary_product`` / ``energy_basis`` assertion is therefore tested via
``physics_inputs()`` directly (unit-style) in ``test_compare_outputs_carry_physics_keys``.

All external HTTP calls are patched — no network required.
"""

from __future__ import annotations

import io
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.config import Settings
from app.platform import runs as _runs_module

# ---------------------------------------------------------------------------
# Shared test application — one app, shared run store for the whole module
# ---------------------------------------------------------------------------

_SETTINGS = Settings(environment="test")


@pytest.fixture(scope="module")
def shared_store():
    """Install a real RunStore as the process-wide store (mirrors test_main.py)."""
    store = _runs_module.RunStore()
    # Patch the module-level _store so both /simulations (platform router, which
    # uses Depends(get_run_store)) and /simulations/{id}/uncertainty (core_engine
    # router, which calls app.platform.runs.get_run → get_run_store()) see the
    # same store.
    original = _runs_module._store
    _runs_module._store = store
    yield store
    _runs_module._store = original


@pytest.fixture(scope="module")
def e2e(shared_store):
    """A TestClient bound to the full app; dependency override mirrors shared_store."""
    from app.platform.runs import get_run_store
    app = create_app(_SETTINGS)
    app.dependency_overrides[get_run_store] = lambda: shared_store
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def _httpx_ok(body) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json.return_value = body
    resp.raise_for_status.return_value = None
    return resp


def _httpx_err(status: int) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.json.return_value = {"error": "upstream error"}
    resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        message=f"HTTP {status}", request=MagicMock(), response=resp
    )
    return resp


_NOMINATIM_HIT = [
    {
        "lat": "28.6139",
        "lon": "77.2090",
        "display_name": "New Delhi, Delhi, India",
    }
]

_OPEN_METEO_HIT = {
    "latitude": 28.6139,
    "longitude": 77.2090,
    "hourly": {
        "temperature_2m": [32.5],
        "relative_humidity_2m": [60.0],
    },
}

_PLACES_BUYER_HIT = {
    "places": [
        {
            "id": "buyer_place_001",
            "displayName": {"text": "Delhi Industrial Estate"},
            "formattedAddress": "123 Main Road, Delhi",
            "location": {"latitude": 28.64, "longitude": 77.22},
            "types": ["industrial_estate"],
        }
    ]
}

# ---------------------------------------------------------------------------
# Geocode cache and rate-limit reset between relevant tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_geocode_state():
    import app.services.geocode_client as _gc
    _gc._cache._store.clear()
    _gc._last_call_time = 0.0
    yield
    _gc._cache._store.clear()
    _gc._last_call_time = 0.0


# ===========================================================================
# THE SMOKE TEST
# ===========================================================================

class TestE2ESmoke:
    """Single end-to-end journey: geocode → weather → simulate → uncertainty →
    compare → catalog → buyers, with all external services mocked."""

    # -----------------------------------------------------------------------
    # Step 1 — GET /geocode
    # -----------------------------------------------------------------------

    def test_step1_geocode_200(self, e2e):
        with patch("app.services.geocode_client.httpx.get",
                   return_value=_httpx_ok(_NOMINATIM_HIT)):
            resp = e2e.get("/geocode", params={"pincode": "110001", "country": "India"})

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert isinstance(data["lat"], float)
        assert isinstance(data["lng"], float)
        assert abs(data["lat"] - 28.6139) < 1e-4
        assert abs(data["lng"] - 77.2090) < 1e-4
        assert data["display_name"] == "New Delhi, Delhi, India"
        assert data["precision"] == "postal-code area centroid, approximate"
        assert data["source"] == "OpenStreetMap Nominatim (ODbL)"
        assert isinstance(data["cached"], bool)

    def test_step1_geocode_error_returns_detail(self, e2e):
        """422 for a bad Indian pincode → {"detail": ...}."""
        resp = e2e.get("/geocode", params={"pincode": "12345", "country": "India"})
        assert resp.status_code == 422
        body = resp.json()
        assert "detail" in body

    def test_step1_geocode_timeout_returns_503_with_detail(self, e2e):
        with patch("app.services.geocode_client.httpx.get",
                   side_effect=httpx.TimeoutException("timed out")):
            resp = e2e.get("/geocode", params={"pincode": "110001", "country": "India"})
        assert resp.status_code == 503
        body = resp.json()
        assert "detail" in body
        assert isinstance(body["detail"], str)

    # -----------------------------------------------------------------------
    # Step 2 — GET /weather at the geocoded coordinates
    # -----------------------------------------------------------------------

    def test_step2_weather_200(self, e2e):
        with patch("app.services.weather_client.httpx.get",
                   return_value=_httpx_ok(_OPEN_METEO_HIT)):
            resp = e2e.get("/weather", params={"lat": 28.6139, "lon": 77.2090})

        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert "ambient_temp_c" in data
        assert "relative_humidity" in data
        assert isinstance(data["ambient_temp_c"], float)
        assert 0.0 <= data["relative_humidity"] <= 1.0

    def test_step2_weather_missing_param_returns_422_with_detail(self, e2e):
        """Missing required query param → FastAPI 422 → {"detail": [...]}."""
        resp = e2e.get("/weather", params={"lat": 28.6139})  # missing lon
        assert resp.status_code == 422
        body = resp.json()
        assert "detail" in body

    # -----------------------------------------------------------------------
    # Step 3 — POST /simulations (golden values from the task spec)
    # -----------------------------------------------------------------------

    def test_step3_simulation_golden(self, e2e):
        payload = {
            "waste_mass_kg_day": 1000,
            "organic_fraction": 0.45,
            "suitable_fraction": 0.80,
        }
        resp = e2e.post("/simulations", json=payload)
        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert "id" in data
        results = data["results"]

        # Golden values from the task spec: within 1e-3
        assert abs(results["e_net_kwh_d"] - 76.7406) < 1e-3, (
            f"e_net_kwh_d {results['e_net_kwh_d']!r} != 76.7406"
        )
        assert abs(results["biogas_nm3_d"] - 47.0448) < 1e-3, (
            f"biogas_nm3_d {results['biogas_nm3_d']!r} != 47.0448"
        )
        assert data["status"] == "illustrative_estimate"

        # Stash the run_id for subsequent steps (module-level side effect via fixture)
        TestE2ESmoke._run_id = data["id"]

    # -----------------------------------------------------------------------
    # Step 4 — POST /simulations/{run_id}/uncertainty
    # -----------------------------------------------------------------------

    def test_step4_uncertainty(self, e2e):
        run_id = getattr(TestE2ESmoke, "_run_id", None)
        if run_id is None:
            pytest.skip("Step 3 did not store a run_id")

        resp = e2e.post(f"/simulations/{run_id}/uncertainty", json={})
        assert resp.status_code == 200, resp.text
        data = resp.json()

        assert "median" in data, "uncertainty response missing 'median'"
        assert "centred_on" in data, "uncertainty response missing 'centred_on'"

        # median between 60 and 90 kWh/d
        assert 60.0 <= data["median"] <= 90.0, (
            f"median {data['median']!r} not in [60, 90]"
        )

    def test_step4_uncertainty_unknown_run_returns_404_with_detail(self, e2e):
        resp = e2e.post("/simulations/definitely-unknown-run-id/uncertainty", json={})
        assert resp.status_code == 404
        body = resp.json()
        assert "detail" in body

    # -----------------------------------------------------------------------
    # Step 5 — POST /pathways/compare
    # -----------------------------------------------------------------------

    _ALL_7 = [
        "anaerobic_digestion", "composting", "incineration",
        "gasification", "pyrolysis", "htc", "torrefaction",
    ]

    def test_step5_compare_7_pathways(self, e2e):
        payload = {
            "farm_id": "smoke_farm",
            "waste_tpd": 10.0,
            "pathways": self._ALL_7,
            "mc_runs": 10,
        }
        resp = e2e.post("/pathways/compare", json=payload)
        assert resp.status_code == 200, resp.text
        results = resp.json()

        assert len(results) == 7, f"Expected 7 pathways, got {len(results)}"

        # Check required keys on every result
        for r in results:
            assert "pathway" in r
            assert "feasible" in r
            assert "outputs" in r
            assert isinstance(r["outputs"], dict)
            assert "status" in r
            assert r["status"] in {"feasible", "rejected", "uncertain"}

        # Optimality shares must sum to ~1.0 over feasible pathways
        feasible_results = [r for r in results if r["feasible"]]
        if feasible_results:
            opt_shares = [
                r["optimality_share"]
                for r in feasible_results
                if r["optimality_share"] is not None
            ]
            if opt_shares:
                total = sum(opt_shares)
                assert abs(total - 1.0) < 0.01, (
                    f"Optimality shares over feasible pathways sum to {total:.4f}, expected ~1.0"
                )

        # Every result must have a 'model_status' key (physics engine status)
        # primary_product and energy_basis are available from physics_inputs()
        # but are not propagated into PathwayResult by compare.py;
        # they are verified separately in test_compare_outputs_carry_physics_keys.
        for r in results:
            assert "model_status" in r, (
                f"Pathway {r['pathway']!r} missing 'model_status'"
            )

    def test_step5_compare_outputs_carry_physics_keys(self):
        """primary_product and energy_basis are present in physics_inputs() for every pathway.

        These keys come from the adapter layer (adapter.py) and are the source
        that compare.py reads when building PathwayResult.  They are present in
        the raw physics dict, confirming the engine ran correctly.
        """
        from app.core_engine.pathways.adapter import physics_inputs

        # Use a representative stream similar to the simulation golden values
        stream = {
            "total_mass_kg_d": 10_000.0,
            "organic_fraction": 0.45,
            "plastic_fraction": 0.20,
            "paper_fraction": 0.15,
            "other_fraction": 0.20,
            "moisture_fraction": 0.73,
            "ash_fraction_dry": 0.10,
            "lhv_dry_mj_per_kg": 14.0,
            "contamination_pct": 5.0,
        }
        phys = physics_inputs(stream)

        all_7 = [
            "anaerobic_digestion", "composting", "incineration",
            "gasification", "pyrolysis", "htc", "torrefaction",
        ]
        for pw in all_7:
            assert pw in phys, f"pathway {pw!r} missing from physics_inputs output"
            assert "primary_product" in phys[pw], (
                f"pathway {pw!r} missing 'primary_product'"
            )
            assert "energy_basis" in phys[pw], (
                f"pathway {pw!r} missing 'energy_basis'"
            )

    # -----------------------------------------------------------------------
    # Step 6 — GET /pathways/catalog/anaerobic_digestion?waste_kg=1000
    # -----------------------------------------------------------------------

    def test_step6_catalog_anaerobic_digestion(self, e2e):
        resp = e2e.get("/pathways/catalog/anaerobic_digestion", params={"waste_kg": 1000})
        assert resp.status_code == 200, resp.text
        data = resp.json()

        # At waste_kg=1000 the multiplier is 1.0 — inputs unchanged
        assert "inputs" in data
        inputs = data["inputs"]
        assert "dilution_water_kg" in inputs, (
            "Expected 'dilution_water_kg' in catalog inputs for anaerobic_digestion"
        )
        assert inputs["dilution_water_kg"] == pytest.approx(1700.0), (
            f"dilution_water_kg = {inputs['dilution_water_kg']!r}, expected 1700.0"
        )

    def test_step6_catalog_unknown_process_returns_404_with_detail(self, e2e):
        resp = e2e.get("/pathways/catalog/no_such_process")
        assert resp.status_code == 404
        body = resp.json()
        assert "detail" in body

    # -----------------------------------------------------------------------
    # Step 7 — GET /buyers
    # -----------------------------------------------------------------------

    def test_step7_buyers_distance_km_present_no_price(self, e2e, monkeypatch):
        """Every buyer result must have distance_km; no price-related field allowed."""
        monkeypatch.setattr("app.data.buyers.GOOGLE_PLACES_API_KEY", "test-api-key")
        price_fields = {"price", "tariff", "rate", "cost_per_unit", "unit_price"}
        with patch("app.data.buyers.httpx.post",
                   return_value=_httpx_ok(_PLACES_BUYER_HIT)), \
             patch("app.services.routing_client.httpx.post",
                   return_value=_httpx_ok({
                       "durations": [[0.0]],
                       "distances": [[5000.0]],
                   })):
            resp = e2e.get(
                "/buyers",
                params={
                    "lat": 28.6139,
                    "lng": 77.2090,
                    "product": "electricity",
                    "radius_km": 50.0,
                },
            )

        assert resp.status_code == 200, resp.text
        buyers = resp.json()
        assert isinstance(buyers, list)

        for buyer in buyers:
            assert "distance_km" in buyer, f"Buyer missing 'distance_km': {buyer}"
            for pf in price_fields:
                assert pf not in buyer, (
                    f"Buyer result contains forbidden price field {pf!r}"
                )

    def test_step7_buyers_bad_product_returns_422_with_detail(self, e2e):
        resp = e2e.get(
            "/buyers",
            params={
                "lat": 28.6139,
                "lng": 77.2090,
                "product": "uranium",
                "radius_km": 50.0,
            },
        )
        assert resp.status_code == 422
        body = resp.json()
        assert "detail" in body
        assert isinstance(body["detail"], str)
