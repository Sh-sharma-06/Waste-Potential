"""buyers.py — GET /buyers endpoint for energy/product buyer discovery.

Given a location (lat, lng) and a product type, searches Google Places for
candidate buyers nearby, computes road distances via OpenRouteService (or falls
back to haversine), filters by radius_km and returns sorted results.

Uses the same HTTP infrastructure as app/services/places_client.py and
app/services/routing_client.py — no new HTTP libraries or client classes are
introduced.  Keys come from app.config exactly as they do in those modules.

Products supported: electricity, fuel, compost, cbg.
"""

from __future__ import annotations

import logging
import math
from typing import Optional

import httpx

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.config import GOOGLE_PLACES_API_KEY
from app.services.places_client import PlacesClientError, PlaceResult
from app.services.routing_client import RoutingClientError, get_distance_matrix

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Buyers"])

# ---------------------------------------------------------------------------
# Places API constants — shared with places_client.py (same endpoint/key)
# ---------------------------------------------------------------------------

_SEARCH_TEXT_URL = "https://places.googleapis.com/v1/places:searchText"
_TIMEOUT_S = 10.0
_FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,"
    "places.location,places.types"
)

# ---------------------------------------------------------------------------
# Product → Places text queries
# ---------------------------------------------------------------------------

PRODUCT_QUERIES: dict[str, list[str]] = {
    "electricity": [
        "industrial estate",
        "factory",
        "power plant",
    ],
    "fuel": [
        "biomass power plant",
        "boiler industry",
        "cement plant",
    ],
    "compost": [
        "plant nursery",
        "fertilizer shop",
    ],
    "cbg": [
        "CNG station",
        "city gas distribution",
    ],
}

VALID_PRODUCTS = frozenset(PRODUCT_QUERIES)

_DATA_QUALITY = (
    "candidate from Google Places search; demand and tariff not verified"
)


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

class BuyerResult(BaseModel):
    """A single candidate buyer returned by the /buyers endpoint."""

    name: str = Field(..., description="Display name of the buyer.")
    place_id: str = Field(..., description="Unique Google Place ID.")
    lat: float = Field(..., description="Decimal latitude of the buyer.")
    lng: float = Field(..., description="Decimal longitude of the buyer.")
    distance_km: float = Field(..., description="Distance from the query origin in km.")
    distance_basis: str = Field(
        ...,
        description="'road' when computed by ORS, 'straight_line' on routing fallback.",
    )
    product: str = Field(..., description="Product type queried.")
    data_quality: str = Field(..., description="Data quality note.")


# ---------------------------------------------------------------------------
# Haversine fallback
# ---------------------------------------------------------------------------

def _haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return the great-circle distance in km between two points."""
    r = 6_371.0
    d_lat = math.radians(lat2 - lat1)
    d_lng = math.radians(lng2 - lng1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lng / 2) ** 2
    )
    return r * 2 * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Places search (product-specific queries, same API as places_client.py)
# ---------------------------------------------------------------------------

def _search_product_places(
    lat: float,
    lng: float,
    radius_m: int,
    queries: list[str],
) -> list[PlaceResult]:
    """Issue one Places ``searchText`` POST per query and return deduplicated results.

    Uses the same URL, field mask, API key and error handling as
    ``app.services.places_client.search_nearby_facilities``.  Factored out
    here because that function uses fixed facility queries; buyers need
    product-specific queries instead.

    Raises
    ------
    PlacesClientError
        If the API key is missing or any request fails.
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

    for query in queries:
        payload: dict = {
            "textQuery": query,
            "locationBias": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lng},
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
        except PlacesClientError:
            raise
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
                logger.debug(
                    "Skipping malformed Places (New) result: %r", item.get("id")
                )

    return list(seen.values())


# ---------------------------------------------------------------------------
# Core logic (importable for tests)
# ---------------------------------------------------------------------------

def find_buyers(
    lat: float,
    lng: float,
    product: str,
    radius_km: float,
) -> list[BuyerResult]:
    """Search for candidate buyers and enrich with road distances.

    Parameters
    ----------
    lat, lng:
        Origin coordinates.
    product:
        One of: electricity, fuel, compost, cbg.
    radius_km:
        Drop candidates beyond this distance.

    Returns
    -------
    list[BuyerResult]
        Deduplicated, filtered, sorted by distance_km ascending.

    Raises
    ------
    PlacesClientError
        If the Places search fails entirely.
    """
    queries = PRODUCT_QUERIES[product]
    radius_m = int(radius_km * 1_000)

    candidates = _search_product_places(lat, lng, radius_m, queries)
    if not candidates:
        return []

    # --- Compute road distances ---
    dest_coords = [(p.longitude, p.latitude) for p in candidates]
    distance_basis = "road"
    distances_km: list[Optional[float]] = []

    try:
        matrix = get_distance_matrix(lng, lat, dest_coords)
        distances_km = matrix.distances_km
    except RoutingClientError as exc:
        logger.warning("Routing failed, falling back to haversine: %s", exc)
        distance_basis = "straight_line"
        distances_km = [
            _haversine_km(lat, lng, p.latitude, p.longitude) for p in candidates
        ]

    # --- Build results, filter and sort ---
    results: list[BuyerResult] = []
    for place, dist in zip(candidates, distances_km):
        # A None distance from ORS means unroutable — fall back to haversine
        if dist is None:
            actual_dist = _haversine_km(lat, lng, place.latitude, place.longitude)
            basis = "straight_line"
        else:
            actual_dist = dist
            basis = distance_basis

        if actual_dist > radius_km:
            continue

        results.append(
            BuyerResult(
                name=place.name,
                place_id=place.place_id,
                lat=place.latitude,
                lng=place.longitude,
                distance_km=round(actual_dist, 3),
                distance_basis=basis,
                product=product,
                data_quality=_DATA_QUALITY,
            )
        )

    results.sort(key=lambda r: r.distance_km)
    return results


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------

@router.get(
    "/buyers",
    response_model=list[BuyerResult],
    summary="Search for nearby buyers of a waste-derived product",
    responses={
        422: {"description": "Invalid product or out-of-range radius_km."},
        503: {"description": "Google Places or ORS is unreachable or denied."},
    },
)
def get_buyers(
    lat: float = Query(..., description="Decimal latitude of the waste source."),
    lng: float = Query(..., description="Decimal longitude of the waste source."),
    product: str = Query(
        ...,
        description="Product to sell: electricity, fuel, compost, or cbg.",
    ),
    radius_km: float = Query(
        50.0,
        ge=1.0,
        le=200.0,
        description="Search radius in km (1–200). Default 50.",
    ),
) -> list[BuyerResult]:
    """Return candidate buyers for a product near the supplied coordinates.

    Each result includes a name, place_id, coordinates, distance (road or
    straight-line), and a data-quality note.  No price or tariff is included.
    """
    if product not in VALID_PRODUCTS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"product {product!r} is not supported; "
                f"must be one of {sorted(VALID_PRODUCTS)}"
            ),
        )

    try:
        return find_buyers(lat=lat, lng=lng, product=product, radius_km=radius_km)
    except PlacesClientError as exc:
        logger.warning("Buyers Places fetch failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Unexpected buyers error: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
