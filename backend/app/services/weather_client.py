"""weather_client.py — Open-Meteo integration for live ambient conditions.

Fetches current hourly temperature and relative humidity for a given lat/lon
from the Open-Meteo free API (no key required).  Returns a typed
:class:`WeatherReading` dataclass.

API docs: https://open-meteo.com/en/docs

Error handling
--------------
* Network timeouts (default 10 s) raise :class:`WeatherClientError`.
* Unexpected JSON shapes raise :class:`WeatherClientError`.
* The caller (endpoint) is responsible for converting to an HTTP error.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.open-meteo.com/v1/forecast"
_TIMEOUT_S = 10.0


class WeatherClientError(RuntimeError):
    """Raised when the Open-Meteo request fails or returns unexpected data."""


@dataclass(frozen=True)
class WeatherReading:
    """Ambient conditions at the requested coordinates (latest hourly value).

    Attributes
    ----------
    latitude:
        Latitude echoed from the API response.
    longitude:
        Longitude echoed from the API response.
    ambient_temp_c:
        Current air temperature at 2 m height (°C).
    relative_humidity:
        Current relative humidity at 2 m height as a fraction [0, 1].
    """

    latitude: float
    longitude: float
    ambient_temp_c: float
    relative_humidity: float


def get_current_weather(latitude: float, longitude: float) -> WeatherReading:
    """Fetch the latest ambient temperature and humidity for a location.

    Parameters
    ----------
    latitude:
        Decimal latitude of the site (−90 to 90).
    longitude:
        Decimal longitude of the site (−180 to 180).

    Returns
    -------
    WeatherReading
        Temperature (°C) and relative humidity fraction for the latest
        available hourly timestep.

    Raises
    ------
    WeatherClientError
        On network timeout, non-200 HTTP status, or unexpected response shape.
    """
    params: dict[str, Any] = {
        "latitude": latitude,
        "longitude": longitude,
        "hourly": "temperature_2m,relative_humidity_2m",
        "forecast_days": 1,
        "timezone": "auto",
    }

    try:
        response = httpx.get(_BASE_URL, params=params, timeout=_TIMEOUT_S)
        response.raise_for_status()
        data = response.json()
    except httpx.TimeoutException as exc:
        raise WeatherClientError(
            f"Open-Meteo request timed out after {_TIMEOUT_S}s"
        ) from exc
    except httpx.HTTPStatusError as exc:
        raise WeatherClientError(
            f"Open-Meteo returned HTTP {exc.response.status_code}"
        ) from exc
    except Exception as exc:
        raise WeatherClientError(f"Open-Meteo request failed: {exc}") from exc

    try:
        hourly = data["hourly"]
        temps: list[float] = hourly["temperature_2m"]
        humidities: list[float] = hourly["relative_humidity_2m"]

        # Use the last non-None value (most recent completed hour).
        temp_c = next(
            (v for v in reversed(temps) if v is not None), temps[0]
        )
        rh_raw = next(
            (v for v in reversed(humidities) if v is not None), humidities[0]
        )
        # Open-Meteo returns RH as 0–100; normalise to 0–1.
        relative_humidity = float(rh_raw) / 100.0
    except (KeyError, IndexError, TypeError) as exc:
        raise WeatherClientError(
            f"Unexpected Open-Meteo response shape: {exc}"
        ) from exc

    logger.debug(
        "Open-Meteo: lat=%.4f lon=%.4f temp=%.1f°C rh=%.3f",
        latitude,
        longitude,
        temp_c,
        relative_humidity,
    )
    return WeatherReading(
        latitude=float(data.get("latitude", latitude)),
        longitude=float(data.get("longitude", longitude)),
        ambient_temp_c=float(temp_c),
        relative_humidity=round(min(max(relative_humidity, 0.0), 1.0), 4),
    )
