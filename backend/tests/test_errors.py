"""Tests for the project-wide exception handlers (app/errors.py)."""

from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import Field

from app.errors import INTERNAL_ERROR_DETAIL, register_error_handlers
from app.schemas.common import BaseSchema


class _Body(BaseSchema):
    x: int


class _Bounded(BaseSchema):
    amount: float = Field(..., gt=0, le=1e6)
    name: str


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/http/{code}")
    def raise_http(code: int):
        raise HTTPException(status_code=code, detail="secret: db password=hunter2")

    @app.get("/teapot")
    def teapot():
        raise HTTPException(status_code=418, detail="short and stout", headers={"X-Tea": "1"})

    @app.get("/chained")
    def chained():
        try:
            raise RuntimeError("root cause detail")
        except RuntimeError as exc:
            raise HTTPException(status_code=500, detail="wrapped: root cause detail") from exc

    @app.get("/boom")
    def boom():
        raise RuntimeError("secret internal state")

    @app.post("/body")
    def body(payload: _Body):
        return payload

    @app.post("/bounded")
    def bounded(payload: _Bounded):
        return payload

    return TestClient(app, raise_server_exceptions=False)


def _post_raw(client: TestClient, url: str, raw: str):
    return client.post(url, content=raw.encode(), headers={"content-type": "application/json"})


@pytest.mark.parametrize("code", [400, 404, 409, 422])
def test_client_errors_pass_through(client, code):
    resp = client.get(f"/http/{code}")
    assert resp.status_code == code
    assert resp.json() == {"detail": "secret: db password=hunter2"}


def test_client_error_headers_preserved(client):
    resp = client.get("/teapot")
    assert resp.status_code == 418
    assert resp.headers["X-Tea"] == "1"


@pytest.mark.parametrize("code", [500, 502, 503])
def test_server_http_errors_are_sanitized(client, code, caplog):
    with caplog.at_level(logging.ERROR, logger="app.errors"):
        resp = client.get(f"/http/{code}")
    assert resp.status_code == code
    assert resp.json() == {"detail": INTERNAL_ERROR_DETAIL}
    assert "hunter2" in caplog.text  # logged server-side, not returned


def test_server_http_error_logs_traceback_with_chained_cause(client, caplog):
    with caplog.at_level(logging.ERROR, logger="app.errors"):
        resp = client.get("/chained")
    assert resp.status_code == 500
    assert resp.json() == {"detail": INTERNAL_ERROR_DETAIL}
    assert "root cause detail" not in resp.text

    record = next(r for r in caplog.records if r.name == "app.errors")
    assert record.exc_info is not None
    assert isinstance(record.exc_info[1].__cause__, RuntimeError)
    assert "Traceback" in caplog.text
    assert "RuntimeError: root cause detail" in caplog.text
    assert "The above exception was the direct cause" in caplog.text


def test_unhandled_exception_returns_generic_500(client, caplog):
    with caplog.at_level(logging.ERROR, logger="app.errors"):
        resp = client.get("/boom")
    assert resp.status_code == 500
    assert resp.json() == {"detail": INTERNAL_ERROR_DETAIL}
    assert "secret internal state" not in resp.text
    assert "secret internal state" in caplog.text


def test_unknown_route_404(client):
    resp = client.get("/does-not-exist")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Not Found"}


def test_validation_errors_keep_fastapi_default_shape(client):
    resp = client.post("/body", json={"x": "nope", "extra": 1})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert isinstance(detail, list)
    assert {e["type"] for e in detail} == {"int_parsing", "extra_forbidden"}


@pytest.mark.parametrize(
    "body",
    [
        {"x": "nope", "extra": 1},
        {"amount": -5, "name": "a"},
        {"amount": 2e6},
        {},
    ],
    ids=["types-and-extra", "bound", "bound-and-missing", "empty"],
)
def test_finite_validation_body_identical_to_fastapi_default(client, body):
    """Our handler must not change ordinary 422 bodies at all."""
    plain = FastAPI()  # FastAPI's built-in validation handler

    @plain.post("/body")
    def _b(payload: _Body):
        return payload

    @plain.post("/bounded")
    def _bd(payload: _Bounded):
        return payload

    url = "/body" if "x" in body else "/bounded"
    ours = client.post(url, json=body)
    default = TestClient(plain).post(url, json=body)
    assert ours.status_code == default.status_code == 422
    assert ours.json() == default.json()


@pytest.mark.parametrize(
    "literal, echoed",
    [("NaN", "NaN"), ("Infinity", "Infinity"), ("-Infinity", "-Infinity")],
)
def test_non_finite_rejected_input_returns_422(client, caplog, literal, echoed):
    with caplog.at_level(logging.ERROR, logger="app.errors"):
        resp = _post_raw(client, "/bounded", f'{{"amount": {literal}, "name": "a"}}')
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert isinstance(detail, list) and len(detail) == 1
    assert detail[0]["loc"] == ["body", "amount"]
    assert detail[0]["input"] == echoed
    assert detail[0]["type"] in {"greater_than", "less_than_equal", "finite_number"}
    assert not caplog.records  # not routed to the 500 handler


def test_non_finite_nested_in_rejected_input_returns_422(client):
    # Missing "name" → the error's input is the whole body, NaN included.
    resp = _post_raw(client, "/bounded", '{"amount": NaN, "extra": [1, Infinity, {"y": -Infinity}]}')
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    inputs = [e["input"] for e in detail if e["type"] == "missing"]
    assert inputs == [{"amount": "NaN", "extra": [1, "Infinity", {"y": "-Infinity"}]}]


def test_int_field_with_nan_returns_422(client):
    resp = _post_raw(client, "/body", '{"x": NaN}')
    assert resp.status_code == 422
    assert resp.json()["detail"][0]["input"] == "NaN"
