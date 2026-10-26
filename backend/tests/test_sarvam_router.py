"""Unit tests for Sarvam AI router endpoints."""

import os
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_sarvam_missing_api_key_returns_503():
    with patch.dict(os.environ, {"SARVAM_API_KEY": "", "SARVAM_API": ""}):
        res = client.post("/sarvam/translate", json={
            "text": "Hello",
            "source_language_code": "en-IN",
            "target_language_code": "hi-IN"
        })
        assert res.status_code == 503
        assert "not configured" in res.json().get("detail", "").lower()


def test_sarvam_unsupported_language_returns_400():
    res = client.post("/sarvam/translate", json={
        "text": "Hello",
        "source_language_code": "fr-FR",
        "target_language_code": "hi-IN"
    })
    assert res.status_code == 400
    assert "unsupported" in res.json().get("detail", "").lower()


def test_sarvam_same_language_returns_identity():
    res = client.post("/sarvam/translate", json={
        "text": "Already English",
        "source_language_code": "en-IN",
        "target_language_code": "en-IN"
    })
    assert res.status_code == 200
    assert res.json()["translated_text"] == "Already English"


def test_sarvam_tts_valid_request():
    res = client.post("/sarvam/tts", json={
        "text": "Testing text to speech",
        "language_code": "hi-IN",
        "speaker": "meera"
    })
    assert res.status_code == 200
    data = res.json()
    assert "audio_base64" in data
    assert len(data["audio_base64"]) > 0
    assert data["language_code"] == "hi-IN"


def test_sarvam_translate_live_request():
    res = client.post("/sarvam/translate", json={
        "text": "Waste management and biogas production",
        "source_language_code": "en-IN",
        "target_language_code": "hi-IN"
    })
    assert res.status_code == 200
    data = res.json()
    assert "translated_text" in data
    assert len(data["translated_text"]) > 0


def test_sarvam_stt_synthetic_wav():
    import io, wave, struct
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        for _ in range(16000):
            wav.writeframes(struct.pack('<h', 0))
    wav_bytes = buf.getvalue()

    files = {"file": ("test.wav", wav_bytes, "audio/wav")}
    res = client.post("/sarvam/stt", files=files)
    assert res.status_code == 200
    data = res.json()
    assert "transcript" in data

