"""
Unit tests for:
  - app.schemas.data   (Metadata, FeedstockField, Feedstock, LocationContext)
  - app.data.service   (get_stream, get_location_context)
  - app.ml.predictor   (YieldPredictor)

Coverage:
  Feedstock schema:
  - get_stream() returns a dict that validates against Feedstock without error
  - All metadata kind fields default to "estimated"
  - All metadata source_id fields default to "default_v1"
  - organic + plastic + paper + other fractions sum to 1.0
  - Root validator rejects fractions that don't sum to 1.0
  - Root validator accepts fractions summing to 1.0 within floating-point tolerance

  LocationContext schema:
  - get_location_context() validates against LocationContext without error
  - facilities list is non-empty
  - every FacilityEntry has a road_km key > 0
  - electricity_tariff_inr_per_kwh defaults to 7.50
  - compost_price_inr_per_kg defaults to 4.0
  - grid_available defaults to True

  YieldPredictor:
  - predict_yield() returns dict with required keys
  - total_mass_kg_d > 0 for positive area
  - dry_matter_kg_d ≤ total_mass_kg_d (can't have more dry matter than total mass)
  - biogas_m3_d > 0 for organic crops
  - Unknown crop falls back to _default without raising
  - area_ha ≤ 0 raises ValueError
  - soil_index clamping: soil_index=0 produces non-zero output (clamped to 0.05)
  - Larger area → proportionally larger total_mass_kg_d
"""

import math
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.schemas.data import (
    Feedstock,
    FeedstockField,
    LocationContext,
    Metadata,
)
from app.data.service import (
    get_stream,
    get_location_context,
    _DEFAULT_ELECTRICITY_TARIFF_INR_KWH,
    _DEFAULT_COMPOST_PRICE_INR_KG,
    _DEFAULT_AMBIENT_TEMP_C,
    _DEFAULT_RELATIVE_HUMIDITY,
    _DEFAULT_RAINFALL_MM_D,
)
from app.ml.predictor import YieldPredictor


# ===========================================================================
# Feedstock schema + service
# ===========================================================================

class TestGetStream:
    def test_returns_dict(self):
        result = get_stream("loc-001")
        assert isinstance(result, dict)

    def test_validates_against_feedstock_schema(self):
        """get_stream() dict must parse into Feedstock without ValidationError."""
        data = get_stream("loc-001")
        fs = Feedstock(**data)
        assert isinstance(fs, Feedstock)

    def test_all_metadata_kind_is_estimated(self):
        data = get_stream("loc-xyz")
        scalar_fields = [
            "total_mass_kg_d", "organic_fraction", "plastic_fraction",
            "paper_fraction", "other_fraction", "moisture_fraction",
            "ash_fraction_dry", "lhv_dry_mj_per_kg", "contamination_pct",
        ]
        for key in scalar_fields:
            meta = data[key]["meta"]
            assert meta["kind"] == "estimated", (
                f"Expected kind='estimated' for '{key}', got '{meta['kind']}'"
            )

    def test_all_metadata_source_id_is_default_v1(self):
        data = get_stream("loc-xyz")
        scalar_fields = [
            "total_mass_kg_d", "organic_fraction", "plastic_fraction",
            "paper_fraction", "other_fraction", "moisture_fraction",
            "ash_fraction_dry", "lhv_dry_mj_per_kg", "contamination_pct",
        ]
        for key in scalar_fields:
            meta = data[key]["meta"]
            assert meta["source_id"] == "default_v1", (
                f"Expected source_id='default_v1' for '{key}', got '{meta['source_id']}'"
            )

    def test_composition_fractions_sum_to_one(self):
        """organic + plastic + paper + other + lignocellulosic must equal 1.0 (defaults)."""
        data = get_stream("loc-001")
        total = (
            data["organic_fraction"]["value"]
            + data["plastic_fraction"]["value"]
            + data["paper_fraction"]["value"]
            + data["other_fraction"]["value"]
            + data["lignocellulosic_fraction"]["value"]
        )
        assert math.isclose(total, 1.0, abs_tol=1e-6), (
            f"Composition fractions sum to {total:.8f}, expected 1.0"
        )

    def test_different_location_ids_return_identical_defaults(self):
        """Phase 1: all locations return the same default values."""
        a = get_stream("farm-a")
        b = get_stream("farm-b")
        assert a["lhv_dry_mj_per_kg"]["value"] == b["lhv_dry_mj_per_kg"]["value"]

    def test_total_mass_positive(self):
        data = get_stream("loc-001")
        assert data["total_mass_kg_d"]["value"] > 0

    def test_lhv_default_value(self):
        data = get_stream("loc-001")
        assert math.isclose(data["lhv_dry_mj_per_kg"]["value"], 16.5, rel_tol=1e-9)

    def test_contamination_pct_default_value(self):
        data = get_stream("loc-001")
        assert math.isclose(data["contamination_pct"]["value"], 5.0, rel_tol=1e-9)


