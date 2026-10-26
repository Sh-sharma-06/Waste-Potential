"""test_simulator.py — Tests for /simulator/recommend and /simulator/process-details.

Verifies:
  1. Missing either KEY_RECOMMEND or KEY_EXPLAIN raises 503.
  2. POST /simulator/recommend uses KEY_RECOMMEND and returns valid JSON {"suggested_process": ...}.
  3. POST /simulator/process-details uses KEY_EXPLAIN and returns Markdown briefing.
  4. Network/GenAI failure propagates as 503.
  5. 422 Unprocessable Entity on invalid request payloads.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers.simulator import router

URL_RECOMMEND = "/simulator/recommend"
URL_DETAILS = "/simulator/process-details"


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client():
    return TestClient(_app())


def test_missing_recommend_key_returns_503(client):
    with patch("app.routers.simulator.KEY_RECOMMEND", ""), \
         patch("app.routers.simulator.KEY_EXPLAIN", "fake-key"):
        resp = client.post(
            URL_RECOMMEND,
            json={
                "location": "Bengaluru",
                "weight": 25.0,
                "weather": "28°C sunny",
                "duration_pref": "fast",
            },
        )
    assert resp.status_code == 503
    assert "missing" in resp.json()["detail"].lower() or "not configured" in resp.json()["detail"].lower()


def test_missing_explain_key_returns_503(client):
    with patch("app.routers.simulator.KEY_RECOMMEND", "fake-key"), \
         patch("app.routers.simulator.KEY_EXPLAIN", ""):
        resp = client.post(
            URL_DETAILS,
            json={
                "location": "Bengaluru",
                "weight": 25.0,
                "target_process": "Gasification",
                "suggested_process": "Pyrolysis",
            },
        )
    assert resp.status_code == 503
    assert "missing" in resp.json()["detail"].lower() or "not configured" in resp.json()["detail"].lower()


def test_recommend_success(client):
    mock_genai_response = MagicMock()
    mock_genai_response.text = json.dumps({"suggested_process": "Pyrolysis"})

    with patch("app.routers.simulator.KEY_RECOMMEND", "test-rec-key"), \
         patch("app.routers.simulator.KEY_EXPLAIN", "test-exp-key"), \
         patch("app.routers.simulator.genai.Client") as mock_client_cls:
        
        mock_client = mock_client_cls.return_value
        mock_client.models.generate_content.return_value = mock_genai_response

        resp = client.post(
            URL_RECOMMEND,
            json={
                "location": "Bengaluru",
                "weight": 50.0,
                "weather": "Tropical, 26°C",
                "duration_pref": "< 24 hours",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["suggested_process"] == "Pyrolysis"
    mock_client_cls.assert_called_with(api_key="test-rec-key")


def test_process_details_success(client):
    mock_genai_response = MagicMock()
    mock_genai_response.text = (
        "## Technical Pros\n- High yield\n\n## Operational Cons\n- High capital cost\n\n"
        "## Comparison with Pyrolysis\n- Higher thermal requirements."
    )

    with patch("app.routers.simulator.KEY_RECOMMEND", "test-rec-key"), \
         patch("app.routers.simulator.KEY_EXPLAIN", "test-exp-key"), \
         patch("app.routers.simulator.genai.Client") as mock_client_cls:
        
        mock_client = mock_client_cls.return_value
        mock_client.models.generate_content.return_value = mock_genai_response

        resp = client.post(
            URL_DETAILS,
            json={
                "location": "Bengaluru",
                "weight": 50.0,
                "target_process": "Gasification",
                "suggested_process": "Pyrolysis",
                "weather": "Sunny, 30°C",
            },
        )

    assert resp.status_code == 200
    data = resp.json()
    assert "## Technical Pros" in data["details"]
    assert data["target_process"] == "Gasification"
    assert data["suggested_process"] == "Pyrolysis"
    mock_client_cls.assert_called_with(api_key="test-exp-key")


def test_recommend_handles_wrapped_markdown_json(client):
    mock_genai_response = MagicMock()
    mock_genai_response.text = '```json\n{"suggested_process": "Anaerobic Digestion"}\n```'

    with patch("app.routers.simulator.KEY_RECOMMEND", "test-rec-key"), \
         patch("app.routers.simulator.KEY_EXPLAIN", "test-exp-key"), \
         patch("app.routers.simulator.genai.Client") as mock_client_cls:
        
        mock_client = mock_client_cls.return_value
        mock_client.models.generate_content.return_value = mock_genai_response

        resp = client.post(
            URL_RECOMMEND,
            json={
                "location": "Pune",
                "weight": 10.0,
                "weather": "Humid",
                "duration_pref": "Standard",
            },
        )

    assert resp.status_code == 200
    assert resp.json()["suggested_process"] == "Anaerobic Digestion"


def test_api_failure_raises_503(client):
    with patch("app.routers.simulator.KEY_RECOMMEND", "test-rec-key"), \
         patch("app.routers.simulator.KEY_EXPLAIN", "test-exp-key"), \
         patch("app.routers.simulator.genai.Client") as mock_client_cls:
        
        mock_client = mock_client_cls.return_value
        mock_client.models.generate_content.side_effect = RuntimeError("Service Unavailable")

        resp = client.post(
            URL_RECOMMEND,
            json={
                "location": "Pune",
                "weight": 10.0,
                "weather": "Humid",
                "duration_pref": "Standard",
            },
        )

    assert resp.status_code == 503


def test_validation_error_returns_422(client):
    with patch("app.routers.simulator.KEY_RECOMMEND", "test-rec-key"), \
         patch("app.routers.simulator.KEY_EXPLAIN", "test-exp-key"):
        # Missing weight and duration_pref
        resp = client.post(URL_RECOMMEND, json={"location": "Pune"})
    assert resp.status_code == 422
