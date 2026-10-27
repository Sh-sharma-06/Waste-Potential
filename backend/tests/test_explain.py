"""Tests for POST /pathways/explain (app/pathways/explain_router.py).

All Gemini calls are mocked — no network required.

Covers:
  - Grounded Gemini answer accepted (source="gemini", grounded=True).
  - Invented number blocked → template returned (source="template", grounded=False).
  - Rejected pathway's template names its reasons.
  - Thermal pathway: system prompt contains instruction not to call it electricity.
  - Missing API key → template (never 500).
  - Unknown pathway → 422.
  - Response is JSON-serialisable.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.pathways.explain_router import router, _EXPLAIN_SYSTEM, _EXPLAIN_DISCLAIMER
from app.pathways.explain_service import (
    build_template,
    check_grounding,
    extract_numbers,
)

URL = "/pathways/explain"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client():
    return TestClient(_app())


def _gemini_mock(text: str) -> MagicMock:
    resp = MagicMock()
    resp.text = text
    return resp


# ---------------------------------------------------------------------------
# Shared compare-like results fixture
# ---------------------------------------------------------------------------

_AD_ROW = {
    "pathway": "anaerobic_digestion",
    "feasible": True,
    "reasons": [],
    "e_net_kwh_d": 76.74,
    "annual_net_value_inr": 250000.0,
    "primary_product": "biogas",
    "energy_basis": "thermal",
    "optimality_share": 0.62,
    "warnings": ["illustrative estimate"],
    "outputs": {},
    "status": "feasible",
    "model_status": "illustrative_estimate",
    "win_count": 310,
    "optimality_note": None,
    "revenue_inr_y": 300000.0,
    "cost_inr_y": 50000.0,
}

_COMPOST_ROW = {
    "pathway": "composting",
    "feasible": True,
    "reasons": [],
    "e_net_kwh_d": 0.0,
    "annual_net_value_inr": 80000.0,
    "primary_product": "compost",
    "energy_basis": "none",
    "optimality_share": 0.38,
    "warnings": [],
    "outputs": {},
    "status": "feasible",
    "model_status": "illustrative_estimate",
    "win_count": 190,
    "optimality_note": None,
    "revenue_inr_y": 100000.0,
    "cost_inr_y": 20000.0,
}

_PYROLYSIS_ROW = {
    "pathway": "pyrolysis",
    "feasible": False,
    "reasons": ["Insufficient feedstock LHV for net-positive pyrolysis"],
    "e_net_kwh_d": 0.0,
    "annual_net_value_inr": 0.0,
    "primary_product": "bio_oil",
    "energy_basis": "thermal",
    "optimality_share": None,
    "warnings": ["GHG not modelled"],
    "outputs": {},
    "status": "rejected",
    "model_status": "illustrative_estimate",
    "win_count": None,
    "optimality_note": None,
    "revenue_inr_y": 0.0,
    "cost_inr_y": 0.0,
}

_ALL_RESULTS = [_AD_ROW, _COMPOST_ROW, _PYROLYSIS_ROW]


# ---------------------------------------------------------------------------
# 1. Grounded Gemini answer accepted
# ---------------------------------------------------------------------------

def test_grounded_gemini_answer_accepted(client):
    """A Gemini response that only uses numbers from FACTS is accepted."""
    # Only use numbers that are in FACTS: 76.74, 250000.0, 0.62
    grounded_text = (
        "Anaerobic digestion ranked first with a net electricity of 76.74 kWh/d "
        "and an annual net value of 250000.0 INR/year. "
        "It was optimal in 0.62 of Monte Carlo runs. "
        "Ranking depends on assumed price and cost distributions and is not validated."
    )

    with patch("app.pathways.explain_router._GEMINI_API_KEY_EXPLAIN", "fake-key"), \
         patch("app.pathways.explain_router.genai.Client") as mock_cls:
        mock_cls.return_value.models.generate_content.return_value = _gemini_mock(grounded_text)
        resp = client.post(URL, json={"pathway": "anaerobic_digestion", "results": _ALL_RESULTS})

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["source"] == "gemini"
    assert data["grounded"] is True
    assert data["unsupported_numbers"] == []
    assert data["disclaimer"] == _EXPLAIN_DISCLAIMER
    assert "facts" in data
    assert data["facts"]["pathway"] == "anaerobic_digestion"
    assert data["text"] == grounded_text


# ---------------------------------------------------------------------------
# 2. Invented number blocked → template returned
# ---------------------------------------------------------------------------

def test_invented_number_blocked_returns_template(client):
    """A Gemini response containing a number not in FACTS must be blocked."""
    invented_text = (
        "Anaerobic digestion produces 999999 kWh/d of electricity. "
        "Ranking depends on assumed price and cost distributions and is not validated."
    )

    with patch("app.pathways.explain_router._GEMINI_API_KEY_EXPLAIN", "fake-key"), \
         patch("app.pathways.explain_router.genai.Client") as mock_cls:
        mock_cls.return_value.models.generate_content.return_value = _gemini_mock(invented_text)
        resp = client.post(URL, json={"pathway": "anaerobic_digestion", "results": _ALL_RESULTS})

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["source"] == "template", f"Expected template fallback, got {data['source']!r}"
    assert data["grounded"] is False
    assert 999999.0 in data["unsupported_numbers"]


# ---------------------------------------------------------------------------
# 3. Rejected pathway's explanation names its reasons
# ---------------------------------------------------------------------------

def test_rejected_pathway_template_names_reasons(client):
    """When the pathway is infeasible and the template is used, the reasons appear."""
    with patch("app.pathways.explain_router._GEMINI_API_KEY_EXPLAIN", ""):
        resp = client.post(URL, json={"pathway": "pyrolysis", "results": _ALL_RESULTS})

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["source"] == "template"
    assert "Insufficient feedstock LHV" in data["text"], (
        f"Expected rejection reason in text: {data['text']!r}"
    )


# ---------------------------------------------------------------------------
# 4. Thermal pathway system prompt forbids calling it "electricity"
# ---------------------------------------------------------------------------

def test_system_prompt_forbids_electricity_for_thermal(client):
    """The system prompt sent to Gemini must instruct not to call thermal output electricity."""
    captured: dict = {}

    def fake_generate(model, contents, config):
        captured["system_instruction"] = config.system_instruction
        return _gemini_mock(
            "The thermal output is 76.74 kWh/d. "
            "Ranking depends on assumed price and cost distributions and is not validated."
        )

    with patch("app.pathways.explain_router._GEMINI_API_KEY_EXPLAIN", "fake-key"), \
         patch("app.pathways.explain_router.genai.Client") as mock_cls:
        mock_cls.return_value.models.generate_content.side_effect = fake_generate
        resp = client.post(URL, json={"pathway": "anaerobic_digestion", "results": _ALL_RESULTS})

    assert resp.status_code == 200
    prompt = captured.get("system_instruction", "")
    assert "thermal" in prompt.lower(), "Prompt must mention 'thermal'"
    assert "electricity" in prompt.lower(), (
        "Prompt must instruct not to call thermal output 'electricity'"
    )


# ---------------------------------------------------------------------------
# 5. Missing API key → template (never 500)
# ---------------------------------------------------------------------------

def test_missing_api_key_returns_template_not_500(client):
    """With no API key, the endpoint must return the template, not a 500."""
    with patch("app.pathways.explain_router._GEMINI_API_KEY_EXPLAIN", ""):
        resp = client.post(URL, json={"pathway": "anaerobic_digestion", "results": _ALL_RESULTS})

    assert resp.status_code == 200, f"Expected 200 (template), got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["source"] == "template"
    assert data["grounded"] is False
    assert data["disclaimer"] == _EXPLAIN_DISCLAIMER


# ---------------------------------------------------------------------------
# 6. Unknown pathway → 422
# ---------------------------------------------------------------------------

def test_unknown_pathway_returns_422(client):
    resp = client.post(URL, json={"pathway": "landfill", "results": _ALL_RESULTS})
    assert resp.status_code == 422
    body = resp.json()
    assert "detail" in body
    assert "landfill" in body["detail"]


# ---------------------------------------------------------------------------
# 7. Response is JSON-serialisable
# ---------------------------------------------------------------------------

def test_response_is_json_serialisable(client):
    with patch("app.pathways.explain_router._GEMINI_API_KEY_EXPLAIN", ""):
        resp = client.post(URL, json={"pathway": "anaerobic_digestion", "results": _ALL_RESULTS})

    assert resp.status_code == 200
    # If resp.json() did not raise, the response is JSON-serialisable.
    # Round-trip through json.dumps to be thorough.
    round_tripped = json.loads(json.dumps(resp.json()))
    assert round_tripped["source"] == "template"


# ---------------------------------------------------------------------------
# 8. API failure (exception) → template (never 500)
# ---------------------------------------------------------------------------

def test_api_failure_returns_template_not_500(client):
    with patch("app.pathways.explain_router._GEMINI_API_KEY_EXPLAIN", "fake-key"), \
         patch("app.pathways.explain_router.genai.Client") as mock_cls:
        mock_cls.return_value.models.generate_content.side_effect = RuntimeError("network down")
        resp = client.post(URL, json={"pathway": "anaerobic_digestion", "results": _ALL_RESULTS})

    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "template"
    assert data["grounded"] is False


# ---------------------------------------------------------------------------
# 9. Facts dict is echoed in response
# ---------------------------------------------------------------------------

def test_facts_echoed_in_response(client):
    with patch("app.pathways.explain_router._GEMINI_API_KEY_EXPLAIN", ""):
        resp = client.post(URL, json={"pathway": "composting", "results": _ALL_RESULTS})

    data = resp.json()
    facts = data["facts"]
    assert facts["pathway"] == "composting"
    assert facts["feasible"] is True
    assert "peer_optimality_shares" in facts
    # peer shares should include anaerobic_digestion and pyrolysis
    assert "anaerobic_digestion" in facts["peer_optimality_shares"]
    assert "pyrolysis" in facts["peer_optimality_shares"]


# ---------------------------------------------------------------------------
# Unit tests for explain_service helpers
# ---------------------------------------------------------------------------

def test_extract_numbers_basic():
    assert extract_numbers("value is 76.74 kWh and 250000 INR") == [76.74, 250000.0]


def test_extract_numbers_negative():
    assert extract_numbers("temperature -15.0 C") == [-15.0]


def test_check_grounding_passes_when_all_match():
    facts = {"e_net_kwh_d": 76.74, "annual_net_value_inr": 250000.0}
    grounded, unsupported = check_grounding("value 76.74 and 250000.0", facts)
    assert grounded is True
    assert unsupported == []


def test_check_grounding_fails_on_invented_number():
    facts = {"e_net_kwh_d": 76.74}
    grounded, unsupported = check_grounding("value 99999.0", facts)
    assert grounded is False
    assert 99999.0 in unsupported


def test_check_grounding_one_percent_tolerance():
    # 76.74 * 1.009 is within 1%; 76.74 * 1.02 is outside
    facts = {"e_net_kwh_d": 76.74}
    g1, _ = check_grounding(f"{76.74 * 1.009:.4f}", facts)
    g2, _ = check_grounding(f"{76.74 * 1.02:.4f}", facts)
    assert g1 is True
    assert g2 is False


def test_build_template_feasible():
    facts = {
        "pathway": "anaerobic_digestion",
        "feasible": True,
        "reasons": [],
        "e_net_kwh_d": 76.74,
        "annual_net_value_inr": 250000.0,
        "optimality_share": 0.62,
        "primary_product": "biogas",
        "energy_basis": "thermal",
        "warnings": [],
    }
    text = build_template("anaerobic_digestion", facts)
    assert "anaerobic_digestion" in text
    assert "76.7" in text
    assert "not validated" in text


def test_build_template_infeasible_names_reasons():
    facts = {
        "pathway": "pyrolysis",
        "feasible": False,
        "reasons": ["Too wet for pyrolysis"],
        "e_net_kwh_d": 0.0,
        "annual_net_value_inr": 0.0,
        "optimality_share": None,
        "primary_product": "bio_oil",
        "energy_basis": "thermal",
        "warnings": [],
    }
    text = build_template("pyrolysis", facts)
    assert "Too wet for pyrolysis" in text
    assert "not validated" in text


def test_explain_falls_back_to_next_model():
    """If the configured model fails (quota/overload), the next model answers instead of the template."""
    from app.config import gemini_models
    from app.pathways.explain_router import _call_gemini

    calls = []

    def generate(model, contents, config):
        calls.append(model)
        if len(calls) == 1:
            raise RuntimeError("429 RESOURCE_EXHAUSTED")
        return _gemini_mock("Fallback model answer.")

    with patch("app.pathways.explain_router.genai.Client") as mock_cls:
        mock_cls.return_value.models.generate_content.side_effect = generate
        text = _call_gemini("fake-key", {"pathway": "pyrolysis"})

    assert text == "Fallback model answer."
    assert calls == gemini_models()[:2]
