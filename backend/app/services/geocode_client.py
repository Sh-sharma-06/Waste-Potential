"""geocode_client.py — Nominatim postal-code geocoding with caching and rate limiting.

Converts a (country, pincode) pair to a latitude / longitude using the free
OpenStreetMap Nominatim search API.

Public-usage-policy compliance
-------------------------------
* User-Agent header identifies the application (contact from env GEOCODE_CONTACT).
* An in-memory LRU cache (max 500 entries, 24 h TTL) avoids repeated identical calls.
* A threading lock ensures at most one outbound call per 1.1 s.

API docs: https://nominatim.org/release-docs/develop/api/Search/

Error handling
--------------
* Empty result list → raises :class:`GeocodeNotFoundError`.
* Network timeout, non-200 response, other network errors → :class:`GeocodeClientError`.
* The caller (endpoint) is responsible for mapping to HTTP status codes.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
_TIMEOUT_S = 10.0
_RATE_INTERVAL_S = 1.1          # minimum seconds between outbound calls
_CACHE_TTL_S = 24 * 60 * 60.0  # 24 h
_CACHE_MAX = 500

_APP_NAME = "Waste-Potential-Hackathon-App/1.0"


def _build_user_agent() -> str:
    contact = os.environ.get("GEOCODE_CONTACT", "").strip()
    if contact:
        return f"{_APP_NAME} ({contact})"
    return _APP_NAME


# ---------------------------------------------------------------------------
# Simple TTL cache (no external dependencies)
# ---------------------------------------------------------------------------

class _TTLCache:
    """Thread-safe in-memory cache with TTL and a maximum capacity."""

    def __init__(self, maxsize: int, ttl: float) -> None:
        self._maxsize = maxsize
        self._ttl = ttl
        self._store: dict[tuple, tuple[float, object]] = {}  # key → (expires_at, value)
        self._lock = threading.Lock()

    def get(self, key: tuple) -> object | None:
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            expires_at, value = entry
            if time.monotonic() > expires_at:
                del self._store[key]
                return None
            return value

    def set(self, key: tuple, value: object) -> None:
        with self._lock:
            if len(self._store) >= self._maxsize and key not in self._store:
                # Evict the oldest entry (first inserted).
                oldest = next(iter(self._store))
                del self._store[oldest]
            self._store[key] = (time.monotonic() + self._ttl, value)

    def __len__(self) -> int:
        return len(self._store)


_cache: _TTLCache = _TTLCache(maxsize=_CACHE_MAX, ttl=_CACHE_TTL_S)

# Rate-limiting state
_rate_lock = threading.Lock()
_last_call_time: float = 0.0


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

class GeocodeClientError(RuntimeError):
    """Raised on network timeout, non-200 response, or other transport error."""


class GeocodeNotFoundError(LookupError):
    """Raised when Nominatim returns an empty result list."""


@dataclass(frozen=True)
class GeocodeResult:
    lat: float
    lng: float
    display_name: str
    cached: bool


# ---------------------------------------------------------------------------
# Main function
# ---------------------------------------------------------------------------

def geocode_pincode(pincode: str, country: str) -> GeocodeResult:
    """Geocode a postal code to lat/lng via Nominatim.

    Raises
    ------
    GeocodeNotFoundError
        If Nominatim returns no results for the given pincode + country.
    GeocodeClientError
        On network timeout, non-200 HTTP response, or other transport error.
    """
    key = (country.lower(), pincode.lower())

    cached_value = _cache.get(key)
    if cached_value is not None:
        logger.debug("geocode cache hit: %s/%s", country, pincode)
        result = cached_value
        return GeocodeResult(
            lat=result.lat,  # type: ignore[union-attr]
            lng=result.lng,  # type: ignore[union-attr]
            display_name=result.display_name,  # type: ignore[union-attr]
            cached=True,
        )

    _rate_limit()

    headers = {"User-Agent": _build_user_agent()}
    params = {
        "postalcode": pincode,
        "country": country,
        "format": "jsonv2",
        "limit": 1,
    }

    try:
        response = httpx.get(_NOMINATIM_URL, params=params, headers=headers, timeout=_TIMEOUT_S)
        response.raise_for_status()
        data = response.json()
    except httpx.TimeoutException as exc:
        raise GeocodeClientError(
            f"Nominatim request timed out after {_TIMEOUT_S}s"
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise GeocodeClientError(
            f"Nominatim returned HTTP {exc.response.status_code}"
        ) from exc
    except Exception as exc:
        raise GeocodeClientError(f"Nominatim request failed: {exc}") from exc

    if not data:
        raise GeocodeNotFoundError(
            f"No geocoding result found for pincode '{pincode}' in '{country}'."
        )

    item = data[0]
    result = GeocodeResult(
        lat=float(item["lat"]),
        lng=float(item["lon"]),
        display_name=str(item.get("display_name", "")),
        cached=False,
    )
    _cache.set(key, result)
    logger.debug("geocode: %s/%s → %.6f, %.6f", country, pincode, result.lat, result.lng)
    return result


def _rate_limit() -> None:
    """Block until at least _RATE_INTERVAL_S seconds have passed since the last call."""
    global _last_call_time
    with _rate_lock:
        now = time.monotonic()
        wait = _last_call_time + _RATE_INTERVAL_S - now
        if wait > 0:
            time.sleep(wait)
        _last_call_time = time.monotonic()
