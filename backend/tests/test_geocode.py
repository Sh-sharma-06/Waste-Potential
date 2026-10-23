"""Tests for GET /geocode (app/api/geocode.py + app/services/geocode_client.py).

All Nominatim HTTP calls are mocked — no network required.

Covers:
  - 200: string lat/lon from Nominatim converted to floats; all response fields present.
  - 404: empty list from Nominatim.
  - 503: timeout exception from httpx.
  - 503: non-200 (500) HTTP response from Nominatim.
  - 422: "12345" (5-digit Indian pincode).
  - 422: "012345" (Indian pincode starting with 0).
  - 422: letters passed as Indian pincode.
  - Cache hit: a second identical request makes only one upstream call.
  - User-Agent header is sent with every outbound request.
  - Rate guard: a second uncached call is delayed by at least 1.1 s.
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.geocode import router
import app.services.geocode_client as _gc_mod

URL = "/geocode"


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client():
    return TestClient(_app())


@pytest.fixture(autouse=True)
def reset_geocode_cache():
    """Wipe the module-level cache and rate-limit timestamp before each test."""
    _gc_mod._cache._store.clear()
    _gc_mod._last_call_time = 0.0
    yield
    _gc_mod._cache._store.clear()
    _gc_mod._last_call_time = 0.0


# ---------------------------------------------------------------------------
# Helper: build a minimal httpx Response mock
# ---------------------------------------------------------------------------

def _httpx_response(status: int, body) -> MagicMock:
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status
    resp.json.return_value = body
    if status >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            message=f"HTTP {status}",
            request=MagicMock(),
            response=resp,
        )
    else:
        resp.raise_for_status.return_value = None
    return resp


_NOMINATIM_RESULT = [
    {
        "lat": "28.6139",
        "lon": "77.2090",
        "display_name": "New Delhi, Delhi, India",
    }
]


# ---------------------------------------------------------------------------
# 1. Valid classify path — string coords converted to floats
# ---------------------------------------------------------------------------

def test_geocode_200_converts_strings_to_floats(client):
    with patch("app.services.geocode_client.httpx.get",
               return_value=_httpx_response(200, _NOMINATIM_RESULT)):
        resp = client.get(URL, params={"pincode": "110001", "country": "India"})

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert isinstance(data["lat"], float)
    assert isinstance(data["lng"], float)
    assert data["lat"] == pytest.approx(28.6139)
    assert data["lng"] == pytest.approx(77.2090)
    assert data["display_name"] == "New Delhi, Delhi, India"
    assert data["precision"] == "postal-code area centroid, approximate"
    assert data["source"] == "OpenStreetMap Nominatim (ODbL)"
    assert data["cached"] is False


def test_geocode_200_default_country_is_india(client):
    """Omitting country= should default to India and accept a valid 6-digit pincode."""
    with patch("app.services.geocode_client.httpx.get",
               return_value=_httpx_response(200, _NOMINATIM_RESULT)):
        resp = client.get(URL, params={"pincode": "110001"})
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# 2. 404 — empty Nominatim result list
# ---------------------------------------------------------------------------

def test_geocode_404_on_empty_nominatim_result(client):
    with patch("app.services.geocode_client.httpx.get",
               return_value=_httpx_response(200, [])):
        resp = client.get(URL, params={"pincode": "110001", "country": "India"})

    assert resp.status_code == 404
    assert "110001" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 3. 503 — timeout
# ---------------------------------------------------------------------------

def test_geocode_503_on_timeout(client):
    with patch("app.services.geocode_client.httpx.get",
               side_effect=httpx.TimeoutException("timed out")):
        resp = client.get(URL, params={"pincode": "110001", "country": "India"})

    assert resp.status_code == 503
    assert "timed out" in resp.json()["detail"].lower()


# ---------------------------------------------------------------------------
# 4. 503 — Nominatim returns HTTP 500
# ---------------------------------------------------------------------------

def test_geocode_503_on_nominatim_500(client):
    with patch("app.services.geocode_client.httpx.get",
               return_value=_httpx_response(500, {})):
        resp = client.get(URL, params={"pincode": "110001", "country": "India"})

    assert resp.status_code == 503
    assert "500" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 5. 422 validation — bad Indian pincodes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_pincode", [
    "12345",     # only 5 digits
    "012345",    # starts with 0
    "ABCDEF",    # letters
    "1234567",   # 7 digits
    "",          # empty
])
def test_geocode_422_invalid_india_pincode(client, bad_pincode):
    resp = client.get(URL, params={"pincode": bad_pincode, "country": "India"})
    assert resp.status_code == 422, f"expected 422 for {bad_pincode!r}, got {resp.status_code}"


# ---------------------------------------------------------------------------
# 6. 422 validation — bad generic pincodes for non-India
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("bad_pincode", [
    "",              # empty
    "ABCDE-12345",   # hyphen — not alphanumeric
    "A" * 11,        # 11 chars — too long
])
def test_geocode_422_invalid_generic_pincode(client, bad_pincode):
    resp = client.get(URL, params={"pincode": bad_pincode, "country": "Germany"})
    assert resp.status_code == 422, f"expected 422 for {bad_pincode!r}"


# ---------------------------------------------------------------------------
# 7. Valid non-India pincode
# ---------------------------------------------------------------------------

def test_geocode_200_non_india_alphanumeric(client):
    result = [{"lat": "51.5074", "lon": "-0.1278", "display_name": "London, UK"}]
    with patch("app.services.geocode_client.httpx.get",
               return_value=_httpx_response(200, result)):
        resp = client.get(URL, params={"pincode": "EC1A1BB", "country": "UK"})
    assert resp.status_code == 200
    assert resp.json()["lat"] == pytest.approx(51.5074)


# ---------------------------------------------------------------------------
# 8. Cache hit — single upstream call for two identical requests
# ---------------------------------------------------------------------------

def test_geocode_cache_hit_makes_single_upstream_call(client):
    with patch("app.services.geocode_client.httpx.get",
               return_value=_httpx_response(200, _NOMINATIM_RESULT)) as mock_get:
        r1 = client.get(URL, params={"pincode": "110001", "country": "India"})
        r2 = client.get(URL, params={"pincode": "110001", "country": "India"})

    assert r1.status_code == 200
    assert r2.status_code == 200
    assert mock_get.call_count == 1, "Expected exactly one upstream call (second should be cached)"
    assert r1.json()["cached"] is False
    assert r2.json()["cached"] is True


# ---------------------------------------------------------------------------
# 9. User-Agent header is sent
# ---------------------------------------------------------------------------

def test_geocode_user_agent_header_is_sent(client):
    captured_headers: dict = {}

    def fake_get(url, *, params, headers, timeout):
        captured_headers.update(headers)
        return _httpx_response(200, _NOMINATIM_RESULT)

    with patch("app.services.geocode_client.httpx.get", side_effect=fake_get):
        resp = client.get(URL, params={"pincode": "110001", "country": "India"})

    assert resp.status_code == 200
    assert "User-Agent" in captured_headers
    assert "Waste-Potential-Hackathon-App" in captured_headers["User-Agent"]


# ---------------------------------------------------------------------------
# 10. Rate guard — second uncached call is delayed by ≥ 1.1 s
# ---------------------------------------------------------------------------

def test_geocode_rate_guard_delays_second_call(client):
    result_a = [{"lat": "28.6139", "lon": "77.2090", "display_name": "Delhi"}]
    result_b = [{"lat": "19.0760", "lon": "72.8777", "display_name": "Mumbai"}]

    call_times: list[float] = []

    def fake_get(url, *, params, headers, timeout):
        call_times.append(time.monotonic())
        # Return different results so the second call is a genuine cache miss.
        if params["postalcode"] == "110001":
            return _httpx_response(200, result_a)
        return _httpx_response(200, result_b)

    with patch("app.services.geocode_client.httpx.get", side_effect=fake_get):
        client.get(URL, params={"pincode": "110001", "country": "India"})
        client.get(URL, params={"pincode": "400001", "country": "India"})

    assert len(call_times) == 2
    gap = call_times[1] - call_times[0]
    assert gap >= 1.1, f"Rate guard should delay second call by ≥ 1.1 s, got {gap:.3f}s"


# ---------------------------------------------------------------------------
# 11. GEOCODE_CONTACT env var is included in User-Agent
# ---------------------------------------------------------------------------

def test_geocode_contact_env_appended_to_user_agent(client, monkeypatch):
    monkeypatch.setenv("GEOCODE_CONTACT", "test@example.com")
    captured: dict = {}

    def fake_get(url, *, params, headers, timeout):
        captured.update(headers)
        return _httpx_response(200, _NOMINATIM_RESULT)

    with patch("app.services.geocode_client.httpx.get", side_effect=fake_get):
        resp = client.get(URL, params={"pincode": "110001", "country": "India"})

    assert resp.status_code == 200
    assert "test@example.com" in captured.get("User-Agent", "")
