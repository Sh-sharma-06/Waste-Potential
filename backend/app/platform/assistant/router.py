
"""Gemini-powered assistant endpoints."""

import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.config import (
    GEMINI_API_KEY_ADVISOR,
    GEMINI_API_KEY_AUDIT,
    GEMINI_API_KEY_PARSER,
    gemini_models,
)
from app.platform.assistant.prompts import (
    ADVISOR_PROMPT,
    AUDIT_PROMPT,
    PARSER_PROMPT,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/assistant", tags=["AI Assistant"])


class ParseRequest(BaseModel):
    description: str = Field(min_length=3, max_length=5000)


class AdvisorRequest(BaseModel):
    question: str = Field(min_length=3, max_length=5000)
    context: dict[str, Any] = Field(default_factory=dict)


class AuditRequest(BaseModel):
    results: dict[str, Any]
    assumptions: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


def generate_text(
    api_key: str,
    system_prompt: str,
    user_content: str,
    *,
    json_output: bool = False,
) -> str:
    """Call Gemini on the server without exposing API keys to clients."""

    if not api_key:
        raise HTTPException(
            status_code=503,
            detail="This AI assistant feature is not configured.",
        )

    try:
        client = genai.Client(api_key=api_key)

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json" if json_output else "text/plain",
        )

        models = gemini_models()
        for model_name in models:
            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=user_content,
                    config=config,
                )
                break
            except Exception as exc:
                if model_name == models[-1]:
                    raise
                logger.warning("Gemini model %s failed, trying next: %s", model_name, type(exc).__name__)

        answer = response.text
        if not answer or not answer.strip():
            raise HTTPException(
                status_code=502,
                detail="The AI service returned an empty response.",
            )

        return answer.strip()

    except HTTPException:
        raise
    except Exception as exc:
        # Log only the exception type and message, never credentials or user content.
        logger.error(
            "Gemini request failed: %s: %s",
            type(exc).__name__,
            str(exc),
        )
        raise HTTPException(
            status_code=502,
            detail="The AI service could not complete the request. Please try again.",
        ) from None


@router.post("/parse")
def parse_waste(request: ParseRequest):
    """Extract structured waste information from a free-form description."""

    raw = generate_text(
        GEMINI_API_KEY_PARSER,
        PARSER_PROMPT,
        request.description,
        json_output=True,
    )

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=502,
            detail="The AI service returned invalid structured data.",
        ) from None

    required_keys = {
        "waste_type",
        "quantity_kg_per_day",
        "moisture_percent",
        "organic_fraction_percent",
        "location",
        "missing_information",
    }

    if not isinstance(parsed, dict) or not required_keys.issubset(parsed):
        raise HTTPException(
            status_code=502,
            detail="The AI service returned data in an unexpected format.",
        )

    return {
        "status": "ok",
        "data": parsed,
        "note": "AI-extracted values must be checked before scientific use.",
    }


@router.post("/advise")
def advise(request: AdvisorRequest):
    """Explain a question using context supplied by the caller."""

    prompt_content = json.dumps(
        {
            "question": request.question,
            "available_context": request.context,
        },
        ensure_ascii=False,
        default=str,
    )

    answer = generate_text(
        GEMINI_API_KEY_ADVISOR,
        ADVISOR_PROMPT,
        prompt_content,
    )

    return {"status": "ok", "answer": answer}


@router.post("/audit")
def audit(request: AuditRequest):
    """Generate a narrative grounded in supplied results and limitations."""

    prompt_content = json.dumps(
        {
            "scientific_results": request.results,
            "assumptions": request.assumptions,
            "limitations": request.limitations,
        },
        ensure_ascii=False,
        default=str,
    )

    answer = generate_text(
        GEMINI_API_KEY_AUDIT,
        AUDIT_PROMPT,
        prompt_content,
    )

    return {"status": "ok", "report": answer}
