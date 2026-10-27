"""explain_router.py — POST /pathways/explain.

"Why choose this process?" narrative for a single pathway.

Flow
----
1. Validate: pathway must exist in the supplied results list → 422 otherwise.
2. Build FACTS from the matching PathwayResult row + other pathways' optimality_share.
3. Call Gemini with a strictly-grounded system prompt.
4. Run the numeric grounding guard: every number Gemini mentions must match a FACTS
   value within 1 %.  If any number is unsupported → fall back to the template.
5. Missing key or API failure also falls back to the template (never a 500).
6. Return ExplainResponse (text, grounded, unsupported_numbers, source, facts, disclaimer).

Mirrors the pattern in app/platform/assistant/router.py:
  - genai.Client(api_key=...) per request, key from env, never in source.
  - Model order from app.config.gemini_models() (GEMINI_MODEL, then fallbacks).
  - Only sizes and status are logged; no content logged.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.config import gemini_models, get_setting
from app.pathways.explain_service import build_template, check_grounding

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/pathways", tags=["Pathways Screening"])

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_GEMINI_API_KEY_EXPLAIN = (
    get_setting("GEMINI_API_KEY_EXPLAIN")
    or get_setting("GEMINI_API_KEY_ADVISOR")   # fallback when dedicated key is absent
)

_EXPLAIN_DISCLAIMER = "Modelled estimate, not a validated prediction"

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

_EXPLAIN_SYSTEM = """\
You are a waste-management advisor explaining a single treatment pathway ranking.

Explain in at most 4 sentences why this pathway ranks where it does.
Use ONLY numbers that appear in the FACTS object provided.
Do not invent numbers, prices or yields.
Say explicitly that the ranking depends on assumed price and cost distributions \
and is not validated.
Do not call thermal output (energy_basis thermal) electricity — use "thermal output" instead.
"""

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class PathwayRowInput(BaseModel):
    """Minimal projection of a PathwayResult sufficient for the explain endpoint.

    All fields are optional so the caller can pass the raw compare response
    without filtering; unknown keys are ignored.
    """

    pathway: str
    feasible: bool = True
    reasons: list[str] = Field(default_factory=list)
    e_net_kwh_d: float = 0.0
    annual_net_value_inr: float = 0.0
    primary_product: Optional[str] = None
    energy_basis: Optional[str] = None
    optimality_share: Optional[float] = None
    warnings: list[str] = Field(default_factory=list)
    # Accept any extra keys (outputs, model_status, etc.) without error
    model_config = {"extra": "allow"}


class ExplainRequest(BaseModel):
    pathway: str = Field(..., description="Pathway identifier to explain.")
    results: list[PathwayRowInput] = Field(
        ..., min_length=1, description="List returned by POST /pathways/compare."
    )


class ExplainResponse(BaseModel):
    text: str
    grounded: bool
    unsupported_numbers: list[float]
    source: str                  # "gemini" | "template"
    facts: dict[str, Any]
    disclaimer: str


# ---------------------------------------------------------------------------
# FACTS builder
# ---------------------------------------------------------------------------

def _build_facts(row: PathwayRowInput, all_rows: list[PathwayRowInput]) -> dict[str, Any]:
    """Extract the FACTS dict from *row* plus peer optimality shares."""
    peer_shares: dict[str, Optional[float]] = {
        r.pathway: r.optimality_share
        for r in all_rows
        if r.pathway != row.pathway
    }
    return {
        "pathway": row.pathway,
        "feasible": row.feasible,
        "reasons": row.reasons,
        "e_net_kwh_d": row.e_net_kwh_d,
        "annual_net_value_inr": row.annual_net_value_inr,
        "primary_product": row.primary_product,
        "energy_basis": row.energy_basis,
        "optimality_share": row.optimality_share,
        "warnings": row.warnings,
        "peer_optimality_shares": peer_shares,
    }


# ---------------------------------------------------------------------------
# Gemini call (mirrors generate_text in assistant/router.py)
# ---------------------------------------------------------------------------

def _call_gemini(api_key: str, facts: dict[str, Any]) -> str:
    """Call Gemini and return the stripped text.

    Raises
    ------
    Exception
        Any failure (missing key, network, empty response) is re-raised so the
        caller can fall back to the template.
    """
    if not api_key:
        raise ValueError("GEMINI_API_KEY_EXPLAIN is not set.")

    client = genai.Client(api_key=api_key)
    config = types.GenerateContentConfig(
        system_instruction=_EXPLAIN_SYSTEM,
        response_mime_type="text/plain",
    )
    user_content = (
        "FACTS:\n"
        + json.dumps(facts, ensure_ascii=False, default=str)
        + "\n\nExplain why this pathway ranks where it does."
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
    text = response.text
    if not text or not text.strip():
        raise ValueError("Gemini returned an empty response.")
    return text.strip()


# ---------------------------------------------------------------------------
# POST /pathways/explain
# ---------------------------------------------------------------------------

@router.post(
    "/explain",
    response_model=ExplainResponse,
    summary="Explain why a pathway ranks where it does",
    responses={
        422: {"description": "Pathway not found in the supplied results list."},
    },
)
def explain_pathway(request: ExplainRequest) -> ExplainResponse:
    """Return a short narrative explaining the ranking of a single pathway.

    Gemini's answer is numerically grounded against a FACTS dict built
    server-side from the matching PathwayResult row.  If any number invented
    by Gemini cannot be matched to FACTS within 1 %, the template is returned
    instead.  API failures and missing keys also fall back to the template.
    """
    # --- 1. Validate pathway is in results ---
    row = next((r for r in request.results if r.pathway == request.pathway), None)
    if row is None:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Pathway {request.pathway!r} is not in the supplied results list. "
                f"Available: {[r.pathway for r in request.results]}"
            ),
        )

    # --- 2. Build FACTS ---
    facts = _build_facts(row, request.results)

    # --- 3. Try Gemini ---
    text: Optional[str] = None
    try:
        text = _call_gemini(_GEMINI_API_KEY_EXPLAIN, facts)
    except Exception as exc:
        logger.warning(
            "explain_pathway: Gemini unavailable for %r, using template: %s",
            request.pathway,
            type(exc).__name__,
        )

    # --- 4. Grounding check ---
    if text is not None:
        grounded, unsupported = check_grounding(text, facts)
        if not grounded:
            logger.info(
                "explain_pathway: grounding failed for %r — unsupported numbers: %s",
                request.pathway,
                unsupported,
            )
            text = None  # fall through to template
        else:
            return ExplainResponse(
                text=text,
                grounded=True,
                unsupported_numbers=[],
                source="gemini",
                facts=facts,
                disclaimer=_EXPLAIN_DISCLAIMER,
            )

    # --- 5. Template fallback ---
    template_text = build_template(request.pathway, facts)
    _unsupported = unsupported if text is None and "unsupported" in dir() else []  # type: ignore[possibly-undefined]

    return ExplainResponse(
        text=template_text,
        grounded=False,
        unsupported_numbers=_unsupported,
        source="template",
        facts=facts,
        disclaimer=_EXPLAIN_DISCLAIMER,
    )
