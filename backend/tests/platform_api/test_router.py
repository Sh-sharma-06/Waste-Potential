"""HTTP tests for GET /runs and GET /runs/{run_id} on the real app."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.platform.runs import RunStore, get_run_store


@pytest.fixture
def store() -> RunStore:
    return RunStore()


@pytest.fixture
def client(store):
    app = create_app()
    app.dependency_overrides[get_run_store] = lambda: store
    return TestClient(app)


def test_list_runs_empty(client):
    resp = client.get("/runs")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_runs_newest_first_with_limit(client, store, make_run):
    for rid in ("a", "b", "c"):
        store.save(make_run(rid))
    assert [r["id"] for r in client.get("/runs").json()] == ["c", "b", "a"]
    assert [r["id"] for r in client.get("/runs", params={"limit": 2}).json()] == ["c", "b"]


@pytest.mark.parametrize("limit", [0, 101, "abc"])
def test_list_runs_invalid_limit_returns_422(client, limit):
    resp = client.get("/runs", params={"limit": limit})
    assert resp.status_code == 422


def test_get_run_returns_full_sim_response(client, store, make_run):
    run = store.save(make_run("run-42"))
    resp = client.get("/runs/run-42")
    assert resp.status_code == 200
    assert resp.json() == run.model_dump(mode="json")


def test_get_unknown_run_returns_404_error_body(client):
    resp = client.get("/runs/nope")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Run 'nope' not found"}
