"""simulator.py — Process recommendation and on-demand AI explanation router.

Endpoints:
  - POST /simulator/recommend: Uses GEMINI_API_KEY_RECOMMEND to evaluate 7 waste processing
    methods and return the single most optimal process strictly in JSON.
  - POST /simulator/process-details: Uses GEMINI_API_KEY_EXPLAIN to generate deep technical
    briefing, pros/cons/precautions, and comparative analysis in Markdown.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.config import gemini_models
from app.services.geocode_client import GeocodeClientError, GeocodeNotFoundError, geocode_pincode
from app.services.weather_client import WeatherClientError, get_current_weather

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/simulator", tags=["Simulator"])

# ---------------------------------------------------------------------------
# API Key Configuration
# ---------------------------------------------------------------------------

KEY_RECOMMEND: Optional[str] = os.getenv("GEMINI_API_KEY_RECOMMEND")
KEY_EXPLAIN: Optional[str] = os.getenv("GEMINI_API_KEY_EXPLAIN")


def _get_validated_keys() -> tuple[str, str]:
    """Retrieve and validate that both required Gemini API keys are configured.

    Raises:
        HTTPException(503): If either KEY_RECOMMEND or KEY_EXPLAIN is missing.
    """
    rec = KEY_RECOMMEND if KEY_RECOMMEND is not None else os.getenv("GEMINI_API_KEY_RECOMMEND")
    exp = KEY_EXPLAIN if KEY_EXPLAIN is not None else os.getenv("GEMINI_API_KEY_EXPLAIN")

    if not rec or not exp:
        raise HTTPException(
            status_code=503,
            detail="Simulator AI service is not configured (GEMINI_API_KEY_RECOMMEND or GEMINI_API_KEY_EXPLAIN missing).",
        )
    return rec, exp


# ---------------------------------------------------------------------------
# Gemini Generation Helper
# ---------------------------------------------------------------------------

# Other configured keys the recommendation may borrow when its own project is out of credit or quota.
_BACKUP_KEY_NAMES = (
    "GEMINI_API_KEY_EXPLAIN",
    "GEMINI_API_KEY_ADVISOR",
    "GEMINI_API_KEY_AUDIT",
    "GEMINI_API_KEY_PARSER",
    "GEMINI_API_KEY_VISION",
)


def _with_backup_keys(primary: str) -> list[str]:
    """`primary` first, then every other configured Gemini key, without duplicates or blanks."""
    keys = [primary, *(os.getenv(name, "").strip() for name in _BACKUP_KEY_NAMES)]
    return [k for k in dict.fromkeys(keys) if k]


def _is_out_of_credit(exc: Exception) -> bool:
    """402: the key's project has no prepaid credit, so every model on that key will fail."""
    msg = str(exc)
    return "402" in msg or "prepayment credits are depleted" in msg.lower()


def _gemini_generate(
    api_keys: str | list[str],
    system_prompt: str,
    contents: str | list,
    *,
    json_output: bool = False,
) -> str:
    """Call Gemini, falling back across models and then across the given keys."""
    keys = [api_keys] if isinstance(api_keys, str) else api_keys
    keys = [k for k in keys if k]
    if not keys:
        raise HTTPException(
            status_code=503,
            detail="Gemini API key is missing or not configured.",
        )

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        response_mime_type="application/json" if json_output else "text/plain",
    )

    last_exc = None
    for key_index, api_key in enumerate(keys):
        client = genai.Client(api_key=api_key)
        for model_name in gemini_models():
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=contents,
                    config=config,
                )
                text = response.text
                if text and text.strip():
                    return text.strip()
            except Exception as exc:
                last_exc = exc
                logger.warning("Gemini key #%d model %s failed: %s", key_index + 1, model_name, exc)
                if _is_out_of_credit(exc):
                    break  # same result for every model on this key; try the next key

    logger.error("All Gemini keys and models failed. Last error: %s", last_exc)
    raise HTTPException(
        status_code=503,
        detail=f"Gemini service temporarily unavailable: {last_exc}",
    )


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class RecommendRequest(BaseModel):
    location: str = Field(..., description="Location/region of the waste source")
    weight: float = Field(..., gt=0, description="Waste weight in tonnes per day")
    category: Optional[str] = Field(None, description="Waste category: 'energy' or 'non-energy'")
    pincode: Optional[str] = Field(None, description="Indian PIN code, used to look up live weather")
    lat: Optional[float] = Field(None, ge=-90, le=90)
    lng: Optional[float] = Field(None, ge=-180, le=180)
    weather: Optional[str] = Field(None, description="Override; live weather is looked up when omitted")
    duration_pref: str = Field("No preference", description="Preferred processing duration")


