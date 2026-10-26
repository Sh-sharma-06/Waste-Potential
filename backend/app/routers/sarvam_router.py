"""Sarvam AI integration router for Speech-to-Text (STT), Translation, and Text-to-Speech (TTS)."""

from __future__ import annotations

import logging
import os
from enum import Enum
from typing import Optional

import httpx
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sarvam", tags=["Sarvam AI"])

SARVAM_BASE_URL = "https://api.sarvam.ai"

# 10 Indian languages supported by Sarvam AI
class IndianLanguage(str, Enum):
    HINDI = "hi-IN"
    BENGALI = "bn-IN"
    MARATHI = "mr-IN"
    TELUGU = "te-IN"
    TAMIL = "ta-IN"
    GUJARATI = "gu-IN"
    KANNADA = "kn-IN"
    ODIA = "or-IN"
    MALAYALAM = "ml-IN"
    PUNJABI = "pa-IN"


SUPPORTED_INDIAN_LANGUAGES = {lang.value for lang in IndianLanguage}
SUPPORTED_ALL_LANGUAGES = SUPPORTED_INDIAN_LANGUAGES.union({"en-IN", "en-US", "auto"})

# Valid speakers for Sarvam bulbul:v3
BULBUL_V3_SPEAKERS = {
    "aditya", "ritu", "ashutosh", "priya", "neha", "rahul", "pooja", "rohan",
    "simran", "kavya", "amit", "dev", "ishita", "shreya", "ratan", "varun",
    "manan", "sumit", "roopa", "kabir", "aayan", "shubh", "advait", "anand",
    "tanya", "tarun", "sunny", "mani", "gokul", "vijay", "shruti", "suhani",
    "mohit", "kavitha", "rehan", "soham", "rupali"
}

SPEAKER_MAPPINGS = {
    "meera": "kavya",
    "anushka": "priya",
    "vidya": "shreya",
}


def get_sarvam_api_key() -> str:
    """Retrieve SARVAM_API_KEY from environment or config. Raise 503 if missing."""
    key = os.getenv("SARVAM_API_KEY") or os.getenv("SARVAM_API") or ""
    key = key.strip().strip('"').strip("'")
    if not key:
        raise HTTPException(
            status_code=503,
            detail="Sarvam AI service is not configured (SARVAM_API_KEY missing in .env).",
        )
    return key


def normalize_lang_code(code: str | None) -> str:
    """Normalize language codes (e.g. en-US -> en-IN for Sarvam)."""
    if not code:
        return "en-IN"
    c = code.strip().lower()
    if c.startswith("en") or c == "english":
        return "en-IN"
    return code.strip()


# ─── Pydantic Schemas ─────────────────────────────────────────────────────────

class TranslateRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Input text to translate")
    source_language_code: str = Field(..., description="Source BCP-47 language code")
    target_language_code: str = Field(..., description="Target BCP-47 language code")


class TranslateResponse(BaseModel):
    translated_text: str
    source_language_code: str
    target_language_code: str


class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Input text to speak")
    language_code: str = Field(default="hi-IN", description="Target language BCP-47 code")
    speaker: str = Field(default="meera", description="Voice speaker persona")


class TTSResponse(BaseModel):
    audio_base64: str
    audios: list[str]
    language_code: str
    speaker: str


class STTResponse(BaseModel):
    transcript: str
    language_code: Optional[str] = None


# ─── Endpoints ───────────────────────────────────────────────────────────────

@router.post("/stt", response_model=STTResponse)
async def speech_to_text(
    file: UploadFile = File(..., description="Audio file (WAV, MP3, AAC, WebM, etc.)"),
    language_code: Optional[str] = Form(None, description="Optional spoken language code"),
):
    """Transcribe spoken audio using Sarvam Speech-to-Text API."""
    api_key = get_sarvam_api_key()

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Uploaded audio file is empty.")

    filename = file.filename or "audio.wav"
    content_type = file.content_type or "audio/wav"

    data: dict[str, str] = {"model": "saaras:v3"}
    if language_code:
        norm = normalize_lang_code(language_code)
        if norm in SUPPORTED_ALL_LANGUAGES:
            data["language_code"] = norm

    headers = {"api-subscription-key": api_key}
    files = {"file": (filename, content, content_type)}

    async with httpx.AsyncClient(timeout=45.0) as client:
        try:
            resp = await client.post(
                f"{SARVAM_BASE_URL}/speech-to-text",
                data=data,
                files=files,
                headers=headers,
            )
        except Exception as exc:
            logger.error("Sarvam STT network error: %s", exc)
            raise HTTPException(
                status_code=502,
                detail=f"Failed to communicate with Sarvam STT service: {str(exc)}",
            )

    if resp.status_code != 200:
        logger.error("Sarvam STT error %s: %s", resp.status_code, resp.text)
        raise HTTPException(
            status_code=resp.status_code if resp.status_code < 500 else 502,
            detail=f"Sarvam STT failed: {resp.text}",
        )

    res_json = resp.json()
    return STTResponse(
        transcript=res_json.get("transcript", "").strip(),
        language_code=res_json.get("language_code", language_code),
    )


