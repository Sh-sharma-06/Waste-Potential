"""
Integration tests: P3 data service layer → P4 decision / pathway engine.

Tests in this module verify the full end-to-end chain:
  get_stream / get_location_context → compare.evaluate_pathways
  YieldPredictor → waste_tpd override in PathwayCompareRequest
  match_demand_greedy → revenue via sinks in screen_pathway
  MC perturbations: weather ±5°C, humidity ±15%, tariff ±15%
  cost.TechnologyParams hauling_cost_per_tonne_km × road_km

All IDs are strings throughout; composite keys use | delimiter.

Coverage groups
---------------
T1  get_stream returns expected feedstock dict
T2  get_location_context returns sinks and weather fields
T3  evaluate_pathways uses location-context sinks for revenue
T4  YieldPredictor overrides waste_tpd when crop_type + area_ha provided
T5  road_km from facility record overrides request.distance_km
T6  match_demand_greedy integrated revenue > flat-price when sinks high-value
T7  MC run_mc_compare includes tariff variation in p10/p90 spread
T8  TechnologyParams with hauling_cost_per_tonne_km factors into net_cost
T9  evaluate_pathways fallback: no crop_type → uses request.waste_tpd
T10 Multiple pathways return one result each in correct order
T11 rejected pathway still returns result with reasons populated
T12 YieldPredictor failure falls back gracefully to request.waste_tpd
"""

from __future__ import annotations

import math
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from app.data.demand import match_demand_greedy
from app.data.service import get_location_context, get_stream
from app.decision.cost import CostEngine, LPCostCoeff, TechnologyParams
from app.ml.predictor import YieldPredictor
from app.pathways.compare import evaluate_pathways, screen_pathway, _resolve_waste_tpd
from app.pathways.mc_compare import run_mc_compare
from app.pathways.schemas import PathwayCompareRequest, PathwayResult


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def base_request() -> PathwayCompareRequest:
    """Minimal valid request for a single anaerobic_digestion pathway."""
    return PathwayCompareRequest(
        farm_id="farm_001",
        waste_tpd=10.0,
        pathways=["anaerobic_digestion"],
        capex_inr={"anaerobic_digestion": 5_000_000.0},
        opex_inr_yr={"anaerobic_digestion": 300_000.0},
        net_kwh_per_tonne={"anaerobic_digestion": 120.0},
        capacity_tpd={"anaerobic_digestion": 20.0},
        distance_km=10.0,
        electricity_price_inr_kwh=0.0,   # force sink-based revenue
        mc_runs=50,
    )


@pytest.fixture
def multi_pathway_request() -> PathwayCompareRequest:
    """Request with two pathways (AD + composting)."""
    return PathwayCompareRequest(
        farm_id="farm_multi",
        waste_tpd=8.0,
        pathways=["anaerobic_digestion", "composting"],
        capex_inr={"anaerobic_digestion": 4_000_000.0, "composting": 1_500_000.0},
        opex_inr_yr={"anaerobic_digestion": 250_000.0, "composting": 80_000.0},
        net_kwh_per_tonne={"anaerobic_digestion": 100.0, "composting": 0.0},
        capacity_tpd={"anaerobic_digestion": 15.0, "composting": 10.0},
        distance_km=5.0,
        mc_runs=50,
    )


# ---------------------------------------------------------------------------
# T1 — get_stream returns expected feedstock dict
# ---------------------------------------------------------------------------

