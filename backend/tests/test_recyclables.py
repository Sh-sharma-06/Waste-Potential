"""Tests for GET /recyclables/buyers and GET /recyclables/prices.

All external HTTP calls and the CSV path are mocked — no network required.

Covers:
  - Buyers: ordering by distance (nearest first).
  - Buyers: deduplication by place_id across queries.
  - Buyers: radius filter (beyond radius_km dropped).
  - Buyers: straight-line fallback when ORS raises RoutingClientError.
  - Buyers: 422 for unknown material.
  - Prices: empty CSV → note message, prices=[].
  - Prices: malformed rows skipped and counted.
  - Prices: stale flag set for rows older than 90 days.
  - Prices: rows sorted by price_inr_per_kg_high descending.
  - Prices: 422 for unknown material.
  - Prices: response is JSON-serialisable.
"""

from __future__ import annotations

import io
import json
import textwrap
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.recyclables.recyclables_router import router
from app.recyclables.recyclables_service import load_prices, _EMPTY_NOTE, _INDICATIVE_NOTE
from app.services.places_client import PlaceResult, PlacesClientError
from app.services.routing_client import DistanceMatrix, RoutingClientError

URL_BUYERS = "/recyclables/buyers"
URL_PRICES = "/recyclables/prices"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client():
    return TestClient(_app())


def _place(place_id: str, lat: float, lng: float, name: str = "Recycler") -> PlaceResult:
    return PlaceResult(
        place_id=place_id, name=name, vicinity="", latitude=lat, longitude=lng
    )


def _matrix(dists: list[float | None]) -> DistanceMatrix:
    return DistanceMatrix(source=(77.0, 12.0), destinations=[], distances_km=dists)


