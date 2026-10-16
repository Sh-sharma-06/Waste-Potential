"""
Tests for backend/app/decision/market.py and specs.py

Coverage:
  - mock_osrm_road_distance: correctly applies 1.3x straight-line multiplier
  - Hard filter: distance > max radius drops buyer with correct reason
  - Hard filter: demand ≤ 0 drops buyer
  - Hard filter: product type mismatch drops buyer
  - Hard filter: spec threshold not met drops buyer
  - Scoring: match_score in [0.0, 1.0] for all eligible buyers
  - Scoring: higher bid + shorter distance → higher score
  - Allocation: allocated volume ≤ min(available_supply, buyer_demand)
  - Allocation: total allocated never exceeds facility available_volume
  - Allocation: stops when remaining_volume == 0
  - Allocation: remaining_volume correct when demand < supply
  - All-filtered case: 0 allocated, 100 % remaining
"""

import math
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.decision.market import MarketMatcher, mock_osrm_road_distance, _haversine_km
from app.decision.specs import (
    BuyerMatch,
    BuyerProfile,
    FacilityOutput,
    MarketMatchResult,
    ProductSpec,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

LONDON_LAT, LONDON_LON = 51.5074, -0.1278
MANCHESTER_LAT, MANCHESTER_LON = 53.4808, -2.2426
BIRMINGHAM_LAT, BIRMINGHAM_LON = 52.4862, -1.8904
EDINBURGH_LAT, EDINBURGH_LON = 55.9533, -3.1883


@pytest.fixture
def biogas_facility() -> FacilityOutput:
    return FacilityOutput(
        facility_id="FAC-001",
        product=ProductSpec("biogas", {"methane_pct": 62.5, "h2s_ppm": 200.0}),
        available_volume=1000.0,
        latitude=LONDON_LAT,
        longitude=LONDON_LON,
    )


@pytest.fixture
def eligible_buyer_close() -> BuyerProfile:
    """High bid, close distance — should rank highest."""
    return BuyerProfile(
        buyer_id="B-HIGH",
        product_type="biogas",
        demand_volume=400.0,
        min_spec_thresholds={"methane_pct": 55.0},
        bid_price=120.0,
        latitude=51.6,
        longitude=-0.2,
        max_road_distance_km=500.0,
    )


@pytest.fixture
def eligible_buyer_far() -> BuyerProfile:
    """Lower bid, farther distance — should rank below B-HIGH."""
    return BuyerProfile(
        buyer_id="B-LOW",
        product_type="biogas",
        demand_volume=700.0,
        min_spec_thresholds={"methane_pct": 55.0},
        bid_price=80.0,
        latitude=MANCHESTER_LAT,
        longitude=MANCHESTER_LON,
        max_road_distance_km=500.0,
    )


@pytest.fixture
def matcher() -> MarketMatcher:
    return MarketMatcher()


# ---------------------------------------------------------------------------
# OSRM mock distance
# ---------------------------------------------------------------------------

class TestMockOSRM:
    def test_multiplier_is_1_3x_straight_line(self):
        """Road distance must equal haversine × 1.3."""
        straight = _haversine_km(LONDON_LAT, LONDON_LON, MANCHESTER_LAT, MANCHESTER_LON)
        road = mock_osrm_road_distance(LONDON_LAT, LONDON_LON, MANCHESTER_LAT, MANCHESTER_LON)
        assert math.isclose(road, straight * 1.3, rel_tol=1e-9)

    def test_known_distance_london_manchester(self):
        """London–Manchester is ~260 km straight-line → ~338 km road."""
        road = mock_osrm_road_distance(LONDON_LAT, LONDON_LON, MANCHESTER_LAT, MANCHESTER_LON)
        assert 300 < road < 400, f"Expected 300–400 km road distance, got {road:.1f} km"

    def test_same_point_is_zero(self):
        dist = mock_osrm_road_distance(51.5, -0.1, 51.5, -0.1)
        assert dist == pytest.approx(0.0, abs=1e-6)

    def test_symmetry(self):
        """A→B and B→A should give the same distance."""
        ab = mock_osrm_road_distance(LONDON_LAT, LONDON_LON, EDINBURGH_LAT, EDINBURGH_LON)
        ba = mock_osrm_road_distance(EDINBURGH_LAT, EDINBURGH_LON, LONDON_LAT, LONDON_LON)
        assert math.isclose(ab, ba, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# Hard filter
# ---------------------------------------------------------------------------

class TestHardFilter:
    def test_buyer_outside_max_radius_is_dropped(self, biogas_facility, matcher):
        """Buyer with max_road_distance_km=1 should be filtered (London→Manchester is ~338 km)."""
        far_buyer = BuyerProfile(
            buyer_id="TOO-FAR",
            product_type="biogas",
            demand_volume=200.0,
            min_spec_thresholds={"methane_pct": 55.0},
            bid_price=90.0,
            latitude=MANCHESTER_LAT,
            longitude=MANCHESTER_LON,
            max_road_distance_km=1.0,   # only 1 km allowed — impossible
        )
        result = matcher.match(biogas_facility, [far_buyer])
        assert "TOO-FAR" in result.filter_reasons
        assert "road_distance" in result.filter_reasons["TOO-FAR"]
        assert result.n_eligible_buyers == 0
        assert result.total_allocated == 0.0

    def test_buyer_inside_max_radius_is_kept(self, biogas_facility, eligible_buyer_close, matcher):
        result = matcher.match(biogas_facility, [eligible_buyer_close])
        assert eligible_buyer_close.buyer_id not in result.filter_reasons
        assert result.n_eligible_buyers == 1

    def test_zero_demand_is_dropped(self, biogas_facility, matcher):
        zero_demand = BuyerProfile(
            buyer_id="ZERO-DEMAND",
            product_type="biogas",
            demand_volume=0.0,
            min_spec_thresholds={},
            bid_price=50.0,
            latitude=51.6,
            longitude=-0.2,
        )
        result = matcher.match(biogas_facility, [zero_demand])
        assert "ZERO-DEMAND" in result.filter_reasons
        assert "demand_volume" in result.filter_reasons["ZERO-DEMAND"]

    def test_negative_demand_is_dropped(self, biogas_facility, matcher):
        neg_demand = BuyerProfile(
            buyer_id="NEG-DEMAND",
            product_type="biogas",
            demand_volume=-100.0,
            min_spec_thresholds={},
            bid_price=50.0,
            latitude=51.6,
            longitude=-0.2,
        )
        result = matcher.match(biogas_facility, [neg_demand])
        assert "NEG-DEMAND" in result.filter_reasons

    def test_wrong_product_type_is_dropped(self, biogas_facility, matcher):
        wrong_type = BuyerProfile(
            buyer_id="WRONG-PRODUCT",
            product_type="digestate",  # facility offers biogas
            demand_volume=300.0,
            min_spec_thresholds={},
            bid_price=70.0,
            latitude=51.6,
            longitude=-0.2,
        )
        result = matcher.match(biogas_facility, [wrong_type])
        assert "WRONG-PRODUCT" in result.filter_reasons
        assert "product_type mismatch" in result.filter_reasons["WRONG-PRODUCT"]

    def test_spec_below_threshold_is_dropped(self, biogas_facility, matcher):
        """Buyer requires methane_pct ≥ 70 but facility only produces 62.5 %."""
        demanding_buyer = BuyerProfile(
            buyer_id="SPEC-FAIL",
            product_type="biogas",
            demand_volume=200.0,
            min_spec_thresholds={"methane_pct": 70.0},  # 62.5 < 70.0
            bid_price=100.0,
            latitude=51.6,
            longitude=-0.2,
            max_road_distance_km=500.0,
        )
        result = matcher.match(biogas_facility, [demanding_buyer])
        assert "SPEC-FAIL" in result.filter_reasons
        assert "methane_pct" in result.filter_reasons["SPEC-FAIL"]

    def test_spec_at_threshold_is_kept(self, biogas_facility, matcher):
        """Buyer requires exactly 62.5 % — facility meets the threshold."""
        exact_spec = BuyerProfile(
            buyer_id="EXACT-SPEC",
            product_type="biogas",
            demand_volume=200.0,
            min_spec_thresholds={"methane_pct": 62.5},  # exactly met
            bid_price=90.0,
            latitude=51.6,
            longitude=-0.2,
            max_road_distance_km=500.0,
        )
        result = matcher.match(biogas_facility, [exact_spec])
        assert "EXACT-SPEC" not in result.filter_reasons

    def test_missing_spec_parameter_drops_buyer(self, biogas_facility, matcher):
        """Buyer requires a spec key the facility doesn't declare."""
        mystery_spec = BuyerProfile(
            buyer_id="MYSTERY",
            product_type="biogas",
            demand_volume=100.0,
            min_spec_thresholds={"co2_pct": 5.0},   # facility has no co2_pct
            bid_price=80.0,
            latitude=51.6,
            longitude=-0.2,
            max_road_distance_km=500.0,
        )
        result = matcher.match(biogas_facility, [mystery_spec])
        assert "MYSTERY" in result.filter_reasons


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

class TestMatchScoring:
    def test_scores_in_valid_range(
        self, biogas_facility, eligible_buyer_close, eligible_buyer_far, matcher
    ):
        result = matcher.match(biogas_facility, [eligible_buyer_close, eligible_buyer_far])
        for m in result.matches:
            assert 0.0 <= m.match_score <= 1.0, f"Score out of range: {m.match_score}"

    def test_higher_bid_and_closer_ranks_first(
        self, biogas_facility, eligible_buyer_close, eligible_buyer_far, matcher
    ):
        """B-HIGH has higher bid AND shorter distance — must have higher match_score."""
        result = matcher.match(biogas_facility, [eligible_buyer_close, eligible_buyer_far])
        scores = {m.buyer_id: m.match_score for m in result.matches}
        assert scores["B-HIGH"] > scores["B-LOW"], (
            f"B-HIGH score={scores['B-HIGH']:.4f} should exceed "
            f"B-LOW score={scores['B-LOW']:.4f}"
        )

    def test_single_buyer_gets_score_point_five(self, biogas_facility, matcher):
        """With a single eligible buyer, both norm values collapse to 0.5
        → score = 0.6·0.5 + 0.4·0.5 = 0.5."""
        solo = BuyerProfile(
            buyer_id="SOLO",
            product_type="biogas",
            demand_volume=200.0,
            min_spec_thresholds={"methane_pct": 55.0},
            bid_price=90.0,
            latitude=51.6,
            longitude=-0.2,
            max_road_distance_km=500.0,
        )
        result = matcher.match(biogas_facility, [solo])
        assert len(result.matches) == 1
        assert math.isclose(result.matches[0].match_score, 0.5, abs_tol=1e-9)


# ---------------------------------------------------------------------------
# Allocation
# ---------------------------------------------------------------------------

class TestAllocation:
    def test_each_allocation_does_not_exceed_buyer_demand(
        self, biogas_facility, eligible_buyer_close, eligible_buyer_far, matcher
    ):
        """Each buyer's allocated_volume ≤ buyer demand_volume."""
        result = matcher.match(biogas_facility, [eligible_buyer_close, eligible_buyer_far])
        demand_map = {
            eligible_buyer_close.buyer_id: eligible_buyer_close.demand_volume,
            eligible_buyer_far.buyer_id: eligible_buyer_far.demand_volume,
        }
        for m in result.matches:
            assert m.allocated_volume <= demand_map[m.buyer_id] + 1e-9, (
                f"Buyer {m.buyer_id} allocated {m.allocated_volume} > demand {demand_map[m.buyer_id]}"
            )

    def test_total_allocated_does_not_exceed_supply(
        self, biogas_facility, eligible_buyer_close, eligible_buyer_far, matcher
    ):
        """total_allocated ≤ facility.available_volume."""
        result = matcher.match(biogas_facility, [eligible_buyer_close, eligible_buyer_far])
        assert result.total_allocated <= biogas_facility.available_volume + 1e-9

    def test_remaining_volume_is_correct(
        self, biogas_facility, eligible_buyer_close, eligible_buyer_far, matcher
    ):
        result = matcher.match(biogas_facility, [eligible_buyer_close, eligible_buyer_far])
        expected_remaining = biogas_facility.available_volume - result.total_allocated
        assert math.isclose(result.remaining_volume, expected_remaining, rel_tol=1e-9)

    def test_allocation_stops_when_supply_exhausted(self, matcher):
        """When demand >> supply, all supply is allocated and remaining == 0."""
        facility = FacilityOutput(
            "F2", ProductSpec("biogas", {"methane_pct": 60.0}), 500.0, 51.5, -0.1
        )
        buyers = [
            BuyerProfile(f"B{i}", "biogas", 300.0, {"methane_pct": 50.0}, 80.0 + i * 5,
                         51.5 + i * 0.05, -0.1, max_road_distance_km=1000.0)
            for i in range(4)  # 4 buyers × 300 t = 1200 t demand vs 500 t supply
        ]
        result = matcher.match(facility, buyers)
        assert math.isclose(result.total_allocated, 500.0, abs_tol=1e-6)
        assert math.isclose(result.remaining_volume, 0.0, abs_tol=1e-6)

    def test_partial_demand_leaves_correct_remaining(self, matcher):
        """When supply > total demand, remaining_volume = supply - sum(demand)."""
        facility = FacilityOutput(
            "F3", ProductSpec("biogas", {"methane_pct": 60.0}), 2000.0, 51.5, -0.1
        )
        buyers = [
            BuyerProfile("B1", "biogas", 200.0, {}, 80.0, 51.6, -0.15, max_road_distance_km=500.0),
            BuyerProfile("B2", "biogas", 300.0, {}, 90.0, 51.7, -0.20, max_road_distance_km=500.0),
        ]
        result = matcher.match(facility, buyers)
        assert math.isclose(result.total_allocated, 500.0, abs_tol=1e-6)
        assert math.isclose(result.remaining_volume, 1500.0, abs_tol=1e-6)

    def test_all_filtered_leaves_full_remaining(self, biogas_facility, matcher):
        """When every buyer fails hard filter, nothing is allocated."""
        wrong_product_buyers = [
            BuyerProfile(f"B{i}", "electricity", 100.0, {}, 50.0, 51.5, -0.1)
            for i in range(3)
        ]
        result = matcher.match(biogas_facility, wrong_product_buyers)
        assert result.total_allocated == 0.0
        assert result.remaining_volume == biogas_facility.available_volume
        assert result.n_eligible_buyers == 0
        assert result.n_filtered_buyers == 3


# ---------------------------------------------------------------------------
# MarketMatchResult structure
# ---------------------------------------------------------------------------

class TestResultStructure:
    def test_result_fields_present(self, biogas_facility, eligible_buyer_close, matcher):
        result = matcher.match(biogas_facility, [eligible_buyer_close])
        assert isinstance(result, MarketMatchResult)
        assert result.facility_id == biogas_facility.facility_id
        assert isinstance(result.matches, list)
        assert isinstance(result.filter_reasons, dict)
        assert isinstance(result.n_eligible_buyers, int)
        assert isinstance(result.n_filtered_buyers, int)

    def test_filter_reasons_has_entry_for_each_dropped_buyer(
        self, biogas_facility, matcher
    ):
        buyers = [
            BuyerProfile("GOOD", "biogas", 100.0, {"methane_pct": 55.0}, 80.0, 51.6, -0.2, max_road_distance_km=500.0),
            BuyerProfile("BAD-PRODUCT", "digestate", 100.0, {}, 80.0, 51.6, -0.2),
            BuyerProfile("BAD-SPEC", "biogas", 100.0, {"methane_pct": 99.0}, 90.0, 51.6, -0.2, max_road_distance_km=500.0),
        ]
        result = matcher.match(biogas_facility, buyers)
        assert "BAD-PRODUCT" in result.filter_reasons
        assert "BAD-SPEC" in result.filter_reasons
        assert "GOOD" not in result.filter_reasons
