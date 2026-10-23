"""Tests for GET /buyers (app/data/buyers.py) — all network calls mocked.

Covers:
  - Ordering by distance (nearest first).
  - Deduplication by place_id across product queries.
  - Radius filter (beyond radius_km is dropped).
  - Straight-line fallback when ORS raises RoutingClientError.
  - 422 for unknown product.
  - 422 for out-of-range radius_km (validated by Pydantic/FastAPI).
  - 503 when Places raises PlacesClientError.
  - Response fields match the spec (no price/tariff).
  - Partial ORS None distances fall back to haversine for that entry.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.data.buyers import (
    BuyerResult,
    _DATA_QUALITY,
    _haversine_km,
    find_buyers,
    router,
)
from app.services.places_client import PlaceResult, PlacesClientError
from app.services.routing_client import DistanceMatrix, RoutingClientError

URL = "/buyers"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client():
    return TestClient(_app())


def _place(place_id: str, lat: float, lng: float, name: str = "Place") -> PlaceResult:
    return PlaceResult(
        place_id=place_id,
        name=name,
        vicinity="",
        latitude=lat,
        longitude=lng,
    )


def _matrix(dists: list[float | None], source_lon: float = 77.0, source_lat: float = 12.0) -> DistanceMatrix:
    dests = []
    return DistanceMatrix(
        source=(source_lon, source_lat),
        destinations=dests,
        distances_km=dists,
    )


# ---------------------------------------------------------------------------
# 1. Ordering by distance
# ---------------------------------------------------------------------------

def test_results_ordered_by_distance(client):
    places = [
        _place("p_far", 12.50, 77.0, "Far"),
        _place("p_mid", 12.20, 77.0, "Mid"),
        _place("p_near", 12.05, 77.0, "Near"),
    ]
    # Road distances from source (12.0, 77.0): far=55km, mid=22km, near=5km
    dists = [55.0, 22.0, 5.0]

    with patch("app.data.buyers._search_product_places", return_value=places), \
         patch("app.data.buyers.get_distance_matrix",
               return_value=_matrix(dists)):
        resp = client.get(URL, params={"lat": 12.0, "lng": 77.0, "product": "electricity",
                                       "radius_km": 100})

    assert resp.status_code == 200
    data = resp.json()
    names = [r["name"] for r in data]
    assert names == ["Near", "Mid", "Far"]
    assert data[0]["distance_km"] == 5.0
    assert data[1]["distance_km"] == 22.0
    assert data[2]["distance_km"] == 55.0
    for r in data:
        assert r["distance_basis"] == "road"


# ---------------------------------------------------------------------------
# 2. Deduplication by place_id
# ---------------------------------------------------------------------------

def test_deduplication_by_place_id():
    # _search_product_places already deduplicates; this tests find_buyers
    # doesn't introduce extra duplicates by calling it multiple times.
    places = [
        _place("p1", 12.1, 77.0, "Factory A"),
        _place("p2", 12.2, 77.0, "Factory B"),
    ]
    with patch("app.data.buyers._search_product_places", return_value=places), \
         patch("app.data.buyers.get_distance_matrix",
               return_value=_matrix([5.0, 10.0])):
        result = find_buyers(lat=12.0, lng=77.0, product="electricity", radius_km=50.0)

    place_ids = [r.place_id for r in result]
    assert len(place_ids) == len(set(place_ids)) == 2


# ---------------------------------------------------------------------------
# 3. Radius filter
# ---------------------------------------------------------------------------

def test_radius_filter_drops_distant_results(client):
    places = [
        _place("p_in", 12.1, 77.0, "In Radius"),
        _place("p_out", 13.5, 77.0, "Out of Radius"),
    ]
    dists = [5.0, 200.0]

    with patch("app.data.buyers._search_product_places", return_value=places), \
         patch("app.data.buyers.get_distance_matrix", return_value=_matrix(dists)):
        resp = client.get(URL, params={"lat": 12.0, "lng": 77.0, "product": "compost",
                                       "radius_km": 50})

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["place_id"] == "p_in"


# ---------------------------------------------------------------------------
# 4. Straight-line fallback when ORS fails
# ---------------------------------------------------------------------------

def test_straight_line_fallback_on_routing_error(client):
    # Place at ~11.1 km from origin (12.0, 77.0)
    places = [_place("p1", 12.1, 77.0, "Factory")]

    with patch("app.data.buyers._search_product_places", return_value=places), \
         patch("app.data.buyers.get_distance_matrix",
               side_effect=RoutingClientError("ORS down")):
        resp = client.get(URL, params={"lat": 12.0, "lng": 77.0, "product": "fuel",
                                       "radius_km": 50})

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["distance_basis"] == "straight_line"
    expected = _haversine_km(12.0, 77.0, 12.1, 77.0)
    assert abs(data[0]["distance_km"] - expected) < 0.01


# ---------------------------------------------------------------------------
# 5. Partial ORS None fallback for individual entries
# ---------------------------------------------------------------------------

def test_none_ors_distance_falls_back_to_haversine():
    places = [
        _place("p1", 12.1, 77.0, "Routable"),
        _place("p2", 12.2, 77.0, "Unroutable"),
    ]
    # ORS returns None for the second destination
    with patch("app.data.buyers._search_product_places", return_value=places), \
         patch("app.data.buyers.get_distance_matrix",
               return_value=_matrix([5.0, None])):
        result = find_buyers(lat=12.0, lng=77.0, product="electricity", radius_km=100.0)

    by_id = {r.place_id: r for r in result}
    assert by_id["p1"].distance_basis == "road"
    assert by_id["p2"].distance_basis == "straight_line"
    expected = _haversine_km(12.0, 77.0, 12.2, 77.0)
    assert abs(by_id["p2"].distance_km - expected) < 0.01


# ---------------------------------------------------------------------------
# 6. 422 for unknown product
# ---------------------------------------------------------------------------

def test_unknown_product_returns_422(client):
    resp = client.get(URL, params={"lat": 12.0, "lng": 77.0, "product": "uranium"})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert "uranium" in detail


# ---------------------------------------------------------------------------
# 7. 422 for out-of-range radius_km (Pydantic/FastAPI validation)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("radius", [0.5, 0.0, -10.0, 201.0, 500.0])
def test_out_of_range_radius_returns_422(client, radius):
    resp = client.get(URL, params={"lat": 12.0, "lng": 77.0,
                                   "product": "electricity", "radius_km": radius})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# 8. 503 when Places raises PlacesClientError
# ---------------------------------------------------------------------------

def test_places_error_returns_503(client):
    with patch("app.data.buyers._search_product_places",
               side_effect=PlacesClientError("API key missing")):
        resp = client.get(URL, params={"lat": 12.0, "lng": 77.0, "product": "cbg"})

    assert resp.status_code == 503
    assert "API key missing" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# 9. Response fields match spec (no price or tariff)
# ---------------------------------------------------------------------------

def test_response_fields_match_spec(client):
    places = [_place("p1", 12.1, 77.0, "CNG Hub")]
    with patch("app.data.buyers._search_product_places", return_value=places), \
         patch("app.data.buyers.get_distance_matrix", return_value=_matrix([8.0])):
        resp = client.get(URL, params={"lat": 12.0, "lng": 77.0, "product": "cbg"})

    assert resp.status_code == 200
    row = resp.json()[0]
    expected_keys = {"name", "place_id", "lat", "lng", "distance_km",
                     "distance_basis", "product", "data_quality"}
    assert set(row.keys()) == expected_keys
    assert "price" not in row
    assert "tariff" not in row
    assert row["product"] == "cbg"
    assert row["data_quality"] == _DATA_QUALITY


# ---------------------------------------------------------------------------
# 10. Empty result when all places are beyond radius
# ---------------------------------------------------------------------------

def test_empty_result_when_all_beyond_radius(client):
    places = [_place("p_far", 14.0, 77.0, "Far Away")]
    with patch("app.data.buyers._search_product_places", return_value=places), \
         patch("app.data.buyers.get_distance_matrix", return_value=_matrix([300.0])):
        resp = client.get(URL, params={"lat": 12.0, "lng": 77.0, "product": "compost",
                                       "radius_km": 50})

    assert resp.status_code == 200
    assert resp.json() == []


# ---------------------------------------------------------------------------
# 11. No Places results → empty response (no routing call needed)
# ---------------------------------------------------------------------------

def test_empty_places_result_returns_empty_list(client):
    with patch("app.data.buyers._search_product_places", return_value=[]) as ps, \
         patch("app.data.buyers.get_distance_matrix") as route:
        resp = client.get(URL, params={"lat": 12.0, "lng": 77.0, "product": "electricity"})

    assert resp.status_code == 200
    assert resp.json() == []
    route.assert_not_called()
