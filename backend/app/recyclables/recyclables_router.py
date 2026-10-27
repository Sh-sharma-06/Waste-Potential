"""recyclables_router.py — GET /recyclables/buyers and GET /recyclables/prices.

Reuses app.data.buyers helpers (_search_product_places, _haversine_km) and
app.services.routing_client for distance computation — same HTTP clients and
error handling as the existing GET /buyers endpoint.
"""

from __future__ import annotations

import logging
import math
from typing import Optional

import httpx

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.config import GOOGLE_PLACES_API_KEY
from app.data.buyers import _haversine_km
from app.services.places_client import MAX_BIAS_RADIUS_M, PlacesClientError, PlaceResult
from app.services.routing_client import RoutingClientError, get_distance_matrix
from app.recyclables.recyclables_service import load_prices

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/recyclables", tags=["Recyclables"])

# ---------------------------------------------------------------------------
# Valid materials and their Places queries
# ---------------------------------------------------------------------------

VALID_MATERIALS = frozenset({"plastic", "glass", "metal", "e_waste", "paper"})

_MATERIAL_QUERIES: dict[str, list[str]] = {
    "plastic": ["plastic recycler", "plastic scrap dealer"],
    "glass":   ["glass recycling", "glass scrap dealer"],
    "metal":   ["scrap dealer", "metal recycler"],
    "e_waste": ["e-waste recycler", "electronic waste recycler"],
    "paper":   ["paper recycler", "waste paper and cardboard dealer"],
}

# ---------------------------------------------------------------------------
# Places search (same URL/key/field-mask as app.data.buyers)
# ---------------------------------------------------------------------------

_SEARCH_TEXT_URL = "https://places.googleapis.com/v1/places:searchText"
_TIMEOUT_S = 10.0
_FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,"
    "places.location,places.types"
)


def _search_recycler_places(
    lat: float,
    lng: float,
    radius_m: int,
    queries: list[str],
) -> list[PlaceResult]:
    """Issue one Places searchText POST per query; deduplicate by place_id.

    Mirrors app.data.buyers._search_product_places exactly.
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
                    # Bias only; callers still filter results by the full radius.
                    "radius": float(min(radius_m, MAX_BIAS_RADIUS_M)),
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
                " (check GOOGLE_PLACES_API_KEY)"
                if status_code == 403 else ""
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
                    "Skipping malformed Places result: %r", item.get("id")
                )

    return list(seen.values())


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class RecyclerResult(BaseModel):
    name: str
    place_id: str
    lat: float
    lng: float
    distance_km: float
    distance_basis: str   # "road" | "straight_line"
    material: str


class PriceRowResponse(BaseModel):
    material: str
    sub_type: str
    price_inr_per_kg_low: float
    price_inr_per_kg_high: float
    as_of: str
    source: str
    region: str
    stale: bool


class PricesResponse(BaseModel):
    prices: list[PriceRowResponse]
    rows_skipped: int
    note: str


# ---------------------------------------------------------------------------
# GET /recyclables/buyers
# ---------------------------------------------------------------------------

@router.get(
    "/buyers",
    response_model=list[RecyclerResult],
    summary="Find nearby recyclers for a material",
    responses={
        422: {"description": "Unknown material."},
        503: {"description": "Google Places or ORS unreachable."},
    },
)
def get_recycler_buyers(
    lat: float = Query(..., description="Decimal latitude of the waste source."),
    lng: float = Query(..., description="Decimal longitude of the waste source."),
    material: str = Query(
        ...,
        description="Material type: plastic, glass, metal, e_waste, or paper.",
    ),
    radius_km: float = Query(
        50.0,
        ge=1.0,
        le=200.0,
        description="Search radius in km (1–200). Default 50.",
    ),
) -> list[RecyclerResult]:
    """Return nearby recyclers for the given material, sorted by distance."""
    if material not in VALID_MATERIALS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"material {material!r} is not supported; "
                f"must be one of {sorted(VALID_MATERIALS)}"
            ),
        )

    queries = _MATERIAL_QUERIES[material]
    radius_m = int(radius_km * 1_000)

    try:
        candidates = _search_recycler_places(lat, lng, radius_m, queries)
    except PlacesClientError as exc:
        logger.warning("Recycler Places fetch failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if not candidates:
        return []

    # Compute road distances (same pattern as buyers.find_buyers)
    dest_coords = [(p.longitude, p.latitude) for p in candidates]
    distance_basis = "road"
    distances_km: list[Optional[float]] = []

    try:
        matrix = get_distance_matrix(lng, lat, dest_coords)
        distances_km = matrix.distances_km
    except RoutingClientError as exc:
        logger.warning("Routing failed for recyclables, falling back to haversine: %s", exc)
        distance_basis = "straight_line"
        distances_km = [
            _haversine_km(lat, lng, p.latitude, p.longitude) for p in candidates
        ]

    results: list[RecyclerResult] = []
    for place, dist in zip(candidates, distances_km):
        if dist is None:
            actual_dist = _haversine_km(lat, lng, place.latitude, place.longitude)
            basis = "straight_line"
        else:
            actual_dist = dist
            basis = distance_basis

        if actual_dist > radius_km:
            continue

        results.append(RecyclerResult(
            name=place.name,
            place_id=place.place_id,
            lat=place.latitude,
            lng=place.longitude,
            distance_km=round(actual_dist, 3),
            distance_basis=basis,
            material=material,
        ))

    results.sort(key=lambda r: r.distance_km)
    return results


# ---------------------------------------------------------------------------
# GET /recyclables/prices
# ---------------------------------------------------------------------------

@router.get(
    "/prices",
    response_model=PricesResponse,
    summary="Get indicative scrap prices for a material",
    responses={
        422: {"description": "Unknown material."},
    },
)
def get_prices(
    material: str = Query(
        ...,
        description="Material type: plastic, glass, metal, e_waste, or paper.",
    ),
) -> PricesResponse:
    """Return indicative price ranges for the given material from the local CSV."""
    if material not in VALID_MATERIALS:
        raise HTTPException(
            status_code=422,
            detail=(
                f"material {material!r} is not supported; "
                f"must be one of {sorted(VALID_MATERIALS)}"
            ),
        )

    result = load_prices(material)
    return PricesResponse(
        prices=[
            PriceRowResponse(
                material=row.material,
                sub_type=row.sub_type,
                price_inr_per_kg_low=row.price_inr_per_kg_low,
                price_inr_per_kg_high=row.price_inr_per_kg_high,
                as_of=row.as_of,
                source=row.source,
                region=row.region,
                stale=row.stale,
            )
            for row in result.rows
        ],
        rows_skipped=result.rows_skipped,
        note=result.note,
    )
