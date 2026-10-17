"""Tests for the application entry point (app/main.py)."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import Settings, load_settings
from app.errors import INTERNAL_ERROR_DETAIL
from app.main import app, create_app

AD = "anaerobic_digestion"


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(Settings(environment="test")), raise_server_exceptions=False)


def _routes(application) -> set[tuple[str, str]]:
    # Derived from OpenAPI: included routers are not flattened into app.routes
    # on all FastAPI versions.
    return {
        (method.upper(), path)
        for path, ops in application.openapi()["paths"].items()
        for method in ops
    }


def test_module_app_matches_environment_settings():
    # The module-level app is built from the environment at import time, so
    # compare against a fresh read of it instead of hard-coded defaults.
    expected = load_settings()
    assert isinstance(app, FastAPI)
    assert app.title == expected.app_name

    resp = TestClient(app).get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "environment": expected.environment}


def test_health(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "environment": "test"}


def test_app_name_comes_from_settings():
    assert create_app(Settings(app_name="Custom")).title == "Custom"


def test_expected_routes_are_mounted():
    assert _routes(create_app()) == {
        ("GET", "/health"),
        ("POST", "/pathways/compare"),
        ("POST", "/decision/optimize"),
        ("POST", "/decision/costs"),
        ("POST", "/decision/carbon/package"),
        ("POST", "/decision/marketplace/match"),
        ("POST", "/simulations"),
        ("GET", "/runs"),
        ("GET", "/runs/{run_id}"),
    }


def test_no_duplicated_prefixes():
    paths = create_app().openapi()["paths"]
    assert not [p for p in paths if p.startswith("/decision/decision")]
    assert not [p for p in paths if p.startswith("/pathways/pathways")]


def test_openapi_generates(client):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    assert "/pathways/compare" in resp.json()["paths"]


def _compare_body() -> dict:
    return {"farm_id": "f", "waste_tpd": 10.0, "pathways": [AD], "mc_runs": 10}


def test_router_500_detail_is_sanitized(client):
    with patch(
        "app.pathways.router.evaluate_pathways",
        side_effect=RuntimeError("secret engine state"),
    ):
        resp = client.post("/pathways/compare", json=_compare_body())
    assert resp.status_code == 500
    assert resp.json() == {"detail": INTERNAL_ERROR_DETAIL}


def test_router_422_detail_passes_through(client):
    with patch(
        "app.pathways.router.evaluate_pathways",
        side_effect=ValueError("invalid input"),
    ):
        resp = client.post("/pathways/compare", json=_compare_body())
    assert resp.status_code == 422
    assert resp.json() == {"detail": "invalid input"}


def test_decision_endpoint_reachable_at_single_prefix(client):
    # Empty list is valid input for /decision/costs.
    resp = client.post("/decision/costs", json=[])
    assert resp.status_code == 200
    assert resp.json() == {"coefficients": []}
    assert client.post("/decision/decision/costs", json=[]).status_code == 404


# ---------------------------------------------------------------------------
# Non-finite numbers in rejected input → 422, not 500 (regression)
# ---------------------------------------------------------------------------

# (url, raw JSON body with {v} for the literal, loc of the rejected field, literal)
# Only literals each schema actually rejects are listed: the pathways and
# decision fields have no upper bound, so +Infinity is valid input there.
_SIM = ("/simulations", '{{"waste_mass_kg_day": {v}}}', ["body", "waste_mass_kg_day"])
_PATHWAYS = (
    "/pathways/compare",
    '{{"farm_id": "f", "waste_tpd": {v}, "pathways": ["anaerobic_digestion"]}}',
    ["body", "waste_tpd"],
)
_COSTS = (
    "/decision/costs",
    '[{{"tech_id": "a", "capex": {v}, "opex_annual": 1, "throughput_tonnes_yr": 1}}]',
    ["body", 0, "capex"],
)
NON_FINITE_CASES = [
    (*_SIM, "NaN"), (*_SIM, "Infinity"), (*_SIM, "-Infinity"),
    (*_PATHWAYS, "NaN"), (*_PATHWAYS, "-Infinity"),
    (*_COSTS, "NaN"), (*_COSTS, "-Infinity"),
]


@pytest.mark.parametrize(
    "url, template, loc, literal",
    NON_FINITE_CASES,
    ids=[f"{c[0]}-{c[3]}" for c in NON_FINITE_CASES],
)
def test_non_finite_input_returns_422_through_app(client, caplog, url, template, loc, literal):
    echoed = literal
    with caplog.at_level("ERROR", logger="app.errors"):
        resp = client.post(
            url,
            content=template.format(v=literal).encode(),
            headers={"content-type": "application/json"},
        )
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert isinstance(detail, list)
    errors = [e for e in detail if e["loc"] == loc]
    assert errors and errors[0]["input"] == echoed
    assert INTERNAL_ERROR_DETAIL not in resp.text
    assert not caplog.records


def test_non_finite_simulation_input_saves_no_run():
    from app.platform.runs import RunStore, get_run_store

    store = RunStore()
    application = create_app(Settings(environment="test"))
    application.dependency_overrides[get_run_store] = lambda: store
    resp = TestClient(application, raise_server_exceptions=False).post(
        "/simulations",
        content=b'{"waste_mass_kg_day": NaN}',
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 422
    assert len(store) == 0