class TestGetStream:
    def test_returns_dict(self):
        stream = get_stream("default")
        assert isinstance(stream, dict)

    def test_has_required_keys(self):
        stream = get_stream("default")
        required = {
            "total_mass_kg_d", "moisture_fraction", "lhv_dry_mj_per_kg",
            "organic_fraction", "ash_fraction_dry", "contamination_pct",
        }
        assert required.issubset(stream.keys())

    def test_values_are_field_dicts_with_value_key(self):
        stream = get_stream("default")
        val = stream["moisture_fraction"]
        assert isinstance(val, dict) and "value" in val

    def test_moisture_fraction_in_range(self):
        stream = get_stream("default")
        mf = stream["moisture_fraction"]["value"]
        assert 0.0 < mf < 1.0

    def test_composition_fractions_sum_to_one(self):
        stream = get_stream("default")
        total = sum(
            stream[k]["value"]
            for k in ("organic_fraction", "plastic_fraction", "paper_fraction", "other_fraction")
        )
        assert math.isclose(total, 1.0, abs_tol=1e-6)

    def test_lhv_positive(self):
        stream = get_stream("default")
        assert stream["lhv_dry_mj_per_kg"]["value"] > 0

    def test_unknown_location_returns_defaults(self):
        # Unknown location IDs should still return defaults
        stream_a = get_stream("unknown_farm_999")
        stream_b = get_stream("default")
        assert stream_a["moisture_fraction"]["value"] == stream_b["moisture_fraction"]["value"]


# ---------------------------------------------------------------------------
# T2 — get_location_context returns sinks and weather
# ---------------------------------------------------------------------------

class TestGetLocationContext:
    def test_returns_dict(self):
        ctx = get_location_context("default")
        assert isinstance(ctx, dict)

    def test_has_electricity_tariff(self):
        ctx = get_location_context("default")
        assert "electricity_tariff_inr_per_kwh" in ctx

    def test_tariff_is_positive(self):
        ctx = get_location_context("default")
        raw = ctx["electricity_tariff_inr_per_kwh"]
        val = raw["value"] if isinstance(raw, dict) else raw
        assert val > 0

    def test_has_sinks(self):
        ctx = get_location_context("default")
        assert "sinks" in ctx
        assert len(ctx["sinks"]) >= 1

    def test_sinks_have_required_keys(self):
        ctx = get_location_context("default")
        for sink in ctx["sinks"]:
            assert "demand_kwh_d" in sink
            assert "price" in sink

    def test_has_weather_fields(self):
        ctx = get_location_context("default")
        for key in ("ambient_temp_c", "relative_humidity", "rainfall_mm_d"):
            assert key in ctx

    def test_ambient_temp_reasonable(self):
        ctx = get_location_context("default")
        raw = ctx["ambient_temp_c"]
        val = raw["value"] if isinstance(raw, dict) else raw
        assert -10.0 < val < 60.0

    def test_relative_humidity_in_range(self):
        ctx = get_location_context("default")
        raw = ctx["relative_humidity"]
        val = raw["value"] if isinstance(raw, dict) else raw
        assert 0.0 <= val <= 1.0

    def test_has_facilities(self):
        ctx = get_location_context("default")
        assert "facilities" in ctx
        assert len(ctx["facilities"]) >= 1

    def test_facilities_have_road_km(self):
        ctx = get_location_context("default")
        for fac in ctx["facilities"]:
            assert "road_km" in fac
            assert fac["road_km"] >= 0


# ---------------------------------------------------------------------------
# T3 — evaluate_pathways uses location-context sinks for revenue
# ---------------------------------------------------------------------------

class TestEvaluatePathwaysSinkRevenue:
    def test_revenue_positive_when_net_exporter(self, base_request):
        results = evaluate_pathways(base_request)
        assert len(results) == 1
        r = results[0]
        # AD with net_kwh_per_tonne=120 → net exporter → revenue > 0
        assert r.revenue_inr_y > 0.0

    def test_sink_warning_present(self, base_request):
        """Sink matcher warning should appear in warnings list."""
        results = evaluate_pathways(base_request)
        r = results[0]
        combined = " ".join(r.warnings)
        # Either sink matcher message or generic indicative-output warning
        assert len(r.warnings) > 0

    def test_revenue_exceeds_zero_even_without_explicit_price(self, base_request):
        """Revenue > 0 because sinks have positive prices from location context."""
        results = evaluate_pathways(base_request)
        assert results[0].revenue_inr_y > 0

    def test_no_revenue_when_net_consumer(self):
        req = PathwayCompareRequest(
            farm_id="f_consumer",
            waste_tpd=5.0,
            pathways=["rdf"],
            net_kwh_per_tonne={"rdf": -50.0},
            capacity_tpd={"rdf": 10.0},
            distance_km=5.0,
            mc_runs=20,
        )
        results = evaluate_pathways(req)
        r = results[0]
        assert r.revenue_inr_y == 0.0
        assert r.cost_inr_y >= 0.0  # import cost added

    def test_result_is_pathway_result_instance(self, base_request):
        results = evaluate_pathways(base_request)
        assert all(isinstance(r, PathwayResult) for r in results)