class TestFeedstockValidator:
    """Root validator on Feedstock — fraction sum enforcement."""

    def _make_data(
        self,
        organic: float = 0.55,
        plastic: float = 0.09,
        paper: float = 0.07,
        other: float = 0.29,
    ) -> dict:
        """Build a minimal valid Feedstock dict with custom fractions."""
        meta = {"kind": "estimated", "resolution": "n/a", "source_id": "default_v1"}
        return {
            "total_mass_kg_d":    {"value": 1000.0, "meta": meta},
            "organic_fraction":   {"value": organic, "meta": meta},
            "plastic_fraction":   {"value": plastic, "meta": meta},
            "paper_fraction":     {"value": paper,   "meta": meta},
            "other_fraction":     {"value": other,   "meta": meta},
            "moisture_fraction":  {"value": 0.55,    "meta": meta},
            "ash_fraction_dry":   {"value": 0.18,    "meta": meta},
            "lhv_dry_mj_per_kg":  {"value": 16.5,    "meta": meta},
            "contamination_pct":  {"value": 5.0,     "meta": meta},
        }

    def test_valid_fractions_accepted(self):
        data = self._make_data(0.55, 0.09, 0.07, 0.29)
        fs = Feedstock(**data)
        assert isinstance(fs, Feedstock)

    def test_fractions_summing_to_one_within_tolerance_accepted(self):
        """1/3 × 3 fractions close to 1.0 — floating-point edge case."""
        third = 1.0 / 3.0
        data = self._make_data(third, third, third, 0.0)
        # 3 × (1/3) may not be exactly 1.0 due to float representation
        fs = Feedstock(**data)
        assert isinstance(fs, Feedstock)

    def test_fractions_not_summing_to_one_raises(self):
        """Fractions summing to 0.90 must raise ValidationError."""
        from pydantic import ValidationError
        data = self._make_data(organic=0.40, plastic=0.20, paper=0.10, other=0.20)
        with pytest.raises(ValidationError, match="sum to 1.0"):
            Feedstock(**data)

    def test_fractions_summing_to_more_than_one_raises(self):
        """Fractions summing to 1.10 must raise ValidationError."""
        from pydantic import ValidationError
        data = self._make_data(organic=0.60, plastic=0.20, paper=0.15, other=0.15)
        with pytest.raises(ValidationError, match="sum to 1.0"):
            Feedstock(**data)


# ===========================================================================
# LocationContext schema + service
# ===========================================================================

