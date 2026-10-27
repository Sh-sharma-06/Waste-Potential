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


def _mock_recommend(client, model_text, body, **patches):
    mock_genai_response = MagicMock()
    mock_genai_response.text = model_text
    with patch("app.routers.simulator.KEY_RECOMMEND", "test-rec-key"), \
         patch("app.routers.simulator.KEY_EXPLAIN", "test-exp-key"), \
         patch("app.routers.simulator.genai.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.models.generate_content.return_value = mock_genai_response
        resp = client.post(URL_RECOMMEND, json=body)
        sent = mock_client.models.generate_content.call_args
    return resp, sent


@pytest.mark.parametrize("model_says", [
    "htc", "HTC", "Hydrothermal Carbonisation (HTC)", "Hydrothermal Carbonization",
])
def test_recommend_normalises_htc_variants(client, model_says):
    resp, _ = _mock_recommend(
        client, json.dumps({"suggested_process": model_says}),
        {"location": "Pune", "weight": 5.0, "weather": "Humid"},
    )
    assert resp.status_code == 200
    assert resp.json()["process_id"] == "htc"
    assert resp.json()["suggested_process"] == "Hydrothermal Carbonisation (HTC)"


def test_recommend_rejects_process_outside_pathway_list(client):
    resp, _ = _mock_recommend(
        client, json.dumps({"suggested_process": "Pelletization"}),
        {"location": "Pune", "weight": 5.0, "weather": "Humid"},
    )
    assert resp.status_code == 502


def test_recommend_sends_real_inputs_and_live_weather(client):
    from app.services.geocode_client import GeocodeResult
    from app.services.weather_client import WeatherReading

    with patch("app.routers.simulator.geocode_pincode",
               return_value=GeocodeResult(lat=18.52, lng=73.85, display_name="Pune", cached=False)) as geo, \
         patch("app.routers.simulator.get_current_weather",
               return_value=WeatherReading(latitude=18.52, longitude=73.85,
                                           ambient_temp_c=31.4, relative_humidity=0.62)):
        resp, sent = _mock_recommend(
            client, json.dumps({"suggested_process": "composting"}),
            {"location": "Pune", "weight": 0.5, "category": "energy",
             "pincode": "411001", "duration_pref": "Weeks (2–8 weeks)"},
        )

    assert resp.status_code == 200
    assert resp.json()["weather_used"].startswith("31.4°C, 62% relative humidity")
    geo.assert_called_once_with(pincode="411001", country="India")
    prompt = sent.kwargs["contents"]
    assert "energy-recoverable stream" in prompt
    assert "0.5 tonnes per day" in prompt
    assert "31.4°C" in prompt
    assert "Weeks (2–8 weeks)" in prompt
    system = sent.kwargs["config"].system_instruction
    assert "Pelletization" not in system and "torrefaction" in system


def test_recommend_defaults_to_no_duration_preference(client):
    resp, sent = _mock_recommend(
        client, json.dumps({"suggested_process": "pyrolysis"}),
        {"location": "Pune", "weight": 5.0, "weather": "Humid"},
    )
    assert resp.status_code == 200
    assert "Preferred processing duration: No preference" in sent.kwargs["contents"]


def test_recommend_falls_back_to_backup_key_when_out_of_credit(client):
    """A 402 on the recommend key moves on to the next configured key."""
    ok = MagicMock()
    ok.text = json.dumps({"suggested_process": "composting"})

    def make_client(api_key):
        c = MagicMock()
        if api_key == "dead-key":
            c.models.generate_content.side_effect = RuntimeError("402 RESOURCE_EXHAUSTED prepayment credits are depleted")
        else:
            c.models.generate_content.return_value = ok
        return c

    with patch("app.routers.simulator.KEY_RECOMMEND", "dead-key"), \
         patch("app.routers.simulator.KEY_EXPLAIN", "test-exp-key"), \
         patch.dict("os.environ", {"GEMINI_API_KEY_EXPLAIN": "backup-key"}), \
         patch("app.routers.simulator.genai.Client", side_effect=make_client) as mock_cls:
        resp = client.post(URL_RECOMMEND, json={"location": "Pune", "weight": 5.0, "weather": "Humid"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["process_id"] == "composting"
    keys_tried = [c.kwargs["api_key"] for c in mock_cls.call_args_list]
    assert keys_tried == ["dead-key", "backup-key"]  # skipped the dead key's other models