@router.post("/translate", response_model=TranslateResponse)
async def translate_text(req: TranslateRequest):
    """Translate text between English and Indian languages using Sarvam API."""
    api_key = get_sarvam_api_key()

    src = normalize_lang_code(req.source_language_code)
    tgt = normalize_lang_code(req.target_language_code)

    # Validate against known languages
    if src not in SUPPORTED_ALL_LANGUAGES and src != "auto":
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported source language: {req.source_language_code}. Supported: {sorted(SUPPORTED_INDIAN_LANGUAGES)} + en-IN",
        )
    if tgt not in SUPPORTED_ALL_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported target language: {req.target_language_code}. Supported: {sorted(SUPPORTED_INDIAN_LANGUAGES)} + en-IN",
        )

    # If source and target are the same language, no need to call external API
    if src == tgt:
        return TranslateResponse(
            translated_text=req.text,
            source_language_code=src,
            target_language_code=tgt,
        )

    payload = {
        "input": req.text,
        "source_language_code": src,
        "target_language_code": tgt,
        "model": "sarvam-translate:v1",
    }
    headers = {
        "api-subscription-key": api_key,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(
                f"{SARVAM_BASE_URL}/translate",
                json=payload,
                headers=headers,
            )
        except Exception as exc:
            logger.error("Sarvam translate network error: %s", exc)
            raise HTTPException(
                status_code=502,
                detail=f"Failed to communicate with Sarvam translation service: {str(exc)}",
            )

    if resp.status_code != 200:
        logger.error("Sarvam translate error %s: %s", resp.status_code, resp.text)
        raise HTTPException(
            status_code=resp.status_code if resp.status_code < 500 else 502,
            detail=f"Sarvam translation failed: {resp.text}",
        )

    res_json = resp.json()
    translated_text = res_json.get("translated_text", "")
    return TranslateResponse(
        translated_text=translated_text,
        source_language_code=src,
        target_language_code=tgt,
    )


@router.post("/tts", response_model=TTSResponse)
async def text_to_speech(req: TTSRequest):
    """Synthesize text into speech using Sarvam Bulbul Text-to-Speech API."""
    api_key = get_sarvam_api_key()

    lang = normalize_lang_code(req.language_code)
    if lang not in SUPPORTED_INDIAN_LANGUAGES and lang != "en-IN":
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported language code for TTS: {req.language_code}. Supported: {sorted(SUPPORTED_INDIAN_LANGUAGES)}",
        )

    # Map requested speaker to valid bulbul:v3 speaker
    raw_spk = req.speaker.lower().strip()
    target_speaker = SPEAKER_MAPPINGS.get(raw_spk, raw_spk)
    if target_speaker not in BULBUL_V3_SPEAKERS:
        target_speaker = "kavya"  # Default pleasant female Indian voice

    clean_text = req.text.strip()
    if len(clean_text) > 2000:
        clean_text = clean_text[:2000]

    payload = {
        "inputs": [clean_text],
        "target_language_code": lang,
        "speaker": target_speaker,
        "model": "bulbul:v3",
        "pace": 1.0,
    }
    headers = {
        "api-subscription-key": api_key,
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.post(
                f"{SARVAM_BASE_URL}/text-to-speech",
                json=payload,
                headers=headers,
            )
        except Exception as exc:
            logger.error("Sarvam TTS network error: %s", exc)
            raise HTTPException(
                status_code=502,
                detail=f"Failed to communicate with Sarvam TTS service: {str(exc)}",
            )

    if resp.status_code != 200:
        logger.error("Sarvam TTS error %s: %s", resp.status_code, resp.text)
        raise HTTPException(
            status_code=resp.status_code if resp.status_code < 500 else 502,
            detail=f"Sarvam TTS failed: {resp.text}",
        )

    res_json = resp.json()
    audios = res_json.get("audios", [])
    if not audios:
        raise HTTPException(status_code=502, detail="No audio returned from Sarvam TTS service.")

    return TTSResponse(
        audio_base64=audios[0],
        audios=audios,
        language_code=lang,
        speaker=target_speaker,
    )


# ─── Backward-compatibility router for /voice/tts ────────────────────────────
voice_router = APIRouter(prefix="/voice", tags=["Voice AI (Legacy Alias)"])

@voice_router.post("/tts")
async def legacy_voice_tts(payload: dict):
    """Legacy compatibility endpoint for /voice/tts."""
    text = payload.get("text", "")
    lang = payload.get("language_code") or payload.get("target_language_code", "hi-IN")
    speaker = payload.get("speaker", "meera")
    return await text_to_speech(TTSRequest(text=text, language_code=lang, speaker=speaker))

