"""vision_router.py — POST /vision/classify and POST /vision/advice.

Provides two endpoints that let urban and rural users upload a waste photo and
receive classification and contextual advice via Gemini.

Design follows app/platform/assistant/router.py:
  - genai.Client(api_key=...) constructed per request (no module-level state).
  - API key from environment via app.config (never in source).
  - Model name from GEMINI_MODEL env var (default "gemini-2.5-flash").
  - Image bytes are NEVER stored or logged; only size and MIME type are logged.

Error mapping
-------------
  - Missing key / API failure  → 503
  - Malformed / missing JSON   → 502
  - Bad upload / bad sector    → 422
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, File, HTTPException, UploadFile
from google import genai
from google.genai import types
from pydantic import BaseModel, Field, ValidationError, model_validator

from app.config import get_setting

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vision", tags=["Vision"])

# ---------------------------------------------------------------------------
# Configuration (env-driven, following the existing assistant pattern)
# ---------------------------------------------------------------------------

_GEMINI_MODEL = get_setting("GEMINI_MODEL", "gemini-2.5-flash")
_GEMINI_API_KEY_VISION = get_setting("GEMINI_API_KEY_VISION")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAX_BYTES = 5 * 1024 * 1024          # 5 MB
_ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}

# Magic-byte signatures for each allowed image type.
# We check the first few bytes of the upload so a text file renamed .jpg is rejected.
_MAGIC: list[tuple[bytes, str]] = [
    (b"\xff\xd8\xff", "image/jpeg"),          # JPEG
    (b"\x89PNG\r\n\x1a\n", "image/png"),      # PNG
    (b"RIFF", "image/webp"),                   # WebP (RIFF....WEBP)
]


def _detect_mime(data: bytes) -> str | None:
    """Return the detected MIME type from *data*'s magic bytes, or None."""
    for magic, mime in _MAGIC:
        if data[:len(magic)] == magic:
            # Extra check for WebP: bytes 8-12 must be b"WEBP"
            if mime == "image/webp" and data[8:12] != b"WEBP":
                continue
            return mime
    return None

VALID_CATEGORIES = frozenset({
    "organic", "plastic", "metal", "glass",
    "paper", "e_waste", "hazardous", "other",
})

# Organic categories drive the server-side stream derivation.
_ORGANIC_CATEGORIES = frozenset({"organic"})

_CLASSIFY_DISCLAIMER = (
    "AI classification from a photo; it does not measure mass. "
    "Please correct any label."
)

# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

_CLASSIFY_SYSTEM = """
You are a waste classification assistant.

Analyse the supplied image and return ONLY a JSON object with this exact structure:
{
  "items": [
    {"label": "<descriptive label>", "category": "<category>", "confidence": <0..1>}
  ]
}

Allowed categories (use exactly): organic, plastic, metal, glass, paper, e_waste, hazardous, other.
confidence must be a number between 0 and 1.
Return ONLY valid JSON. No prose, no markdown fences, no extra keys.
"""

_ADVICE_SYSTEM_URBAN = """
You are a waste-management advisor for urban households and communities.

Give short, practical guidance on what to do with the listed waste items.
Focus on: selling as scrap, DIY reuse, donating, and home composting.

Rules (NEVER violate):
1. Do NOT include any numbers, prices, yields, or quantities.
2. Do NOT include commands to burn waste.
3. End every response with: "Follow your local municipal waste rules."
4. Keep the response concise (5–8 bullet points maximum).
"""

_ADVICE_SYSTEM_RURAL = """
You are a waste-management advisor for rural farms and villages.

Give short, practical guidance on what to do with the listed waste items.
Focus on: crop residue management, farm biogas, biochar production, and composting.

Rules (NEVER violate):
1. Do NOT include any numbers, prices, yields, or quantities.
2. Do NOT include commands to burn waste.
3. End every response with: "Follow your local municipal waste rules."
4. Keep the response concise (5–8 bullet points maximum).
"""

