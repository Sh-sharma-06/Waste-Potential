"""Sarvam AI integration router for Speech-to-Text (STT), Translation, and Text-to-Speech (TTS)."""

from __future__ import annotations

import asyncio
import base64
import io
import logging
import os
import re
import wave
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

# Sarvam rejects longer inputs with a 400 validation error, so longer text is chunked.
TTS_MAX_CHARS = 500
TRANSLATE_MAX_CHARS = 2000
# Most text read aloud per request (keeps latency and cost bounded).
TTS_TOTAL_MAX_CHARS = 2000

# Sentence ends (incl. Devanagari danda and double danda) or line breaks.
_SENTENCE_BREAK = re.compile(r"(?<=[.!?।॥])\s+|\n+")


def split_text(text: str, limit: int) -> list[str]:
    """Split text into chunks of at most `limit` chars at sentence, then word, boundaries."""
    pieces: list[str] = []
    for sentence in _SENTENCE_BREAK.split(text):
        sentence = sentence.strip()
        while len(sentence) > limit:
            cut = sentence.rfind(" ", 0, limit + 1)
            if cut <= 0:
                cut = limit
            pieces.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        if sentence:
            pieces.append(sentence)

    chunks: list[str] = []
    for piece in pieces:
        if chunks and len(chunks[-1]) + 1 + len(piece) <= limit:
            chunks[-1] += " " + piece
        else:
            chunks.append(piece)
    return chunks


def split_paragraphs(text: str, limit: int) -> list[tuple[str, str]]:
    """Chunk text for translation, keeping its layout.

    Returns (chunk, separator) pairs: the separator ("\\n" between paragraphs, " " inside a
    paragraph that had to be split, "" at the end) goes after the chunk when reassembling.
    """
    blocks: list[tuple[str, str]] = []
    for paragraph in text.split("\n"):
        parts = ([paragraph] if len(paragraph) <= limit else split_text(paragraph, limit)) or [""]
        blocks.extend((part, " ") for part in parts[:-1])
        blocks.append((parts[-1], "\n"))
    blocks[-1] = (blocks[-1][0], "")

    chunks: list[tuple[str, str]] = []
    for block, sep in blocks:
        if chunks and len(chunks[-1][0]) + len(chunks[-1][1]) + len(block) <= limit:
            prev, prev_sep = chunks[-1]
            chunks[-1] = (prev + prev_sep + block, sep)
        else:
            chunks.append((block, sep))
    return chunks


def concat_wavs(clips_b64: list[str]) -> str:
    """Join base64 WAV clips that share one format (Sarvam returns mono 16-bit PCM)."""
    if len(clips_b64) == 1:
        return clips_b64[0]
    out = io.BytesIO()
    writer: wave.Wave_write | None = None
    for clip in clips_b64:
        with wave.open(io.BytesIO(base64.b64decode(clip))) as reader:
            if writer is None:
                writer = wave.open(out, "wb")
                writer.setparams(reader.getparams())
            writer.writeframes(reader.readframes(reader.getnframes()))
    assert writer is not None
    writer.close()
    return base64.b64encode(out.getvalue()).decode("ascii")


async def _sarvam_post(client: httpx.AsyncClient, path: str, payload: dict, api_key: str, service: str) -> dict:
    """POST JSON to Sarvam; map network and API errors to HTTPExceptions."""
    try:
        resp = await client.post(
            f"{SARVAM_BASE_URL}{path}",
            json=payload,
            headers={"api-subscription-key": api_key, "Content-Type": "application/json"},
        )
    except Exception as exc:
        logger.error("Sarvam %s network error: %s", service, exc)
        raise HTTPException(
            status_code=502,
            detail=f"Failed to communicate with Sarvam {service} service: {str(exc)}",
        )
    if resp.status_code != 200:
        logger.error("Sarvam %s error %s: %s", service, resp.status_code, resp.text)
        raise HTTPException(
            status_code=resp.status_code if resp.status_code < 500 else 502,
            detail=f"Sarvam {service} failed: {resp.text}",
        )
    return resp.json()


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

    async def translate_chunk(client: httpx.AsyncClient, chunk: str) -> str:
        if not chunk.strip():
            return chunk  # blank line between paragraphs
        payload = {
            "input": chunk,
            "source_language_code": src,
            "target_language_code": tgt,
            "model": "sarvam-translate:v1",
        }
        res_json = await _sarvam_post(client, "/translate", payload, api_key, "translation")
        return res_json.get("translated_text", "")

    chunks = split_paragraphs(req.text, TRANSLATE_MAX_CHARS)
    async with httpx.AsyncClient(timeout=30.0) as client:
        translated = await asyncio.gather(*(translate_chunk(client, c) for c, _ in chunks))
    translated_text = "".join(t + sep for t, (_, sep) in zip(translated, chunks))
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

    # Read up to TTS_TOTAL_MAX_CHARS, in whole chunks of at most TTS_MAX_CHARS.
    chunks: list[str] = []
    total = 0
    for chunk in split_text(req.text, TTS_MAX_CHARS):
        if chunks and total + len(chunk) > TTS_TOTAL_MAX_CHARS:
            break
        chunks.append(chunk)
        total += len(chunk)
    if not chunks:
        raise HTTPException(status_code=400, detail="Text to speak is empty.")

    async def synthesize(client: httpx.AsyncClient, chunk: str) -> str:
        payload = {
            "inputs": [chunk],
            "target_language_code": lang,
            "speaker": target_speaker,
            "model": "bulbul:v3",
            "pace": 1.0,
        }
        res_json = await _sarvam_post(client, "/text-to-speech", payload, api_key, "TTS")
        audios = res_json.get("audios", [])
        if not audios:
            raise HTTPException(status_code=502, detail="No audio returned from Sarvam TTS service.")
        return audios[0]

    async with httpx.AsyncClient(timeout=30.0) as client:
        clips = await asyncio.gather(*(synthesize(client, c) for c in chunks))
    audio = concat_wavs(list(clips))

    return TTSResponse(
        audio_base64=audio,
        audios=[audio],
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