class TestGetLocationContext:
    def test_returns_dict(self):
        result = get_location_context("loc-001")
        assert isinstance(result, dict)

    def test_validates_against_location_context_schema(self):
        """get_location_context() dict must parse into LocationContext."""
        data = get_location_context("loc-001")
        ctx = LocationContext(**data)
        assert isinstance(ctx, LocationContext)

    def test_facilities_list_is_non_empty(self):
        data = get_location_context("loc-001")
        assert len(data["facilities"]) > 0

    def test_every_facility_has_road_km(self):
        data = get_location_context("loc-001")
        for fac in data["facilities"]:
            assert "road_km" in fac, f"Facility entry missing 'road_km': {fac}"
            assert fac["road_km"] > 0, (
                f"road_km must be > 0, got {fac['road_km']} for pathway '{fac.get('pathway')}'"
            )

    def test_every_facility_has_capacity_t_d(self):
        data = get_location_context("loc-001")
        for fac in data["facilities"]:
            assert "capacity_t_d" in fac
            assert fac["capacity_t_d"] > 0

    def test_every_facility_has_pathway_string(self):
        data = get_location_context("loc-001")
        for fac in data["facilities"]:
            assert isinstance(fac["pathway"], str)
            assert len(fac["pathway"]) > 0

    def test_electricity_tariff_default(self):
        data = get_location_context("loc-001")
        val = data["electricity_tariff_inr_per_kwh"]["value"]
        assert math.isclose(val, _DEFAULT_ELECTRICITY_TARIFF_INR_KWH, rel_tol=1e-9)

    def test_compost_price_default(self):
        data = get_location_context("loc-001")
        val = data["compost_price_inr_per_kg"]["value"]
        assert math.isclose(val, _DEFAULT_COMPOST_PRICE_INR_KG, rel_tol=1e-9)

    def test_grid_available_defaults_true(self):
        data = get_location_context("loc-001")
        assert data["grid_available"] is True

    def test_metadata_kind_estimated_for_scalars(self):
        data = get_location_context("loc-001")
        for key in ("electricity_tariff_inr_per_kwh", "compost_price_inr_per_kg", "heat_price_inr_per_kwh"):
            assert data[key]["meta"]["kind"] == "estimated"
            assert data[key]["meta"]["source_id"] == "default_v1"

    # --- new weather field tests ---

    def test_ambient_temp_c_present_and_default(self):
        data = get_location_context("loc-001")
        assert "ambient_temp_c" in data
        assert math.isclose(data["ambient_temp_c"]["value"], _DEFAULT_AMBIENT_TEMP_C, rel_tol=1e-9)

    def test_relative_humidity_present_and_default(self):
        data = get_location_context("loc-001")
        assert "relative_humidity" in data
        assert math.isclose(data["relative_humidity"]["value"], _DEFAULT_RELATIVE_HUMIDITY, rel_tol=1e-9)

    def test_rainfall_mm_d_present_and_default(self):
        data = get_location_context("loc-001")
        assert "rainfall_mm_d" in data
        assert math.isclose(data["rainfall_mm_d"]["value"], _DEFAULT_RAINFALL_MM_D, abs_tol=1e-9)

    def test_weather_metadata_is_estimated(self):
        data = get_location_context("loc-001")
        for key in ("ambient_temp_c", "relative_humidity", "rainfall_mm_d"):
            assert data[key]["meta"]["kind"] == "estimated", f"{key} meta.kind should be 'estimated'"
            assert data[key]["meta"]["source_id"] == "default_v1", f"{key} meta.source_id should be 'default_v1'"

    # --- new sinks field tests ---

    def test_sinks_list_present_and_non_empty(self):
        data = get_location_context("loc-001")
        assert "sinks" in data
        assert len(data["sinks"]) >= 2

    def test_every_sink_has_required_keys(self):
        data = get_location_context("loc-001")
        required = {"customer_class", "accepts", "demand_kwh_d", "road_km", "price"}
        for i, sink in enumerate(data["sinks"]):
            missing = required - sink.keys()
            assert not missing, f"sink[{i}] missing keys: {missing}"

    def test_every_sink_has_positive_demand_and_price(self):
        data = get_location_context("loc-001")
        for sink in data["sinks"]:
            assert sink["demand_kwh_d"] > 0, f"demand_kwh_d must be > 0: {sink}"
            assert sink["price"] > 0, f"price must be > 0: {sink}"

    def test_every_sink_has_road_km(self):
        data = get_location_context("loc-001")
        for sink in data["sinks"]:
            assert "road_km" in sink
            assert sink["road_km"] > 0, f"road_km must be > 0: {sink}"

    def test_every_sink_accepts_is_non_empty_list(self):
        data = get_location_context("loc-001")
        for sink in data["sinks"]:
            assert isinstance(sink["accepts"], list)
            assert len(sink["accepts"]) > 0

    def test_schema_validates_with_new_fields(self):
        """Full LocationContext round-trip with new weather + sinks fields."""
        from app.schemas.data import LocationContext
        data = get_location_context("loc-001")
        ctx = LocationContext(**data)
        assert len(ctx.sinks) >= 2
        assert ctx.ambient_temp_c.value == _DEFAULT_AMBIENT_TEMP_C


# ===========================================================================
# YieldPredictor
# ===========================================================================