def _places_response(places: list[PlaceResult]):
    """Build a mock httpx.post return value with the given places."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.raise_for_status.return_value = None
    resp.json.return_value = {
        "places": [
            {
                "id": p.place_id,
                "displayName": {"text": p.name},
                "formattedAddress": p.vicinity,
                "location": {"latitude": p.latitude, "longitude": p.longitude},
                "types": [],
            }
            for p in places
        ]
    }
    return resp


# ---------------------------------------------------------------------------
# 1. Ordering by distance (nearest first)
# ---------------------------------------------------------------------------

def test_buyers_ordered_by_distance(client):
    places = [
        _place("far", 12.50, 77.0, "Far Recycler"),
        _place("near", 12.05, 77.0, "Near Recycler"),
        _place("mid", 12.20, 77.0, "Mid Recycler"),
    ]
    road_dists = [55.0, 5.0, 22.0]

    with patch("app.recyclables.recyclables_router.httpx.post",
               return_value=_places_response(places)), \
         patch("app.recyclables.recyclables_router.get_distance_matrix",
               return_value=_matrix(road_dists)), \
         patch("app.recyclables.recyclables_router.GOOGLE_PLACES_API_KEY", "fake"):
        resp = client.get(URL_BUYERS, params={"lat": 12.0, "lng": 77.0,
                                               "material": "plastic", "radius_km": 100})

    assert resp.status_code == 200, resp.text
    names = [r["name"] for r in resp.json()]
    assert names == ["Near Recycler", "Mid Recycler", "Far Recycler"]


# ---------------------------------------------------------------------------
# 2. Deduplication by place_id across queries
# ---------------------------------------------------------------------------

def test_buyers_deduplication_across_queries(client):
    # Both Places calls return the same place_id "dup" — must appear once.
    place = _place("dup", 12.1, 77.0, "Dup Recycler")

    call_count = [0]

    def fake_post(url, *, json, headers, timeout):
        call_count[0] += 1
        return _places_response([place])

    with patch("app.recyclables.recyclables_router.httpx.post",
               side_effect=fake_post), \
         patch("app.recyclables.recyclables_router.get_distance_matrix",
               return_value=_matrix([10.0])), \
         patch("app.recyclables.recyclables_router.GOOGLE_PLACES_API_KEY", "fake"):
        resp = client.get(URL_BUYERS, params={"lat": 12.0, "lng": 77.0,
                                               "material": "plastic", "radius_km": 50})

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["place_id"] == "dup"
    # Two queries were issued (plastic has 2 queries)
    assert call_count[0] == 2


# ---------------------------------------------------------------------------
# 3. Radius filter: results beyond radius_km are dropped
# ---------------------------------------------------------------------------

def test_buyers_radius_filter(client):
    places = [
        _place("close", 12.05, 77.0, "Close"),
        _place("far",   12.80, 77.0, "Far"),
    ]
    # Road distances: 5 km and 90 km
    road_dists = [5.0, 90.0]

    with patch("app.recyclables.recyclables_router.httpx.post",
               return_value=_places_response(places)), \
         patch("app.recyclables.recyclables_router.get_distance_matrix",
               return_value=_matrix(road_dists)), \
         patch("app.recyclables.recyclables_router.GOOGLE_PLACES_API_KEY", "fake"):
        resp = client.get(URL_BUYERS, params={"lat": 12.0, "lng": 77.0,
                                               "material": "metal", "radius_km": 50})

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["name"] == "Close"


# ---------------------------------------------------------------------------
# 4. Straight-line fallback when ORS raises RoutingClientError
# ---------------------------------------------------------------------------

def test_buyers_straight_line_fallback(client):
    place = _place("p1", 12.05, 77.0, "Recycler A")

    with patch("app.recyclables.recyclables_router.httpx.post",
               return_value=_places_response([place])), \
         patch("app.recyclables.recyclables_router.get_distance_matrix",
               side_effect=RoutingClientError("ORS down")), \
         patch("app.recyclables.recyclables_router.GOOGLE_PLACES_API_KEY", "fake"):
        resp = client.get(URL_BUYERS, params={"lat": 12.0, "lng": 77.0,
                                               "material": "glass", "radius_km": 50})

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["distance_basis"] == "straight_line"
    assert data[0]["distance_km"] > 0


# ---------------------------------------------------------------------------
# 5. 422 for unknown material (buyers)
# ---------------------------------------------------------------------------

def test_buyers_unknown_material_returns_422(client):
    resp = client.get(URL_BUYERS, params={"lat": 12.0, "lng": 77.0,
                                           "material": "uranium", "radius_km": 50})
    assert resp.status_code == 422
    assert "detail" in resp.json()


# ---------------------------------------------------------------------------
# 6. Prices: empty CSV → note message, prices=[]
# ---------------------------------------------------------------------------

def test_prices_empty_csv_returns_note(client, tmp_path):
    csv_path = tmp_path / "prices.csv"
    csv_path.write_text("material,sub_type,price_inr_per_kg_low,price_inr_per_kg_high,as_of,source,region\n")

    with patch("app.recyclables.recyclables_service._CSV_PATH", csv_path):
        resp = client.get(URL_PRICES, params={"material": "plastic"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["prices"] == []
    assert "No price data" in data["note"]


# ---------------------------------------------------------------------------
# 7. Malformed rows: skipped and counted
# ---------------------------------------------------------------------------

def test_prices_malformed_rows_skipped(tmp_path):
    today = date.today().isoformat()
    csv_path = tmp_path / "prices.csv"
    csv_path.write_text(textwrap.dedent(f"""\
        material,sub_type,price_inr_per_kg_low,price_inr_per_kg_high,as_of,source,region
        plastic,PET,abc,12.0,{today},https://example.com,India
        plastic,HDPE,5.0,abc,{today},https://example.com,India
        plastic,PVC,15.0,10.0,{today},https://example.com,India
        plastic,PP,8.0,,{today},https://example.com,India
        plastic,PS,8.0,10.0,{today},,India
        plastic,LDPE,8.0,10.0,{today},https://example.com,India
    """))

    result = load_prices("plastic", csv_path=csv_path)
    assert result.rows_skipped == 5
    assert len(result.rows) == 1
    assert result.rows[0].sub_type == "LDPE"


# ---------------------------------------------------------------------------
# 8. Stale flag for rows older than 90 days
# ---------------------------------------------------------------------------

def test_prices_stale_flag(tmp_path):
    old_date = (date.today() - timedelta(days=91)).isoformat()
    fresh_date = date.today().isoformat()
    csv_path = tmp_path / "prices.csv"
    csv_path.write_text(textwrap.dedent(f"""\
        material,sub_type,price_inr_per_kg_low,price_inr_per_kg_high,as_of,source,region
        metal,Iron,20.0,25.0,{old_date},https://example.com,India
        metal,Copper,400.0,450.0,{fresh_date},https://example.com,India
    """))

    result = load_prices("metal", csv_path=csv_path)
    by_sub = {r.sub_type: r for r in result.rows}
    assert by_sub["Iron"].stale is True
    assert by_sub["Copper"].stale is False


# ---------------------------------------------------------------------------
# 9. Sorting by price_inr_per_kg_high descending
# ---------------------------------------------------------------------------

def test_prices_sorted_by_high_descending(tmp_path):
    today = date.today().isoformat()
    csv_path = tmp_path / "prices.csv"
    csv_path.write_text(textwrap.dedent(f"""\
        material,sub_type,price_inr_per_kg_low,price_inr_per_kg_high,as_of,source,region
        glass,Green glass,2.0,4.0,{today},https://example.com,India
        glass,Clear glass,3.0,6.0,{today},https://example.com,India
        glass,Brown glass,1.5,3.0,{today},https://example.com,India
    """))

    result = load_prices("glass", csv_path=csv_path)
    highs = [r.price_inr_per_kg_high for r in result.rows]
    assert highs == sorted(highs, reverse=True)
    assert highs[0] == 6.0


# ---------------------------------------------------------------------------
# 10. 422 for unknown material (prices)
# ---------------------------------------------------------------------------

def test_prices_unknown_material_returns_422(client):
    resp = client.get(URL_PRICES, params={"material": "wood"})
    assert resp.status_code == 422
    assert "detail" in resp.json()


# ---------------------------------------------------------------------------
# 11. Response is JSON-serialisable
# ---------------------------------------------------------------------------

def test_prices_response_json_serialisable(client, tmp_path):
    today = date.today().isoformat()
    csv_path = tmp_path / "prices.csv"
    csv_path.write_text(textwrap.dedent(f"""\
        material,sub_type,price_inr_per_kg_low,price_inr_per_kg_high,as_of,source,region
        e_waste,Smartphones,50.0,80.0,{today},https://example.com,India
    """))

    with patch("app.recyclables.recyclables_router.load_prices",
               side_effect=lambda m, **kw: __import__("app.recyclables.recyclables_service",
                   fromlist=["load_prices"]).load_prices(m, csv_path=csv_path)):
        resp = client.get(URL_PRICES, params={"material": "e_waste"})

    assert resp.status_code == 200
    # Round-trip through json.dumps must not raise
    round_tripped = json.loads(json.dumps(resp.json()))
    assert round_tripped["prices"][0]["sub_type"] == "Smartphones"


# ---------------------------------------------------------------------------
# 12. Prices response includes as_of and source on every row
# ---------------------------------------------------------------------------

def test_prices_rows_have_as_of_and_source(tmp_path):
    today = date.today().isoformat()
    csv_path = tmp_path / "prices.csv"
    csv_path.write_text(textwrap.dedent(f"""\
        material,sub_type,price_inr_per_kg_low,price_inr_per_kg_high,as_of,source,region
        plastic,PET,8.0,12.0,{today},https://example.com,India
    """))

    result = load_prices("plastic", csv_path=csv_path)
    assert result.rows[0].as_of == today
    assert result.rows[0].source == "https://example.com"


# ---------------------------------------------------------------------------
# 13. Note is indicative when rows present
# ---------------------------------------------------------------------------

def test_prices_note_is_indicative_when_rows_present(tmp_path):
    today = date.today().isoformat()
    csv_path = tmp_path / "prices.csv"
    csv_path.write_text(textwrap.dedent(f"""\
        material,sub_type,price_inr_per_kg_low,price_inr_per_kg_high,as_of,source,region
        metal,Steel,22.0,28.0,{today},https://example.com,India
    """))

    result = load_prices("metal", csv_path=csv_path)
    assert "indicative" in result.note.lower()
    assert "not live" in result.note.lower()


# ---------------------------------------------------------------------------
# 14. Buyers result carries no price field
# ---------------------------------------------------------------------------

def test_buyers_result_has_no_price_field(client):
    place = _place("p1", 12.05, 77.0, "Recycler")

    with patch("app.recyclables.recyclables_router.httpx.post",
               return_value=_places_response([place])), \
         patch("app.recyclables.recyclables_router.get_distance_matrix",
               return_value=_matrix([5.0])), \
         patch("app.recyclables.recyclables_router.GOOGLE_PLACES_API_KEY", "fake"):
        resp = client.get(URL_BUYERS, params={"lat": 12.0, "lng": 77.0,
                                               "material": "e_waste", "radius_km": 50})

    assert resp.status_code == 200
    for item in resp.json():
        for price_key in ("price", "price_inr_per_kg", "tariff", "rate"):
            assert price_key not in item, f"Unexpected price field {price_key!r} in buyer result"
