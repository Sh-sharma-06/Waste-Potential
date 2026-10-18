"""
Endpoint-level tests for POST /pathways/compare (app/pathways/router.py).

The router is mounted on a throwaway FastAPI app so these tests do not depend
on app/main.py.  Two kinds of tests:

  - End-to-end: the real screening + MC pipeline runs with a small mc_runs.
    MC sampling is unseeded, so only structural invariants are asserted.
  - Controlled: the pipeline functions imported by the router are patched so
    the router's own wiring and error mapping are tested deterministically.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI

from app.pathways.router import router
from app.pathways.schemas import PathwayResult

URL = "/pathways/compare"
AD = "anaerobic_digestion"

RESULT_KEYS = {
    "pathway",
    "feasible",
    "reasons",
    "outputs",
    "revenue_inr_y",
    "cost_inr_y",
    "annual_net_value_inr",
    "e_net_kwh_d",
    "model_status",
    "status",
    "warnings",
    "optimality_share",
    "win_count",
    "optimality_note",
}
VALID_STATUSES = {"feasible", "rejected", "uncertain"}


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    return TestClient(_app())


def _body(**overrides) -> dict:
    body = {
        "farm_id": "farm_001",
        "waste_tpd": 10.0,
        "pathways": [AD],
        "capex_inr": {AD: 5_000_000.0},
        "opex_inr_yr": {AD: 300_000.0},
        "net_kwh_per_tonne": {AD: 120.0},
        "capacity_tpd": {AD: 20.0},
        "distance_km": 10.0,
        "mc_runs": 10,
    }
    body.update(overrides)
    return body


def _result(pathway: str = AD, **overrides) -> PathwayResult:
    fields = {"pathway": pathway, "feasible": True, "status": "feasible"}
    fields.update(overrides)
    return PathwayResult(**fields)


# ---------------------------------------------------------------------------
# OpenAPI contract (no HTTP client needed)
# ---------------------------------------------------------------------------

def test_openapi_declares_compare_endpoint():
    spec = _app().openapi()
    op = spec["paths"][URL]["post"]

    request_ref = op["requestBody"]["content"]["application/json"]["schema"]["$ref"]
    assert request_ref.endswith("/PathwayCompareRequest")

    ok_schema = op["responses"]["200"]["content"]["application/json"]["schema"]
    assert ok_schema["type"] == "array"
    assert ok_schema["items"]["$ref"].endswith("/PathwayResult")
    assert "422" in op["responses"]


def test_openapi_result_schema_fields():
    spec = _app().openapi()
    props = spec["components"]["schemas"]["PathwayResult"]["properties"]
    assert set(props) == RESULT_KEYS


# ---------------------------------------------------------------------------
# End-to-end success
# ---------------------------------------------------------------------------

def test_single_pathway_success(client):
    resp = client.post(URL, json=_body())
    assert resp.status_code == 200

    data = resp.json()
    assert isinstance(data, list) and len(data) == 1
    row = data[0]
    assert set(row) == RESULT_KEYS
    assert row["pathway"] == AD
    assert row["feasible"] is True
    assert row["status"] in {"feasible", "uncertain"}
    assert row["reasons"] == []
    assert row["annual_net_value_inr"] == pytest.approx(
        row["revenue_inr_y"] - row["cost_inr_y"]
    )
    # MC merge appends its summary to warnings
    assert any(w.startswith("MC (10 runs)") for w in row["warnings"])


def test_multi_pathway_preserves_request_order(client):
    pathways = ["composting", AD]
    body = _body(
        pathways=pathways,
        capex_inr={AD: 4_000_000.0, "composting": 1_500_000.0},
        opex_inr_yr={AD: 250_000.0, "composting": 80_000.0},
        net_kwh_per_tonne={AD: 100.0, "composting": 0.0},
        capacity_tpd={AD: 15.0, "composting": 10.0},
    )
    resp = client.post(URL, json=body)
    assert resp.status_code == 200
    data = resp.json()
    assert [r["pathway"] for r in data] == pathways
    for row in data:
        assert row["status"] in VALID_STATUSES


def test_over_capacity_pathway_is_rejected_with_reasons(client):
    resp = client.post(URL, json=_body(capacity_tpd={AD: 1.0}))
    assert resp.status_code == 200
    row = resp.json()[0]
    assert row["feasible"] is False
    assert row["status"] == "rejected"
    assert row["reasons"]


# ---------------------------------------------------------------------------
# Request validation (Pydantic → 422)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "overrides",
    [
        {"waste_tpd": 0.0},
        {"waste_tpd": -5.0},
        {"pathways": []},
        {"mc_runs": 5},
        {"mc_runs": 20_000},
        {"discount_rate": 0.0},
        {"distance_km": -1.0},
        {"soil_index": 1.5},
    ],
    ids=lambda o: next(iter(o)),
)
def test_invalid_field_values_return_422(client, overrides):
    resp = client.post(URL, json=_body(**overrides))
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert isinstance(detail, list)
    assert detail[0]["loc"][:2] == ["body", next(iter(overrides))]


@pytest.mark.parametrize("missing", ["farm_id", "waste_tpd", "pathways"])
def test_missing_required_field_returns_422(client, missing):
    body = _body()
    del body[missing]
    resp = client.post(URL, json=body)
    assert resp.status_code == 422
    assert any(e["loc"][-1] == missing for e in resp.json()["detail"])


def test_non_json_body_returns_422(client):
    resp = client.post(
        URL, content=b"not json", headers={"content-type": "application/json"}
    )
    assert resp.status_code == 422


@pytest.mark.xfail(
    strict=True,
    reason="PathwayCompareRequest extends BaseModel, not BaseSchema; unknown "
    "fields are currently ignored. Pending approval to migrate.",
)
def test_unknown_field_returns_422(client):
    resp = client.post(URL, json=_body(unexpected_field=1))
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Engine errors (router error mapping)
# ---------------------------------------------------------------------------

def test_engine_value_error_from_real_pipeline_returns_422(client):
    # crf() rejects a non-positive asset life with ValueError
    resp = client.post(URL, json=_body(asset_life_yr={AD: 0}))
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert isinstance(detail, str)
    assert "asset_life" in detail


def test_value_error_maps_to_422_with_string_detail(client):
    with patch(
        "app.pathways.router.evaluate_pathways",
        side_effect=ValueError("invalid input"),
    ):
        resp = client.post(URL, json=_body())
    assert resp.status_code == 422
    assert resp.json() == {"detail": "invalid input"}


def test_unexpected_error_maps_to_500(client):
    with patch(
        "app.pathways.router.run_mc_compare",
        side_effect=RuntimeError("solver exploded"),
    ), patch("app.pathways.router.evaluate_pathways", return_value=[_result()]):
        resp = client.post(URL, json=_body())
    assert resp.status_code == 500
    detail = resp.json()["detail"]
    assert detail.startswith("Unexpected pathway screening error")


# ---------------------------------------------------------------------------
# Router wiring (controlled pipeline)
# ---------------------------------------------------------------------------

def test_router_passes_region_and_overrides_and_returns_merged(client):
    deterministic = [_result()]
    mc = [object()]
    merged = [_result(status="uncertain", warnings=["merged"])]
    overrides = {"grid_kg_per_kwh": 0.5}

    with patch(
        "app.pathways.router.evaluate_pathways", return_value=deterministic
    ) as ev, patch(
        "app.pathways.router.run_mc_compare", return_value=mc
    ) as mc_fn, patch(
        "app.pathways.router.merge_mc_into_results", return_value=merged
    ) as merge:
        resp = client.post(
            URL, json=_body(region="IN", operator_overrides=overrides)
        )

    assert resp.status_code == 200
    assert resp.json() == [r.model_dump() for r in merged]

    (req_ev,), kwargs_ev = ev.call_args
    assert req_ev.farm_id == "farm_001"
    assert kwargs_ev == {"region": "IN", "operator_overrides": overrides}

    (req_mc,), kwargs_mc = mc_fn.call_args
    assert req_mc.farm_id == "farm_001"
    assert kwargs_mc["region"] == "IN"
    assert kwargs_mc["operator_overrides"] == overrides
    # feasible_pathways is now also passed by the router
    assert "feasible_pathways" in kwargs_mc

    merge.assert_called_once_with(deterministic, mc)