class TestYieldPredictor:
    @pytest.fixture
    def predictor(self) -> YieldPredictor:
        return YieldPredictor()

    def test_returns_dict_with_required_keys(self, predictor):
        result = predictor.predict_yield("maize", area_ha=5.0, soil_index=0.75)
        assert "total_mass_kg_d" in result
        assert "dry_matter_kg_d" in result
        assert "biogas_m3_d" in result

    def test_total_mass_positive_for_positive_area(self, predictor):
        result = predictor.predict_yield("maize", area_ha=10.0, soil_index=1.0)
        assert result["total_mass_kg_d"] > 0.0

    def test_dry_matter_leq_total_mass(self, predictor):
        """Dry matter cannot exceed total fresh mass."""
        result = predictor.predict_yield("wheat", area_ha=3.0, soil_index=0.8)
        assert result["dry_matter_kg_d"] <= result["total_mass_kg_d"] + 1e-9, (
            f"dry_matter={result['dry_matter_kg_d']} > total_mass={result['total_mass_kg_d']}"
        )

    def test_biogas_positive_for_organic_crop(self, predictor):
        result = predictor.predict_yield("maize", area_ha=2.0, soil_index=1.0)
        assert result["biogas_m3_d"] > 0.0

    def test_unknown_crop_falls_back_to_default(self, predictor):
        """Unrecognised crop type must not raise — falls back to _default table row."""
        result = predictor.predict_yield("bluemoon_grass", area_ha=1.0, soil_index=0.5)
        assert result["total_mass_kg_d"] > 0.0

    def test_zero_area_raises_value_error(self, predictor):
        with pytest.raises(ValueError, match="area_ha"):
            predictor.predict_yield("maize", area_ha=0.0, soil_index=0.75)

    def test_negative_area_raises_value_error(self, predictor):
        with pytest.raises(ValueError, match="area_ha"):
            predictor.predict_yield("rice", area_ha=-5.0, soil_index=0.5)

    def test_soil_index_zero_clamped_to_nonzero_output(self, predictor):
        """soil_index=0.0 is clamped to 0.05 — must produce a non-zero yield."""
        result = predictor.predict_yield("maize", area_ha=5.0, soil_index=0.0)
        assert result["total_mass_kg_d"] > 0.0

    def test_larger_area_gives_proportionally_larger_mass(self, predictor):
        """yield should scale linearly with area (same soil index).

        Uses rel_tol=1e-3 to accommodate rounding in the daily conversion
        (dividing by 365.25 then rounding to 4 dp introduces <0.01 % error).
        """
        r1 = predictor.predict_yield("rice", area_ha=1.0, soil_index=0.8)
        r2 = predictor.predict_yield("rice", area_ha=4.0, soil_index=0.8)
        ratio = r2["total_mass_kg_d"] / r1["total_mass_kg_d"]
        assert math.isclose(ratio, 4.0, rel_tol=1e-3), (
            f"Expected 4x scaling, got {ratio:.6f}"
        )

    def test_higher_soil_index_gives_higher_yield(self, predictor):
        """Better soil quality → higher yield."""
        low = predictor.predict_yield("wheat", area_ha=10.0, soil_index=0.3)
        high = predictor.predict_yield("wheat", area_ha=10.0, soil_index=0.9)
        assert high["total_mass_kg_d"] > low["total_mass_kg_d"]

    def test_case_insensitive_crop_lookup(self, predictor):
        """'MAIZE', 'Maize', 'maize' should all return the same result."""
        r_lower = predictor.predict_yield("maize", area_ha=5.0, soil_index=0.7)
        r_upper = predictor.predict_yield("MAIZE", area_ha=5.0, soil_index=0.7)
        r_mixed = predictor.predict_yield("Maize", area_ha=5.0, soil_index=0.7)
        assert r_lower["total_mass_kg_d"] == r_upper["total_mass_kg_d"]
        assert r_lower["total_mass_kg_d"] == r_mixed["total_mass_kg_d"]

    def test_all_crops_in_table_produce_valid_output(self, predictor):
        """Every registered crop must produce a non-zero, finite result."""
        from app.ml.predictor import _CROP_TABLE
        for crop in _CROP_TABLE:
            if crop == "_default":
                continue
            result = predictor.predict_yield(crop, area_ha=2.0, soil_index=0.7)
            assert result["total_mass_kg_d"] > 0, f"Zero mass for crop '{crop}'"
            assert math.isfinite(result["biogas_m3_d"]), f"Non-finite biogas for '{crop}'"
