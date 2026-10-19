"""geocode.py — FastAPI router for GET /geocode (Nominatim postal-code lookup).

Endpoint
--------
GET /geocode?pincode=&country=
    Convert a postal code to lat/lng via OpenStreetMap Nominatim.

Validation
----------
* India (country="India", case-insensitive): exactly 6 digits, must not start with 0.
* Other countries: non-empty alphanumeric string, at most 10 characters.

Error mapping
-------------
* Validation failure         → 422
* Nominatim returns no hits  → 404
* Timeout / non-200 / error  → 503
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.geocode_client import (
    GeocodeClientError,
    GeocodeNotFoundError,
    geocode_pincode,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/geocode", tags=["Geocoding"])

# ---------------------------------------------------------------------------
# Validation patterns
# ---------------------------------------------------------------------------

_INDIA_RE = re.compile(r"^[1-9]\d{5}$")           # 6 digits, first digit 1–9
_GENERIC_RE = re.compile(r"^[A-Za-z0-9]{1,10}$")  # alphanumeric, 1–10 chars


def _validate_pincode(pincode: str, country: str) -> None:
    """Raise HTTPException(422) if the pincode fails country-specific rules."""
    if country.strip().lower() == "india":
        if not _INDIA_RE.match(pincode):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Invalid Indian pincode {pincode!r}. "
                    "Must be exactly 6 digits and must not start with 0."
                ),
            )
    else:
        if not _GENERIC_RE.match(pincode):
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Invalid pincode {pincode!r}. "
                    "Must be a non-empty alphanumeric string of at most 10 characters."
                ),
            )


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

class GeocodeResponse(BaseModel):
    """Geocoded location derived from a postal code."""

    lat: float = Field(..., description="Decimal latitude.")
    lng: float = Field(..., description="Decimal longitude.")
    display_name: str = Field(..., description="Human-readable location name from Nominatim.")
    precision: str = Field(
        default="postal-code area centroid, approximate",
        description="Precision statement for the returned coordinates.",
    )
    source: str = Field(
        default="OpenStreetMap Nominatim (ODbL)",
        description="Data source and licence.",
    )
    cached: bool = Field(..., description="True if the result was served from the in-memory cache.")


# ---------------------------------------------------------------------------
# GET /geocode
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=GeocodeResponse,
    summary="Geocode a postal code to lat/lng",
    responses={
        404: {"description": "No result found for the given pincode and country."},
        422: {"description": "Pincode fails country-specific validation rules."},
        503: {"description": "Nominatim is unreachable, timed out, or returned an error."},
    },
)
def geocode(
    pincode: str = Query(..., description="Postal / PIN code to geocode."),
    country: str = Query("India", description="Country name (default: India)."),
) -> GeocodeResponse:
    """Convert a postal code to approximate lat/lng coordinates via Nominatim.

    For India the pincode must be exactly 6 digits and must not start with 0.
    For other countries a non-empty alphanumeric string of at most 10 characters
    is accepted.

    Results are cached in memory (24 h TTL, up to 500 entries).  Outbound calls
    are rate-limited to at most one per 1.1 s in compliance with Nominatim's
    public-usage policy.
    """
    _validate_pincode(pincode, country)

    try:
        result = geocode_pincode(pincode=pincode, country=country)
    except GeocodeNotFoundError as exc:
        logger.info("Geocode not found: pincode=%r country=%r", pincode, country)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except GeocodeClientError as exc:
        logger.warning("Geocode client error: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    logger.info(
        "geocode: pincode=%r country=%r lat=%.6f lng=%.6f cached=%s",
        pincode,
        country,
        result.lat,
        result.lng,
        result.cached,
    )
    return GeocodeResponse(
        lat=result.lat,
        lng=result.lng,
        display_name=result.display_name,
        cached=result.cached,
    )
