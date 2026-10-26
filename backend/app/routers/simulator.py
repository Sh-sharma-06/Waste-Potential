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

def _gemini_generate(
    api_key: str,
    system_prompt: str,
    contents: str | list,
    *,
    json_output: bool = False,
) -> str:
    """Call Gemini using the specified API key with automatic fallback models."""
    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="Gemini API key is missing or not configured.",
        )

    models_to_try = [
        os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-1.5-flash",
    ]
    # Deduplicate while preserving order
    models_to_try = list(dict.fromkeys(models_to_try))

    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        response_mime_type="application/json" if json_output else "text/plain",
    )

    last_exc = None
    for model_name in models_to_try:
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
            logger.warning("Gemini model %s generation failed: %s", model_name, exc)
            continue

    logger.error("All Gemini models failed. Last error: %s", last_exc)
    raise HTTPException(
        status_code=503,
        detail=f"Gemini service temporarily unavailable: {last_exc}",
    )


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class RecommendRequest(BaseModel):
    location: str = Field(..., description="Location/region of the waste source")
    weight: float = Field(..., description="Waste weight in tonnes")
    weather: str = Field(..., description="Local weather conditions")
    duration_pref: str = Field(..., description="Preferred processing duration")


class RecommendResponse(BaseModel):
    suggested_process: str = Field(..., description="Single optimal process name")


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

RECOMMEND_SYSTEM_PROMPT = (
    "You are an industrial waste-to-energy optimisation AI. Your task is to evaluate seven waste processing methods "
    "(Pyrolysis, Gasification, Anaerobic Digestion, HTC, Composting, Incineration, Pelletization) based on the user's location, "
    "local weather, waste weight (in tonnes), and preferred processing duration.\n"
    "Analyze these inputs and determine the single most optimal process. You must return your response strictly as a valid JSON object "
    'with a single key "suggested_process" containing the exact name of the recommended process. \n'
    "Do not include any markdown formatting, code blocks, explanations, or additional text outside the JSON object.."
)


@router.post(
    "/recommend",
    response_model=RecommendResponse,
    summary="Recommend the single most optimal waste processing method",
)
def recommend_process(request: RecommendRequest) -> dict[str, Any]:
    """Evaluate 7 waste processing methods and return the single optimal process using KEY_RECOMMEND."""
    rec_key, _ = _get_validated_keys()

    user_content = (
        f"Location: {request.location}\n"
        f"Waste weight: {request.weight} tonnes\n"
        f"Local weather: {request.weather}\n"
        f"Preferred duration: {request.duration_pref}"
    )

    raw_response = _gemini_generate(
        api_key=rec_key,
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

    if isinstance(data, dict) and "suggested_process" in data:
        return {"suggested_process": str(data["suggested_process"])}

    return {"suggested_process": str(data)}


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
        api_key=exp_key,
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