class RecommendResponse(BaseModel):
    suggested_process: str = Field(..., description="Display name of the single optimal process")
    process_id: str = Field(..., description="Canonical pathway id, e.g. 'htc'")
    weather_used: str = Field(..., description="Weather description given to the model")


class ProcessDetailsRequest(BaseModel):
    location: str = Field(..., description="Location of the waste operation")
    weight: float = Field(..., description="Waste weight in tonnes")
    target_process: str = Field(..., description="Method currently being evaluated")
    suggested_process: str = Field(..., description="Optimal recommendation for comparison")
    weather: Optional[str] = Field("ambient", description="Local weather conditions")


class ProcessDetailsResponse(BaseModel):
    details: str = Field(..., description="Markdown briefing and technical comparison")
    explanation: str = Field(..., description="Alias for details")
    markdown: str = Field(..., description="Alias for details")
    target_process: str
    suggested_process: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

# The seven pathways modelled by the simulator, keyed by canonical id.
PROCESS_NAMES: dict[str, str] = {
    "pyrolysis": "Pyrolysis",
    "gasification": "Gasification",
    "anaerobic_digestion": "Anaerobic Digestion",
    "htc": "Hydrothermal Carbonisation (HTC)",
    "composting": "Composting",
    "incineration": "Incineration",
    "torrefaction": "Torrefaction",
}

# Checked in order: torrefaction before pyrolysis, since models often call it "mild pyrolysis".
_PROCESS_KEYWORDS: list[tuple[str, str]] = [
    ("torref", "torrefaction"),
    ("hydrothermal", "htc"),
    ("htc", "htc"),
    ("anaerobic", "anaerobic_digestion"),
    ("digest", "anaerobic_digestion"),
    ("biogas", "anaerobic_digestion"),
    ("gasif", "gasification"),
    ("pyro", "pyrolysis"),
    ("compost", "composting"),
    ("incinerat", "incineration"),
    ("mass burn", "incineration"),
]

CATEGORY_DESCRIPTIONS: dict[str, str] = {
    "energy": "energy-recoverable stream (mixed organics, biomass and combustible municipal/industrial waste)",
    "non-energy": "non-energy-recoverable stream (mostly recyclables and inerts; only residual organics/combustibles "
                  "are available for conversion)",
}


def normalize_process_id(text: str) -> Optional[str]:
    """Map a process name or id returned by the model to a canonical pathway id."""
    s = (text or "").strip().lower().replace("-", " ").replace("_", " ")
    for pid, name in PROCESS_NAMES.items():
        if s in (pid.replace("_", " "), name.lower()):
            return pid
    for keyword, pid in _PROCESS_KEYWORDS:
        if keyword in s:
            return pid
    return None


def _resolve_weather(request: RecommendRequest) -> str:
    """Explicit weather wins; otherwise live Open-Meteo conditions at lat/lng (geocoded from PIN if needed)."""
    if request.weather and request.weather.strip():
        return request.weather.strip()
    lat, lng = request.lat, request.lng
    if (lat is None or lng is None) and request.pincode:
        try:
            g = geocode_pincode(pincode=request.pincode, country="India")
            lat, lng = g.lat, g.lng
        except (GeocodeClientError, GeocodeNotFoundError) as exc:
            logger.warning("Recommend: geocode failed for PIN %s: %s", request.pincode, exc)
    if lat is not None and lng is not None:
        try:
            w = get_current_weather(latitude=lat, longitude=lng)
            return f"{w.ambient_temp_c:.1f}°C, {w.relative_humidity * 100:.0f}% relative humidity (live, Open-Meteo)"
        except WeatherClientError as exc:
            logger.warning("Recommend: weather lookup failed: %s", exc)
    return "unknown (live weather unavailable)"


