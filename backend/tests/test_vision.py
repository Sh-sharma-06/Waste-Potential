"""Tests for POST /vision/classify and POST /vision/advice (app/ml/vision_router.py).

All Gemini calls are mocked — no network required.

Covers:
  - Valid JSON path: items parsed, stream derived server-side, fields present.
  - Malformed Gemini JSON → 502.
  - Missing 'items' key in Gemini JSON → 502.
  - Missing API key → 503.
  - API failure (exception from genai) → 503.
  - 6 MB upload → 422.
  - Non-image MIME type → 422.
  - Stream derived server-side even if Gemini says otherwise.
  - Advice with a bad sector → 422.
  - Advice valid path (urban + rural).
"""

from __future__ import annotations

import io
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ml.vision_router import (
    _CLASSIFY_DISCLAIMER,
    _GEMINI_MODEL,
    _derive_stream,
    router,
    WasteItem,
)

URL_CLASSIFY = "/vision/classify"
URL_ADVICE = "/vision/advice"

# Minimal 1×1 white JPEG bytes (real JFIF header so content-type is valid)
_TINY_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
    b"\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a"
    b"\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\x1e"
    b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00"
    b"\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00"
    b"\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xc4\x00"
    b"\xb5\x10\x00\x02\x01\x03\x03\x02\x04\x03\x05\x05\x04\x04\x00\x00"
    b"\x01}\x01\x02\x03\x00\x04\x11\x05\x12!1A\x06\x13Qa\x07\"q\x142\x81"
    b"\x91\xa1\x08#B\xb1\xc1\x15R\xd1\xf0$3br\x82\t\n\x16\x17\x18\x19"
    b"\x1a%&'()*456789:CDEFGHIJSTUVWXYZ"
    b"\xff\xda\x00\x08\x01\x01\x00\x00?\x00\xfb\xd2\x8a(\x03\xff\xd9"
)


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client():
    return TestClient(_app())


def _gemini_response(text: str):
    """Build a minimal mock object matching response.text."""
    resp = MagicMock()
    resp.text = text
    return resp


def _upload_jpeg(client, data: bytes = _TINY_JPEG):
    return client.post(
        URL_CLASSIFY,
        files={"file": ("waste.jpg", io.BytesIO(data), "image/jpeg")},
    )


# ---------------------------------------------------------------------------
# 1. Valid classify path
# ---------------------------------------------------------------------------