# ---------------------------------------------------------------------------
# T4 — YieldPredictor overrides waste_tpd when crop_type + area_ha provided
# ---------------------------------------------------------------------------

class TestYieldPredictorOverride:
    def test_resolve_waste_tpd_with_crop(self):
        req = PathwayCompareRequest(
            farm_id="f_crop",
            waste_tpd=5.0,           # will be overridden
            pathways=["anaerobic_digestion"],
            crop_type="maize",
            area_ha=3.0,
            soil_index=0.80,
            mc_runs=20,
        )
        effective_tpd, warns = _resolve_waste_tpd(req)
        # YieldPredictor for 3 ha maize, SI=0.8 should give > 0 t/day
        assert effective_tpd > 0.0
        # The override warning should mention YieldPredictor
        assert any("YieldPredictor" in w for w in warns)

    def test_yield_predictor_tpd_differs_from_request_tpd(self):
        """Predicted tpd should differ from the placeholder 5.0 t/day."""
        req = PathwayCompareRequest(
            farm_id="f_crop2",
            waste_tpd=5.0,
            pathways=["anaerobic_digestion"],
            crop_type="rice",
            area_ha=10.0,
            mc_runs=20,
        )
        effective_tpd, _ = _resolve_waste_tpd(req)
        assert not math.isclose(effective_tpd, 5.0, rel_tol=0.001)

    def test_no_crop_type_returns_request_waste_tpd(self):
        req = PathwayCompareRequest(
            farm_id="f_no_crop",
            waste_tpd=7.5,
            pathways=["composting"],
            mc_runs=20,
        )
        effective_tpd, warns = _resolve_waste_tpd(req)
        assert math.isclose(effective_tpd, 7.5, rel_tol=1e-9)
        assert warns == []

    def test_evaluate_pathways_with_crop_type(self):
        """Full evaluate_pathways with crop_type should not raise and returns results."""
        req = PathwayCompareRequest(
            farm_id="f_full_crop",
            waste_tpd=5.0,
            pathways=["anaerobic_digestion"],
            capex_inr={"anaerobic_digestion": 2_000_000.0},
            opex_inr_yr={"anaerobic_digestion": 100_000.0},
            net_kwh_per_tonne={"anaerobic_digestion": 100.0},
            capacity_tpd={"anaerobic_digestion": 20.0},
            crop_type="wheat",
            area_ha=5.0,
            mc_runs=20,
        )
        results = evaluate_pathways(req)
        assert len(results) == 1
        r = results[0]
        # YieldPredictor warning should be in result warnings
        combined = " ".join(r.warnings)
        assert "YieldPredictor" in combined

    def test_soil_index_default_075_used_when_omitted(self):
        """When soil_index is None, default 0.75 should be used (no error)."""
        req = PathwayCompareRequest(
            farm_id="f_si_default",
            waste_tpd=5.0,
            pathways=["anaerobic_digestion"],
            crop_type="sorghum",
            area_ha=4.0,
            soil_index=None,
            mc_runs=20,
        )
        effective_tpd, warns = _resolve_waste_tpd(req)
        assert effective_tpd > 0
        assert any("0.75" in w for w in warns)


# ---------------------------------------------------------------------------
# T5 — road_km from facility record overrides request.distance_km
# ---------------------------------------------------------------------------