RECOMMEND_SYSTEM_PROMPT = (
    "You are an industrial waste-to-energy optimisation AI. Evaluate exactly these seven waste processing pathways: "
    + ", ".join(f"{name} [id: {pid}]" for pid, name in PROCESS_NAMES.items())
    + ".\nWeigh the waste category, daily tonnage (scale suitability and capital intensity), local climate "
    "(temperature and humidity affect feedstock moisture, drying load and biological process rates) and the "
    "operator's preferred processing duration. If the duration preference is 'No preference', do not let "
    "processing time drive the choice.\n"
    'Choose the single most optimal pathway. Return strictly a JSON object with one key "suggested_process" '
    "whose value is the id of the chosen pathway (one of: " + ", ".join(PROCESS_NAMES) + "). "
    "No markdown, code blocks or additional text."
)


@router.post(
    "/recommend",
    response_model=RecommendResponse,
    summary="Recommend the single most optimal waste processing method",
)
def recommend_process(request: RecommendRequest) -> dict[str, Any]:
    """Evaluate the 7 simulator pathways and return the single optimal one using KEY_RECOMMEND."""
    rec_key, _ = _get_validated_keys()

    weather = _resolve_weather(request)
    category = CATEGORY_DESCRIPTIONS.get(
        (request.category or "").strip().lower(), request.category or "unspecified mixed waste"
    )
    user_content = (
        f"Location: {request.location}\n"
        f"Waste category: {category}\n"
        f"Waste quantity: {request.weight} tonnes per day\n"
        f"Local weather: {weather}\n"
        f"Preferred processing duration: {request.duration_pref}"
    )

    raw_response = _gemini_generate(
        api_keys=_with_backup_keys(rec_key),
        system_prompt=RECOMMEND_SYSTEM_PROMPT,
        contents=user_content,
        json_output=True,
    )

    try:
        data = json.loads(raw_response)
    except json.JSONDecodeError:
        cleaned = raw_response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        try:
            data = json.loads(cleaned)
        except Exception:
            data = {"suggested_process": cleaned}

    raw = str(data["suggested_process"]) if isinstance(data, dict) and "suggested_process" in data else str(data)
    process_id = normalize_process_id(raw)
    if process_id is None:
        logger.warning("Recommend: model returned unrecognised process %r", raw)
        raise HTTPException(status_code=502, detail=f"AI returned an unrecognised process: {raw[:80]}")

    return {
        "suggested_process": PROCESS_NAMES[process_id],
        "process_id": process_id,
        "weather_used": weather,
    }


@router.post(
    "/process-details",
    response_model=ProcessDetailsResponse,
    summary="Generate on-demand technical briefing and comparative evaluation",
)
def process_details(request: ProcessDetailsRequest) -> dict[str, Any]:
    """Generate technical briefing and comparison using KEY_EXPLAIN in Markdown format."""
    _, exp_key = _get_validated_keys()

    weather_desc = request.weather or "ambient"
    system_prompt = (
        f"You are an expert industrial waste-to-energy advisor. The user is evaluating the '{request.target_process}' "
        f"method for their waste management in {request.location} (handling {request.weight} tonnes, under {weather_desc} conditions). "
        f"The system's optimal recommendation for this specific scenario is '{request.suggested_process}'.\n\n"
        f"Based on this, generate a highly technical but accessible briefing:\n\n"
        f"1. If '{request.target_process}' matches '{request.suggested_process}': \n"
        f"Explain exactly why it is the optimal fit for their specific location, weight, and climate. Detail its Technical Pros, Operational Cons, and crucial Safety/Execution Precautions.\n\n"
        f"2. If '{request.target_process}' DOES NOT match '{request.suggested_process}': \n"
        f"Detail the Technical Pros, Operational Cons, and Precautions of '{request.target_process}'. Then, provide a direct, technical comparison explaining exactly why it was NOT chosen over the '{request.suggested_process}' (e.g., efficiency loss, weather incompatibility, financial scale mismatch).\n\n"
        f"Format your response in clean, highly readable Markdown using headings (##), bullet points, and bold text for emphasis. Be concise and actionable.\n"
        f"  Format the response in clean Markdown with clear headings."
    )

    user_content = (
        f"Evaluate the waste processing method '{request.target_process}' "
        f"against suggested '{request.suggested_process}' for {request.weight} tonnes in {request.location}."
    )

    markdown_text = _gemini_generate(
        api_keys=exp_key,
        system_prompt=system_prompt,
        contents=user_content,
        json_output=False,
    )

    return {
        "details": markdown_text,
        "explanation": markdown_text,
        "markdown": markdown_text,
        "target_process": request.target_process,
        "suggested_process": request.suggested_process,
    }