_ADVICE_PROMPTS: dict[str, str] = {
    "urban": _ADVICE_SYSTEM_URBAN,
    "rural": _ADVICE_SYSTEM_RURAL,
}

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class WasteItem(BaseModel):
    label: str
    category: str
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _check_category(self) -> "WasteItem":
        if self.category not in VALID_CATEGORIES:
            raise ValueError(
                f"category {self.category!r} is not one of {sorted(VALID_CATEGORIES)}"
            )
        return self


class ClassifyResponse(BaseModel):
    items: list[WasteItem]
    stream: str                  # "organic" | "non_organic"
    model: str
    timestamp: str
    disclaimer: str


class AdviceRequest(BaseModel):
    sector: Literal["urban", "rural"] = "urban"
    items: list[str] = Field(default_factory=list)
    waste_type: str | None = None


class AdviceResponse(BaseModel):
    text: str


# ---------------------------------------------------------------------------
# Gemini helper (mirrors generate_text from assistant/router.py)
# ---------------------------------------------------------------------------

def _gemini_generate(
    api_key: str,
    system_prompt: str,
    contents: list,
    *,
    json_output: bool = False,
) -> str:
    """Call Gemini and return the response text.

    Parameters
    ----------
    api_key:
        Gemini API key.
    system_prompt:
        System instruction for the model.
    contents:
        List of ``types.Part`` instances passed as the user turn.
    json_output:
        When True, requests application/json MIME type.

    Raises
    ------
    HTTPException(503)
        If the key is missing or the API call fails.
    HTTPException(502)
        If the model returns an empty response.
    """
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Vision AI feature is not configured (GEMINI_API_KEY_VISION missing).",
        )

    try:
        client = genai.Client(api_key=api_key)
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json" if json_output else "text/plain",
        )
        response = client.models.generate_content(
            model=_GEMINI_MODEL,
            contents=contents,
            config=config,
        )
        text = response.text
        if not text or not text.strip():
            raise HTTPException(
                status_code=502,
                detail="The AI service returned an empty response.",
            )
        return text.strip()

    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Gemini vision request failed: %s: %s",
            type(exc).__name__,
            str(exc),
        )
        raise HTTPException(
            status_code=503,
            detail="Vision AI service unavailable. Please try again.",
        ) from None


# ---------------------------------------------------------------------------
# Stream derivation (server-side; never trust Gemini for this)
# ---------------------------------------------------------------------------

def _derive_stream(items: list[WasteItem]) -> str:
    """Return 'organic' if any item is in an organic category, else 'non_organic'."""
    for item in items:
        if item.category in _ORGANIC_CATEGORIES:
            return "organic"
    return "non_organic"


# ---------------------------------------------------------------------------
# POST /vision/classify
# ---------------------------------------------------------------------------