def test_classify_valid_json(client):
    gemini_json = json.dumps({
        "items": [
            {"label": "banana peel", "category": "organic", "confidence": 0.95},
            {"label": "plastic bottle", "category": "plastic", "confidence": 0.88},
        ]
    })

    with patch("app.ml.vision_router._GEMINI_API_KEY_VISION", "fake-key"), \
         patch("app.ml.vision_router.genai.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.models.generate_content.return_value = _gemini_response(gemini_json)
        resp = _upload_jpeg(client)

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "items" in data
    assert "stream" in data
    assert "model" in data
    assert "timestamp" in data
    assert "disclaimer" in data
    assert data["disclaimer"] == _CLASSIFY_DISCLAIMER
    assert len(data["items"]) == 2
    assert data["items"][0]["category"] == "organic"
    assert data["model"] == _GEMINI_MODEL


# ---------------------------------------------------------------------------
# 2. Stream derived server-side (Gemini output irrelevant for stream)
# ---------------------------------------------------------------------------

def test_stream_derived_server_side_ignores_gemini(client):
    """Even if we manufacture a response with only organic items, the server
    must derive 'organic'. Even if all items are plastic, it must be 'non_organic'."""
    gemini_json = json.dumps({
        "items": [
            {"label": "plastic bag", "category": "plastic", "confidence": 0.9},
        ]
    })
    with patch("app.ml.vision_router._GEMINI_API_KEY_VISION", "fake-key"), \
         patch("app.ml.vision_router.genai.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.models.generate_content.return_value = _gemini_response(gemini_json)
        resp = _upload_jpeg(client)

    assert resp.status_code == 200
    assert resp.json()["stream"] == "non_organic"


def test_stream_organic_when_any_organic_item(client):
    gemini_json = json.dumps({
        "items": [
            {"label": "food scraps", "category": "organic", "confidence": 0.80},
            {"label": "tin can", "category": "metal", "confidence": 0.92},
        ]
    })
    with patch("app.ml.vision_router._GEMINI_API_KEY_VISION", "fake-key"), \
         patch("app.ml.vision_router.genai.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.models.generate_content.return_value = _gemini_response(gemini_json)
        resp = _upload_jpeg(client)

    assert resp.status_code == 200
    assert resp.json()["stream"] == "organic"


# ---------------------------------------------------------------------------
# 3. Malformed Gemini JSON → 502
# ---------------------------------------------------------------------------

def test_classify_malformed_json_returns_502(client):
    with patch("app.ml.vision_router._GEMINI_API_KEY_VISION", "fake-key"), \
         patch("app.ml.vision_router.genai.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.models.generate_content.return_value = _gemini_response(
            "This is not JSON at all"
        )
        resp = _upload_jpeg(client)

    assert resp.status_code == 502
    assert "invalid JSON" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 4. Missing 'items' key in Gemini JSON → 502
# ---------------------------------------------------------------------------

def test_classify_missing_items_key_returns_502(client):
    gemini_json = json.dumps({"wrong_key": []})
    with patch("app.ml.vision_router._GEMINI_API_KEY_VISION", "fake-key"), \
         patch("app.ml.vision_router.genai.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.models.generate_content.return_value = _gemini_response(gemini_json)
        resp = _upload_jpeg(client)

    assert resp.status_code == 502
    assert "items" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 5. Missing API key → 503
# ---------------------------------------------------------------------------

def test_classify_missing_api_key_returns_503(client):
    with patch("app.ml.vision_router._GEMINI_API_KEY_VISION", ""):
        resp = _upload_jpeg(client)

    assert resp.status_code == 503
    assert "not configured" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 6. API failure (genai exception) → 503
# ---------------------------------------------------------------------------

def test_classify_api_failure_returns_503(client):
    with patch("app.ml.vision_router._GEMINI_API_KEY_VISION", "fake-key"), \
         patch("app.ml.vision_router.genai.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.models.generate_content.side_effect = RuntimeError("network error")
        resp = _upload_jpeg(client)

    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# 7. File too large → 422
# ---------------------------------------------------------------------------

def test_classify_oversized_file_returns_422(client):
    big_jpeg = _TINY_JPEG + b"\x00" * (5 * 1024 * 1024 + 1)
    with patch("app.ml.vision_router._GEMINI_API_KEY_VISION", "fake-key"):
        resp = _upload_jpeg(client, data=big_jpeg)

    assert resp.status_code == 422
    assert "5 MB" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 8. Non-image MIME type → 422
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mime", ["text/plain", "application/pdf", "video/mp4"])
def test_classify_non_image_mime_returns_422(client, mime):
    resp = client.post(
        URL_CLASSIFY,
        files={"file": ("file.bin", io.BytesIO(b"fake"), mime)},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 9. _derive_stream unit tests
# ---------------------------------------------------------------------------

def test_derive_stream_organic_when_organic_present():
    items = [WasteItem(label="food", category="organic", confidence=0.9)]
    assert _derive_stream(items) == "organic"


def test_derive_stream_non_organic_without_organic():
    items = [
        WasteItem(label="bottle", category="plastic", confidence=0.9),
        WasteItem(label="can", category="metal", confidence=0.8),
    ]
    assert _derive_stream(items) == "non_organic"


def test_derive_stream_empty_items():
    assert _derive_stream([]) == "non_organic"


# ---------------------------------------------------------------------------
# 10. Advice valid path
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sector", ["urban", "rural"])
def test_advice_valid_sector(client, sector):
    advice_text = "• Sort your waste.\nFollow your local municipal waste rules."
    with patch("app.ml.vision_router._GEMINI_API_KEY_VISION", "fake-key"), \
         patch("app.ml.vision_router.genai.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.models.generate_content.return_value = _gemini_response(advice_text)
        resp = client.post(URL_ADVICE, json={"sector": sector, "items": ["plastic bag", "food waste"]})

    assert resp.status_code == 200
    assert resp.json()["text"] == advice_text


# ---------------------------------------------------------------------------
# 11. Advice with a bad sector → 422
# ---------------------------------------------------------------------------

def test_advice_bad_sector_returns_422(client):
    resp = client.post(URL_ADVICE, json={"sector": "industrial", "items": ["plastic"]})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 12. Advice missing key → 503
# ---------------------------------------------------------------------------

def test_advice_missing_api_key_returns_503(client):
    with patch("app.ml.vision_router._GEMINI_API_KEY_VISION", ""):
        resp = client.post(URL_ADVICE, json={"sector": "urban", "items": ["paper"]})
    assert resp.status_code == 503


# ---------------------------------------------------------------------------
# 13. Text file renamed .jpg → 422 (magic-byte validation)
# ---------------------------------------------------------------------------

def test_classify_text_file_renamed_jpg_returns_422(client):
    """A plain-text file sent with content-type image/jpeg must be rejected
    because its magic bytes do not match JPEG (\\xff\\xd8\\xff)."""
    text_bytes = b"This is plain text, not a JPEG image.\n"
    resp = client.post(
        URL_CLASSIFY,
        files={"file": ("sneaky.jpg", io.BytesIO(text_bytes), "image/jpeg")},
    )
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert "image format" in detail.lower() or "magic" in detail.lower() or "content" in detail.lower()


# ---------------------------------------------------------------------------
# 14. confidence 1.5 in Gemini response → 502 (not clipped silently)
# ---------------------------------------------------------------------------

def test_classify_confidence_out_of_range_returns_502(client):
    """Gemini returning confidence=1.5 (> 1.0) must be rejected as malformed (502),
    not silently clipped to 1.0."""
    gemini_json = json.dumps({
        "items": [
            {"label": "mystery item", "category": "plastic", "confidence": 1.5},
        ]
    })
    with patch("app.ml.vision_router._GEMINI_API_KEY_VISION", "fake-key"), \
         patch("app.ml.vision_router.genai.Client") as mock_client_cls:
        mock_client = mock_client_cls.return_value
        mock_client.models.generate_content.return_value = _gemini_response(gemini_json)
        resp = _upload_jpeg(client)

    assert resp.status_code == 502, (
        f"Expected 502 for out-of-range confidence, got {resp.status_code}: {resp.text}"
    )


# ---------------------------------------------------------------------------
# 15. Advice system prompt contains "no numbers" instruction
# ---------------------------------------------------------------------------

def test_advice_prompt_forbids_numbers(client):
    """The system prompt sent to Gemini must contain the instruction to not include
    numbers, prices or yields.  Assert this on the captured call args."""
    advice_text = "• Sort your waste.\nFollow your local municipal waste rules."

    captured_config = {}

    def fake_generate_content(model, contents, config):
        captured_config["system_instruction"] = config.system_instruction
        resp = MagicMock()
        resp.text = advice_text
        return resp

    with patch("app.ml.vision_router._GEMINI_API_KEY_VISION", "fake-key"), \
         patch("app.ml.vision_router.genai.Client") as mock_client_cls:
        mock_client_cls.return_value.models.generate_content.side_effect = fake_generate_content
        resp = client.post(URL_ADVICE, json={"sector": "urban", "items": ["plastic bag"]})

    assert resp.status_code == 200
    system_prompt = captured_config.get("system_instruction", "")
    # Spec: system prompt must forbid numbers, prices and yields
    assert "number" in system_prompt.lower(), (
        "System prompt must mention 'numbers' restriction"
    )
    assert "price" in system_prompt.lower(), (
        "System prompt must mention 'prices' restriction"
    )
    assert "yield" in system_prompt.lower() or "quantit" in system_prompt.lower(), (
        "System prompt must mention 'yields' or 'quantities' restriction"
    )
    # Spec: safety line — do not burn waste
    assert "burn" in system_prompt.lower(), (
        "System prompt must forbid burning waste"
    )
    # Spec: follow local rules
    assert "local" in system_prompt.lower(), (
        "System prompt must include 'follow local rules'"
    )
