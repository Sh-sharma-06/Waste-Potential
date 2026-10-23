"""places_client.py — Google Places API (New) integration for nearby waste facilities.

Searches for waste treatment and recycling facilities within a configurable
radius (default 50 km) of a given location using the Places API (New)
Text Search endpoint (``searchText``).

One POST request is issued per text query (e.g. "waste management facility",
"recycling center").  Results are deduplicated by place ID before being
returned, so the same facility found under multiple queries appears only once.

API docs: https://developers.google.com/maps/documentation/places/web-service/text-search

Error handling
--------------
* Missing API key raises :class:`PlacesClientError` immediately.
* Network timeouts (default 10 s) raise :class:`PlacesClientError`.
* Non-200 HTTP responses raise :class:`PlacesClientError`; a 403 indicates
  an invalid / restricted key.
* Unexpected JSON shapes raise :class:`PlacesClientError`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import httpx

from app.config import GOOGLE_PLACES_API_KEY

logger = logging.getLogger(__name__)

_SEARCH_TEXT_URL = "https://places.googleapis.com/v1/places:searchText"
_TIMEOUT_S = 10.0
_DEFAULT_RADIUS_M = 50_000  # 50 km

# Fields requested via X-Goog-FieldMask header.
_FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,"
    "places.location,places.types"
)

# Text queries issued in sequence.  Results are merged and deduplicated.
_TEXT_QUERIES: list[str] = [
    "waste management facility",
    "recycling center",
    "biogas plant",
    "compost facility",
]


class PlacesClientError(RuntimeError):
    """Raised when the Google Places (New) request fails or is denied."""


@dataclass(frozen=True)
class PlaceResult:
    """A single facility returned by the Places API (New).

    Attributes
    ----------
    place_id:
        Unique Google Place ID (``places/<id>``).
    name:
        Human-readable display name of the facility.
    vicinity:
        Formatted address string from the API.
    latitude:
        Decimal latitude of the facility.
    longitude:
        Decimal longitude of the facility.
    types:
        List of Google place type labels.
    """

    place_id: str
    name: str
    vicinity: str
    latitude: float
    longitude: float
    types: list[str] = field(default_factory=list)


def search_nearby_facilities(
    latitude: float,
    longitude: float,
    radius_m: int = _DEFAULT_RADIUS_M,
) -> list[PlaceResult]:
    """Search for waste / recycling facilities near a location.

    Issues one ``searchText`` POST request per text query and deduplicates
    all results by place ID.  Returns up to 10 results per query (40 total
    before deduplication) without additional pagination.

    Parameters
    ----------
    latitude, longitude:
        Decimal coordinates of the origin site.
    radius_m:
        Bias radius in metres.  Defaults to 50 000 (50 km).

    Returns
    -------
    list[PlaceResult]
        Deduplicated list of matching facilities, ordered by first appearance.

    Raises
    ------
    PlacesClientError
        If the API key is missing, a request times out, or the API returns a
        non-200 response.
    """
    if not GOOGLE_PLACES_API_KEY:
        raise PlacesClientError(
            "GOOGLE_PLACES_API_KEY is not set. "
            "Add it to the .env file at the project root."
        )

    headers = {
        "X-Goog-Api-Key": GOOGLE_PLACES_API_KEY,
        "X-Goog-FieldMask": _FIELD_MASK,
        "Content-Type": "application/json",
    }

    seen: dict[str, PlaceResult] = {}

    for query in _TEXT_QUERIES:
        payload: dict = {
            "textQuery": query,
            "locationBias": {
                "circle": {
                    "center": {"latitude": latitude, "longitude": longitude},
                    "radius": float(radius_m),
                }
            },
            "maxResultCount": 10,
        }

        try:
            response = httpx.post(
                _SEARCH_TEXT_URL,
                json=payload,
                headers=headers,
                timeout=_TIMEOUT_S,
            )
            response.raise_for_status()
            data = response.json()
        except httpx.TimeoutException as exc:
            raise PlacesClientError(
                f"Google Places request timed out after {_TIMEOUT_S}s "
                f"(query={query!r})"
            ) from exc
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            hint = (
                " (check GOOGLE_PLACES_API_KEY and that the Places API (New) "
                "is enabled in your Google Cloud project)"
                if status_code == 403
                else ""
            )
            raise PlacesClientError(
                f"Google Places returned HTTP {status_code}{hint} "
                f"(query={query!r})"
            ) from exc
        except Exception as exc:
            raise PlacesClientError(
                f"Google Places request failed (query={query!r}): {exc}"
            ) from exc

        for item in data.get("places", []):
            try:
                place_id: str = item["id"]
                if place_id in seen:
                    continue
                loc = item["location"]
                display_name = item.get("displayName", {})
                seen[place_id] = PlaceResult(
                    place_id=place_id,
                    name=(
                        display_name.get("text", "")
                        if isinstance(display_name, dict)
                        else str(display_name)
                    ),
                    vicinity=item.get("formattedAddress", ""),
                    latitude=float(loc["latitude"]),
                    longitude=float(loc["longitude"]),
                    types=list(item.get("types", [])),
                )
            except (KeyError, TypeError, ValueError):
                # Skip malformed results rather than failing the whole call.
                logger.debug(
                    "Skipping malformed Places (New) result: %r", item.get("id")
                )

    results = list(seen.values())
    logger.debug(
        "Google Places (New): lat=%.4f lon=%.4f radius=%dm → %d unique facilities",
        latitude,
        longitude,
        radius_m,
        len(results),
    )
    return results