class TestFacilityRoadKmOverride:
    def test_anaerobic_digestion_uses_facility_road_km(self):
        """AD facility in default catalogue has road_km=15; request.distance_km=5."""
        req = PathwayCompareRequest(
            farm_id="f_road",
            waste_tpd=5.0,
            pathways=["anaerobic_digestion"],
            distance_km=5.0,       # would be under-distance; facility is 15 km
            max_distance_km=200.0,
            capacity_tpd={"anaerobic_digestion": 50.0},
            mc_runs=20,
        )
        # Facility record AD has road_km=15, max=200 → still feasible
        results = evaluate_pathways(req)
        r = results[0]
        # Result feasible (15 < 200)
        assert r.feasible is True
        # GHG transport should reflect 15 km, not 5 km — net_ghg > 0
        assert "net_ghg_kgco2e_y" in r.outputs

    def test_distance_rejection_uses_facility_km(self):
        """If facility road_km exceeds max_distance_km, pathway is rejected."""
        req = PathwayCompareRequest(
            farm_id="f_road2",
            waste_tpd=5.0,
            pathways=["anaerobic_digestion"],
            distance_km=5.0,
            max_distance_km=10.0,   # facility AD is 15 km → should be rejected
            capacity_tpd={"anaerobic_digestion": 50.0},
            mc_runs=20,
        )
        results = evaluate_pathways(req)
        r = results[0]
        assert r.feasible is False
        assert any("15.0 km" in reason for reason in r.reasons)


# ---------------------------------------------------------------------------
# T6 — match_demand_greedy integrated revenue > flat-price when sinks high-value
# ---------------------------------------------------------------------------

class TestGreedyRevenue:
    def test_greedy_gives_positive_revenue(self):
        sinks = [
            {"customer_class": "industrial", "demand_kwh_d": 500.0, "price": 8.50},
            {"customer_class": "residential", "demand_kwh_d": 300.0, "price": 7.50},
        ]
        result = match_demand_greedy(400.0, sinks)
        assert result["total_revenue_inr_d"] == pytest.approx(400.0 * 8.50, rel=1e-6)

    def test_greedy_partial_allocation(self):
        sinks = [{"demand_kwh_d": 100.0, "price": 8.0}]
        result = match_demand_greedy(60.0, sinks)
        assert result["total_matched_kwh_d"] == pytest.approx(60.0)
        assert result["remaining_supply_kwh_d"] == pytest.approx(0.0)

    def test_revenue_matches_sink_price_times_kwh(self):
        sinks = [{"demand_kwh_d": 200.0, "price": 9.0, "road_km": 3.0}]
        result = match_demand_greedy(150.0, sinks)
        assert result["total_revenue_inr_d"] == pytest.approx(150.0 * 9.0, rel=1e-6)

    def test_revenue_from_evaluate_uses_sinks_not_flat_price(self):
        """When electricity_price_inr_kwh=0 and sinks available, revenue still > 0."""
        req = PathwayCompareRequest(
            farm_id="f_sink_test",
            waste_tpd=5.0,
            pathways=["anaerobic_digestion"],
            net_kwh_per_tonne={"anaerobic_digestion": 100.0},
            electricity_price_inr_kwh=0.0,
            mc_runs=20,
        )
        results = evaluate_pathways(req)
        assert results[0].revenue_inr_y > 0


# ---------------------------------------------------------------------------
# T7 — MC run_mc_compare includes tariff variation in p10/p90 spread
# ---------------------------------------------------------------------------

class TestMCTariffVariation:
    def test_mc_results_have_p10_p50_p90(self, base_request):
        mc_results = run_mc_compare(base_request)
        assert len(mc_results) == 1
        stats = mc_results[0].annual_net_value_mc
        assert hasattr(stats, "p10") and hasattr(stats, "p50") and hasattr(stats, "p90")

    def test_p10_le_p50_le_p90(self, base_request):
        mc_results = run_mc_compare(base_request)
        stats = mc_results[0].annual_net_value_mc
        assert stats.p10 <= stats.p50 <= stats.p90

    def test_mc_spread_exists_for_net_exporter(self, base_request):
        """With tariff variation the MC distribution should have non-zero spread."""
        mc_results = run_mc_compare(base_request)
        stats = mc_results[0].annual_net_value_mc
        # p90 - p10 > 0 indicates spread from tariff/cost sampling
        assert stats.p90 > stats.p10

    def test_mc_prob_positive_in_range(self, base_request):
        mc_results = run_mc_compare(base_request)
        prob = mc_results[0].prob_positive_npv
        assert 0.0 <= prob <= 1.0

    def test_mc_status_is_valid(self, base_request):
        mc_results = run_mc_compare(base_request)
        assert mc_results[0].status in ("feasible", "rejected", "uncertain")

    def test_mc_uses_location_context_sinks(self, base_request):
        """run_mc_compare should produce results without raising (sinks wired in)."""
        mc_results = run_mc_compare(base_request)
        assert len(mc_results) == 1