@router.post(
    "/classify",
    response_model=ClassifyResponse,
    summary="Classify waste from a photo",
    responses={
        422: {"description": "File too large, wrong MIME type, or bad upload."},
        502: {"description": "Gemini returned malformed JSON."},
        503: {"description": "Gemini key missing or API failure."},
    },
)
async def classify_waste(
    file: Annotated[UploadFile, File(description="JPEG, PNG or WebP image, max 5 MB.")],
) -> ClassifyResponse:
    """Classify waste items in the uploaded image using Gemini vision."""

    # --- Validate MIME type before reading bytes ---
    content_type = (file.content_type or "").lower().split(";")[0].strip()
    if content_type not in _ALLOWED_MIME:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Unsupported image type {content_type!r}. "
                f"Allowed: jpeg, png, webp."
            ),
        )

    image_bytes = await file.read()
    size_kb = len(image_bytes) / 1024
    logger.info(
        "classify_waste: received %s %.1f KB",
        content_type,
        size_kb,
    )

    if len(image_bytes) > _MAX_BYTES:
        raise HTTPException(
            status_code=422,
            detail=f"Image exceeds 5 MB limit ({len(image_bytes) / 1_048_576:.1f} MB).",
        )

    # --- Validate by magic bytes (content-type alone is not trusted) ---
    detected = _detect_mime(image_bytes)
    if detected is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "File content does not match a supported image format "
                "(JPEG, PNG or WebP). "
                "Ensure the file is a real image, not a renamed text or binary file."
            ),
        )

    # --- Call Gemini (image + text prompt) ---
    # Use the magic-byte detected type so the MIME sent to Gemini is always accurate.
    image_part = types.Part.from_bytes(data=image_bytes, mime_type=detected)
    text_part = types.Part.from_text(
        text="Classify every distinct waste item visible in this image."
    )

    raw = _gemini_generate(
        _GEMINI_API_KEY_VISION,
        _CLASSIFY_SYSTEM,
        [image_part, text_part],
        json_output=True,
    )

    # --- Parse and validate Gemini's JSON ---
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("classify_waste: Gemini returned non-JSON: %.200s", raw)
        raise HTTPException(
            status_code=502,
            detail="AI classification returned invalid JSON.",
        ) from None

    if not isinstance(parsed, dict) or "items" not in parsed:
        logger.warning("classify_waste: Gemini response missing 'items' key")
        raise HTTPException(
            status_code=502,
            detail="AI classification response is missing the 'items' key.",
        )

    try:
        items = [WasteItem(**item) for item in parsed["items"]]
    except (ValidationError, TypeError, KeyError) as exc:
        logger.warning("classify_waste: Gemini item validation failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=f"AI classification returned an invalid item structure: {exc}",
        ) from None

    stream = _derive_stream(items)
    logger.info(
        "classify_waste: %d items, stream=%s",
        len(items),
        stream,
    )

    return ClassifyResponse(
        items=items,
        stream=stream,
        model=_GEMINI_MODEL,
        timestamp=datetime.now(UTC).isoformat(),
        disclaimer=_CLASSIFY_DISCLAIMER,
    )


# ---------------------------------------------------------------------------
# POST /vision/advice
# ---------------------------------------------------------------------------

@router.post(
    "/advice",
    response_model=AdviceResponse,
    summary="Get disposal advice for classified waste items",
    responses={
        422: {"description": "Unknown sector."},
        503: {"description": "Gemini key missing or API failure."},
    },
)
def give_advice(request: AdviceRequest) -> AdviceResponse:
    """Return short, contextual waste-disposal guidance for the given sector."""
    sector = request.sector or "urban"
    system_prompt = _ADVICE_PROMPTS.get(sector, _ADVICE_SYSTEM_URBAN)
    item_list = request.items if request.items else ([request.waste_type] if request.waste_type else ["waste item"])
    user_content = (
        f"Sector: {sector}\n"
        f"Waste items identified:\n"
        + "\n".join(f"- {label}" for label in item_list)
    )

    text = _gemini_generate(
        _GEMINI_API_KEY_VISION,
        system_prompt,
        [types.Part.from_text(text=user_content)],
    )
    return AdviceResponse(text=text)


from fastapi import UploadFile, File, HTTPException
from transformers import pipeline
from PIL import Image
import io
import os

# 1. Point to the local model folder
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.path.join(BASE_DIR, "ml", "vision", "waste-classification-model")

# 2. Load the Hugging Face model into memory when the server starts
try:
    local_classifier = pipeline("image-classification", model=MODEL_PATH, image_processor=MODEL_PATH)
    print("✅ Local ML Model loaded successfully!")
except Exception as e:
    print(f"⚠️ Local model not loaded: {e}")
    local_classifier = None

# 3. Create the new endpoint
@router.post("/classify-local")
@router.post("/vision/classify-local")
async def classify_local_image(file: UploadFile = File(...)):
    if not local_classifier:
        raise HTTPException(status_code=500, detail="Local ML model not loaded.")
    
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Upload a valid image file.")

    # Read and convert image
    image_bytes = await file.read()
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    # Run local inference
    predictions = local_classifier(image)
    
    # Format the output for the frontend
    results = [
        {"class": p["label"], "confidence": round(p["score"] * 100, 2)}
        for p in predictions
    ]

    return {"filename": file.filename, "detections": results}

