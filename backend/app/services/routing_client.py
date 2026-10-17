"""routing_client.py — OpenRouteService integration for road distance matrices.

Calls the ORS Matrix API to compute road distances (km) between a source
location and one or more destination locations.  Used to populate
:class:`~app.schemas.data.FacilityEntry` ``road_km`` values for transport
cost estimation.

API docs: https://openrouteservice.org/dev/#/api-docs/matrix

Error handling
--------------
* Missing API key raises :class:`RoutingClientError` immediately.
* Network timeouts (default 15 s) raise :class:`RoutingClientError`.
* Non-200 HTTP responses (including 403 for invalid keys) raise
  :class:`RoutingClientError` with the status code in the message.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

import httpx

from app.config import OPEN_ROUTE_SERVICE_API_KEY

logger = logging.getLogger(__name__)

_MATRIX_URL = "https://api.openrouteservice.org/v2/matrix/driving-car"
_TIMEOUT_S = 15.0


class RoutingClientError(RuntimeError):
    """Raised when the ORS request fails or returns unexpected data."""


@dataclass(frozen=True)
class DistanceMatrix:
    """Road distances from a single source to multiple destinations.

    Attributes
    ----------
    source:
        ``(longitude, latitude)`` of the origin point.
    destinations:
        Sequence of ``(longitude, latitude)`` destination coordinates.
    distances_km:
        One-way road distances in km, parallel to ``destinations``.
        A value of ``None`` means ORS could not route to that destination.
    """

    source: tuple[float, float]
    destinations: list[tuple[float, float]]
    distances_km: list[float | None]


def get_distance_matrix(
    source_lon: float,
    source_lat: float,
    destination_coords: Sequence[tuple[float, float]],
) -> DistanceMatrix:
    """Calculate road distances from one source to multiple destinations.

    Parameters
    ----------
    source_lon, source_lat:
        Decimal longitude / latitude of the origin site.
    destination_coords:
        Sequence of ``(longitude, latitude)`` tuples for destination sites.

    Returns
    -------
    DistanceMatrix
        Road distances in km for each destination.

    Raises
    ------
    RoutingClientError
        If the API key is missing, the request times out, or ORS returns an
        error status code.
    """
    if not OPEN_ROUTE_SERVICE_API_KEY:
        raise RoutingClientError(
            "OPEN_ROUTE_SERVICE_API_KEY is not set. "
            "Add it to the .env file at the project root."
        )
    if not destination_coords:
        return DistanceMatrix(
            source=(source_lon, source_lat),
            destinations=[],
            distances_km=[],
        )

    locations = [[source_lon, source_lat]] + [
        [lon, lat] for lon, lat in destination_coords
    ]
    # sources=[0] means the first location is the origin; all others are targets.
    payload = {
        "locations": locations,
        "sources": [0],
        "destinations": list(range(1, len(locations))),
        "metrics": ["distance"],
        "units": "km",
    }
    headers = {
        "Authorization": OPEN_ROUTE_SERVICE_API_KEY,
        "Content-Type": "application/json",
    }

    try:
        response = httpx.post(
            _MATRIX_URL, json=payload, headers=headers, timeout=_TIMEOUT_S
        )
        response.raise_for_status()
        data = response.json()
    except httpx.TimeoutException as exc:
        raise RoutingClientError(
            f"OpenRouteService request timed out after {_TIMEOUT_S}s"
        ) from exc
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        hint = " (check OPEN_ROUTE_SERVICE_API_KEY)" if status == 403 else ""
        raise RoutingClientError(
            f"OpenRouteService returned HTTP {status}{hint}"
        ) from exc
    except Exception as exc:
        raise RoutingClientError(
            f"OpenRouteService request failed: {exc}"
        ) from exc

    try:
        # distances is a 1×N matrix; take row 0.
        raw_row: list[float | None] = data["distances"][0]
    except (KeyError, IndexError, TypeError) as exc:
        raise RoutingClientError(
            f"Unexpected ORS response shape: {exc}"
        ) from exc

    distances_km = [
        round(float(d), 3) if d is not None else None for d in raw_row
    ]
    logger.debug(
        "ORS matrix: source=(%.4f,%.4f) destinations=%d",
        source_lon,
        source_lat,
        len(destination_coords),
    )
    return DistanceMatrix(
        source=(source_lon, source_lat),
        destinations=list(destination_coords),
        distances_km=distances_km,
    )