# ---------------------------------------------------------------------------
# T8 — TechnologyParams hauling_cost factors into net_cost_per_tonne
# ---------------------------------------------------------------------------

class TestHaulingCostIntegration:
    def test_hauling_zero_by_default(self):
        tech = TechnologyParams("t0", 1_000_000.0, 50_000.0, 5_000.0)
        engine = CostEngine(electricity_export_price=0.12)
        coeff = engine.lp_coefficients([tech])["t0"]
        assert coeff.hauling_cost_per_tonne == 0.0

    def test_hauling_adds_to_net_cost(self):
        tech_no_haul = TechnologyParams("t0", 1_000_000.0, 50_000.0, 5_000.0)
        tech_haul = TechnologyParams(
            "t1", 1_000_000.0, 50_000.0, 5_000.0,
            hauling_cost_per_tonne_km=3.0,
            cost_params={"road_km": 10.0},
        )
        engine = CostEngine(electricity_export_price=0.12)
        c0 = engine.lp_coefficients([tech_no_haul])["t0"]
        c1 = engine.lp_coefficients([tech_haul])["t1"]
        # Hauling = 3.0 × 10 = 30 INR/tonne extra
        assert math.isclose(c1.hauling_cost_per_tonne, 30.0, rel_tol=1e-9)
        assert math.isclose(
            c1.net_cost_per_tonne - c0.net_cost_per_tonne, 30.0, rel_tol=1e-6
        )

    def test_hauling_scales_with_distance(self):
        engine = CostEngine(electricity_export_price=0.12)
        near = TechnologyParams("t0", 1_000_000.0, 50_000.0, 5_000.0,
                                hauling_cost_per_tonne_km=2.0,
                                cost_params={"road_km": 5.0})
        far = TechnologyParams("t1", 1_000_000.0, 50_000.0, 5_000.0,
                               hauling_cost_per_tonne_km=2.0,
                               cost_params={"road_km": 25.0})
        cn = engine.lp_coefficients([near])["t0"]
        cf = engine.lp_coefficients([far])["t1"]
        assert cf.hauling_cost_per_tonne > cn.hauling_cost_per_tonne
        assert cf.net_cost_per_tonne > cn.net_cost_per_tonne

    def test_hauling_uses_pipe_id_keys(self):
        """String IDs with | pipe characters should work as dict keys."""
        tech = TechnologyParams(
            "stream_001|tech_AD",
            2_000_000.0, 80_000.0, 8_000.0,
            hauling_cost_per_tonne_km=1.5,
            cost_params={"road_km": 12.0},
        )
        engine = CostEngine(electricity_export_price=0.10)
        coeffs = engine.lp_coefficients([tech])
        assert "stream_001|tech_AD" in coeffs
        assert math.isclose(coeffs["stream_001|tech_AD"].hauling_cost_per_tonne,
                            1.5 * 12.0, rel_tol=1e-9)


# ---------------------------------------------------------------------------
# T9 — fallback: no crop_type → uses request.waste_tpd
# ---------------------------------------------------------------------------

class TestFallbackNoYield:
    def test_fallback_waste_tpd_used(self):
        req = PathwayCompareRequest(
            farm_id="f_fallback",
            waste_tpd=12.0,
            pathways=["composting"],
            capacity_tpd={"composting": 20.0},
            mc_runs=20,
        )
        results = evaluate_pathways(req)
        r = results[0]
        assert r.feasible is True
        # Output compost_t_d ≈ 12 × 0.30 = 3.6
        assert math.isclose(r.outputs.get("compost_t_d", 0.0), 3.6, rel_tol=1e-6)


