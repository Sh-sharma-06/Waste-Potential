"""external.py — FastAPI router for live external-data endpoints (P3 scope).

Endpoints
---------
GET /weather
    Fetch current ambient temperature and relative humidity for a lat/lon via
    the Open-Meteo API (no key required).

GET /facilities
    Search for nearby waste treatment / recycling facilities via the Google
    Places API.  Requires GOOGLE_PLACES_API_KEY in the environment.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.places_client import PlacesClientError, search_nearby_facilities
from app.services.weather_client import WeatherClientError, get_current_weather

logger = logging.getLogger(__name__)

router = APIRouter(tags=["External Data"])


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class WeatherResponse(BaseModel):
    """Current ambient conditions at the requested coordinates."""

    latitude: float = Field(..., description="Latitude echoed from Open-Meteo.")
    longitude: float = Field(..., description="Longitude echoed from Open-Meteo.")
    ambient_temp_c: float = Field(..., description="Air temperature at 2 m (°C).")
    relative_humidity: float = Field(
        ..., description="Relative humidity as a fraction [0, 1]."
    )


class FacilityResponse(BaseModel):
    """A single waste treatment / recycling facility returned by Google Places."""

    place_id: str = Field(..., description="Unique Google Place ID.")
    name: str = Field(..., description="Display name of the facility.")
    vicinity: str = Field(..., description="Short address / neighbourhood.")
    latitude: float = Field(..., description="Decimal latitude.")
    longitude: float = Field(..., description="Decimal longitude.")
    types: list[str] = Field(
        default_factory=list, description="Google place type labels."
    )


# ---------------------------------------------------------------------------
# GET /weather
# ---------------------------------------------------------------------------

@router.get(
    "/weather",
    response_model=WeatherResponse,
    summary="Get current ambient weather for a location",
    responses={
        503: {"description": "Open-Meteo is unreachable or returned an error."},
    },
)
def get_weather(
    lat: float = Query(..., description="Decimal latitude (−90 to 90)."),
    lon: float = Query(..., description="Decimal longitude (−180 to 180)."),
) -> WeatherResponse:
    """Return the latest hourly ambient temperature and relative humidity
    from Open-Meteo for the supplied coordinates.
    """
    try:
        reading = get_current_weather(latitude=lat, longitude=lon)
    except WeatherClientError as exc:
        logger.warning("Weather fetch failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return WeatherResponse(
        latitude=reading.latitude,
        longitude=reading.longitude,
        ambient_temp_c=reading.ambient_temp_c,
        relative_humidity=reading.relative_humidity,
    )


# ---------------------------------------------------------------------------
# GET /facilities
# ---------------------------------------------------------------------------

@router.get(
    "/facilities",
    response_model=list[FacilityResponse],
    summary="Search for nearby waste facilities via Google Places",
    responses={
        503: {
            "description": (
                "Google Places is unreachable, the API key is missing / invalid, "
                "or the request was otherwise denied."
            )
        },
    },
)
def get_facilities(
    lat: float = Query(..., description="Decimal latitude of the site."),
    lon: float = Query(..., description="Decimal longitude of the site."),
    radius_m: int = Query(
        50_000,
        ge=1,
        le=50_000,
        description="Search radius in metres (1–50 000). Default 50 000 (50 km).",
    ),
) -> list[FacilityResponse]:
    """Return nearby waste treatment and recycling facilities from Google Places."""
    try:
        places = search_nearby_facilities(
            latitude=lat, longitude=lon, radius_m=radius_m
        )
    except PlacesClientError as exc:
        logger.warning("Facilities fetch failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return [
        FacilityResponse(
            place_id=p.place_id,
            name=p.name,
            vicinity=p.vicinity,
            latitude=p.latitude,
            longitude=p.longitude,
            types=p.types,
        )
        for p in places
    ]
