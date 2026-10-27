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



# ─── Chunking for Sarvam's per-request limits (offline: _sarvam_post is mocked) ──

import base64
import io
import wave

from app.routers import sarvam_router


def _wav_b64(frames: int) -> str:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\x00\x00" * frames)
    return base64.b64encode(buf.getvalue()).decode()


def test_split_text_respects_limit_and_keeps_all_text():
    text = "Pyrolysis heats waste without oxygen. " * 40 + "नमस्ते। यह एक परीक्षण है। " * 5
    chunks = sarvam_router.split_text(text, 500)
    assert len(chunks) > 1
    assert all(0 < len(c) <= 500 for c in chunks)
    assert "".join(chunks).replace(" ", "") == text.replace(" ", "")


def test_split_text_breaks_overlong_sentence_on_words():
    chunks = sarvam_router.split_text("word " * 300, 500)
    assert all(len(c) <= 500 for c in chunks)
    assert all(not c.startswith("ord") for c in chunks)  # never cuts mid-word


def test_long_tts_is_chunked_and_audio_joined():
    calls = []

    async def fake_post(client, path, payload, api_key, service):
        calls.append(payload["inputs"][0])
        return {"audios": [_wav_b64(1000)]}

    text = "This sentence is about forty-five characters. " * 30  # ~1,400 chars
    with patch.object(sarvam_router, "_sarvam_post", side_effect=fake_post), \
         patch.dict(os.environ, {"SARVAM_API_KEY": "test-key"}):
        res = client.post("/sarvam/tts", json={"text": text, "language_code": "en-IN"})

    assert res.status_code == 200, res.text
    assert len(calls) == 3 and all(len(c) <= sarvam_router.TTS_MAX_CHARS for c in calls)
    with wave.open(io.BytesIO(base64.b64decode(res.json()["audio_base64"]))) as w:
        assert w.getnframes() == 3000  # three 1,000-frame clips joined


def test_long_translation_is_chunked_and_keeps_line_breaks():
    calls = []

    async def fake_post(client, path, payload, api_key, service):
        calls.append(payload["input"])
        return {"translated_text": f"[{len(calls)}]"}

    text = "First paragraph.\n" + ("A long line of text. " * 120)  # ~2,500 chars
    with patch.object(sarvam_router, "_sarvam_post", side_effect=fake_post), \
         patch.dict(os.environ, {"SARVAM_API_KEY": "test-key"}):
        res = client.post("/sarvam/translate", json={
            "text": text, "source_language_code": "en-IN", "target_language_code": "hi-IN",
        })

    assert res.status_code == 200, res.text
    # "First paragraph." can't share a chunk with the 1,994-char piece, and the long line needs two.
    assert len(calls) == 3 and all(len(c) <= sarvam_router.TRANSLATE_MAX_CHARS for c in calls)
    # Paragraph break kept; the split long line is rejoined with a space, not a new line.
    assert res.json()["translated_text"] == "[1]\n[2] [3]"


def test_short_translation_is_one_request_with_layout_kept():
    calls = []

    async def fake_post(client, path, payload, api_key, service):
        calls.append(payload["input"])
        return {"translated_text": payload["input"].upper()}

    with patch.object(sarvam_router, "_sarvam_post", side_effect=fake_post), \
         patch.dict(os.environ, {"SARVAM_API_KEY": "test-key"}):
        res = client.post("/sarvam/translate", json={
            "text": "line one\n\nline two", "source_language_code": "en-IN", "target_language_code": "hi-IN",
        })

    assert calls == ["line one\n\nline two"]
    assert res.json()["translated_text"] == "LINE ONE\n\nLINE TWO"