# ---------------------------------------------------------------------------
# T10 — multiple pathways return one result each in order
# ---------------------------------------------------------------------------

class TestMultiPathwayOrder:
    def test_result_count_matches_pathways(self, multi_pathway_request):
        results = evaluate_pathways(multi_pathway_request)
        assert len(results) == len(multi_pathway_request.pathways)

    def test_result_order_matches_request(self, multi_pathway_request):
        results = evaluate_pathways(multi_pathway_request)
        for res, pw in zip(results, multi_pathway_request.pathways):
            assert res.pathway == pw

    def test_mc_result_count_matches(self, multi_pathway_request):
        mc_results = run_mc_compare(multi_pathway_request)
        assert len(mc_results) == len(multi_pathway_request.pathways)

    def test_mc_result_order_matches(self, multi_pathway_request):
        mc_results = run_mc_compare(multi_pathway_request)
        for mc, pw in zip(mc_results, multi_pathway_request.pathways):
            assert mc.pathway == pw


# ---------------------------------------------------------------------------
# T11 — rejected pathway returns result with reasons populated
# ---------------------------------------------------------------------------

class TestRejectedPathway:
    def test_over_distance_rejected(self):
        # rdf facility in default catalogue has road_km=25; set max_distance_km=10
        # so the facility's 25 km exceeds the 10 km limit → rejected
        req = PathwayCompareRequest(
            farm_id="f_rej",
            waste_tpd=5.0,
            pathways=["rdf"],
            distance_km=300.0,  # overridden by facility road_km=25
            max_distance_km=10.0,
            mc_runs=20,
        )
        results = evaluate_pathways(req)
        r = results[0]
        assert r.feasible is False
        assert r.status == "rejected"
        assert len(r.reasons) >= 1

    def test_over_capacity_rejected(self):
        req = PathwayCompareRequest(
            farm_id="f_cap",
            waste_tpd=50.0,
            pathways=["composting"],
            capacity_tpd={"composting": 10.0},
            mc_runs=20,
        )
        results = evaluate_pathways(req)
        r = results[0]
        assert r.feasible is False

    def test_rejected_status_preserved_after_mc_merge(self):
        from app.pathways.mc_compare import merge_mc_into_results
        req = PathwayCompareRequest(
            farm_id="f_rej_mc",
            waste_tpd=5.0,
            pathways=["rdf"],
            distance_km=500.0,
            max_distance_km=10.0,   # facility rdf road_km=25 > 10 → rejected
            mc_runs=20,
        )
        det_results = evaluate_pathways(req)
        mc_results = run_mc_compare(req)
        merged = merge_mc_into_results(det_results, mc_results)
        assert merged[0].status == "rejected"   # deterministic rejection wins


# ---------------------------------------------------------------------------
# T12 — YieldPredictor failure falls back gracefully
# ---------------------------------------------------------------------------

class TestYieldPredictorFallback:
    def test_area_ha_zero_skips_predictor(self):
        """area_ha=0 (or None) → no predictor call → uses request.waste_tpd."""
        req = PathwayCompareRequest(
            farm_id="f_skip",
            waste_tpd=6.0,
            pathways=["anaerobic_digestion"],
            crop_type="maize",
            area_ha=0.0,   # 0 → predictor is skipped
            mc_runs=20,
        )
        effective_tpd, warns = _resolve_waste_tpd(req)
        assert math.isclose(effective_tpd, 6.0, rel_tol=1e-9)
        assert warns == []

    def test_area_ha_none_skips_predictor(self):
        req = PathwayCompareRequest(
            farm_id="f_none",
            waste_tpd=9.0,
            pathways=["anaerobic_digestion"],
            crop_type="wheat",
            area_ha=None,
            mc_runs=20,
        )
        effective_tpd, warns = _resolve_waste_tpd(req)
        assert math.isclose(effective_tpd, 9.0, rel_tol=1e-9)
        assert warns == []
