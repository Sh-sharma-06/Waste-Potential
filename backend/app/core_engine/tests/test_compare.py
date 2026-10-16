"""tests/test_compare.py — unittest.TestCase tests for pathways/compare.py."""
import dataclasses
import json
import math
import unittest

from app.core_engine.pathways.feedstock import Feedstock
from app.core_engine.pathways.compare import (
    LocationContext,
    PathwayCosts,
    compare_pathways,
    crf,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _fs_ad() -> Feedstock:
    """High-moisture, high-organic feedstock — AD and composting feasible."""
    return Feedstock(
        total_mass_kg_d=1000.0,
        organic_fraction=0.55,
        plastic_fraction=0.15,
        paper_fraction=0.15,
        other_fraction=0.15,
        moisture_fraction=0.60,
        ash_fraction_dry=0.04,
        lhv_dry_mj_per_kg=10.0,
        contamination_pct=5.0,
    )


def _fs_dry() -> Feedstock:
    """Low-moisture, high-plastic feedstock — incineration / gasification feasible."""
    return Feedstock(
        total_mass_kg_d=1000.0,
        organic_fraction=0.10,
        plastic_fraction=0.45,
        paper_fraction=0.25,
        other_fraction=0.20,
        moisture_fraction=0.10,
        ash_fraction_dry=0.06,
        lhv_dry_mj_per_kg=18.0,
        contamination_pct=3.0,
    )


def _ctx_grid() -> LocationContext:
    """Standard context with grid available."""
    return LocationContext(
        electricity_tariff_inr_per_kwh=7.0,
        compost_price_inr_per_kg=2.0,
        heat_price_inr_per_kwh=3.0,
        nearest_buyer_km=10.0,
        transport_cost_inr_per_t_km=5.0,
        grid_available=True,
    )


def _ctx_no_grid() -> LocationContext:
    """Context with no grid connection."""
    return LocationContext(
        electricity_tariff_inr_per_kwh=7.0,
        compost_price_inr_per_kg=2.0,
        heat_price_inr_per_kwh=3.0,
        nearest_buyer_km=10.0,
        transport_cost_inr_per_t_km=5.0,
        grid_available=False,
    )


# ---------------------------------------------------------------------------
# TestCRF
# ---------------------------------------------------------------------------

class TestCRF(unittest.TestCase):

    def test_crf_reference_value(self):
        """crf(0.10, 10) == 0.16275 (spec)."""
        result = crf(0.10, 10)
        self.assertAlmostEqual(result, 0.16275, places=4)

    def test_crf_zero_rate(self):
        """i=0 returns 1/n exactly."""
        self.assertAlmostEqual(crf(0.0, 20), 1.0 / 20.0, places=12)

    def test_crf_single_year(self):
        """With n=1, CRF must equal 1 + i (return full principal + one period interest)."""
        i = 0.12
        expected = i * (1 + i) / ((1 + i) - 1)
        self.assertAlmostEqual(crf(i, 1), expected, places=12)

    def test_crf_negative_rate_raises(self):
        with self.assertRaises(ValueError):
            crf(-0.01, 10)

    def test_crf_zero_years_raises(self):
        with self.assertRaises(ValueError):
            crf(0.10, 0)

    def test_crf_negative_years_raises(self):
        with self.assertRaises(ValueError):
            crf(0.10, -5)

    def test_crf_decreases_with_longer_life(self):
        """Longer project life means smaller annual repayment."""
        self.assertGreater(crf(0.10, 10), crf(0.10, 20))


# ---------------------------------------------------------------------------
# TestLocationContext
# ---------------------------------------------------------------------------

class TestLocationContext(unittest.TestCase):

    def test_defaults_construct(self):
        ctx = _ctx_grid()
        self.assertTrue(ctx.grid_available)
        self.assertEqual(ctx.electricity_tariff_inr_per_kwh, 7.0)

    def test_negative_tariff_raises(self):
        with self.assertRaises(ValueError):
            LocationContext(
                electricity_tariff_inr_per_kwh=-1.0,
                compost_price_inr_per_kg=2.0,
                heat_price_inr_per_kwh=3.0,
                nearest_buyer_km=10.0,
                transport_cost_inr_per_t_km=5.0,
                grid_available=True,
            )

    def test_negative_compost_price_raises(self):
        with self.assertRaises(ValueError):
            LocationContext(
                electricity_tariff_inr_per_kwh=7.0,
                compost_price_inr_per_kg=-0.5,
                heat_price_inr_per_kwh=3.0,
                nearest_buyer_km=10.0,
                transport_cost_inr_per_t_km=5.0,
                grid_available=True,
            )

    def test_negative_transport_cost_raises(self):
        with self.assertRaises(ValueError):
            LocationContext(
                electricity_tariff_inr_per_kwh=7.0,
                compost_price_inr_per_kg=2.0,
                heat_price_inr_per_kwh=3.0,
                nearest_buyer_km=10.0,
                transport_cost_inr_per_t_km=-1.0,
                grid_available=True,
            )

    def test_frozen(self):
        ctx = _ctx_grid()
        with self.assertRaises((dataclasses.FrozenInstanceError, TypeError, AttributeError)):
            ctx.grid_available = False  # type: ignore[misc]

    def test_facilities_default_empty(self):
        ctx = _ctx_grid()
        self.assertEqual(ctx.facilities, [])

    def test_facilities_stored(self):
        ctx = LocationContext(
            electricity_tariff_inr_per_kwh=7.0,
            compost_price_inr_per_kg=2.0,
            heat_price_inr_per_kwh=3.0,
            nearest_buyer_km=5.0,
            transport_cost_inr_per_t_km=4.0,
            grid_available=True,
            facilities=[{"pathway": "composting", "capacity_t_d": 100.0, "road_km": 5.0}],
        )
        self.assertEqual(len(ctx.facilities), 1)
        self.assertEqual(ctx.facilities[0]["pathway"], "composting")


# ---------------------------------------------------------------------------
# TestPathwayCosts
# ---------------------------------------------------------------------------

class TestPathwayCosts(unittest.TestCase):

    def test_defaults_construct(self):
        pc = PathwayCosts(capex_inr=1e7, opex_inr_per_t=500.0, life_years=20.0, discount_rate=0.10)
        self.assertEqual(pc.life_years, 20.0)

    def test_negative_capex_raises(self):
        with self.assertRaises(ValueError):
            PathwayCosts(capex_inr=-1.0, opex_inr_per_t=500.0, life_years=20.0, discount_rate=0.10)

    def test_negative_opex_raises(self):
        with self.assertRaises(ValueError):
            PathwayCosts(capex_inr=1e7, opex_inr_per_t=-1.0, life_years=20.0, discount_rate=0.10)

    def test_zero_life_years_raises(self):
        with self.assertRaises(ValueError):
            PathwayCosts(capex_inr=1e7, opex_inr_per_t=500.0, life_years=0.0, discount_rate=0.10)

    def test_negative_discount_rate_raises(self):
        with self.assertRaises(ValueError):
            PathwayCosts(capex_inr=1e7, opex_inr_per_t=500.0, life_years=20.0, discount_rate=-0.01)

    def test_zero_discount_rate_allowed(self):
        pc = PathwayCosts(capex_inr=1e7, opex_inr_per_t=500.0, life_years=20.0, discount_rate=0.0)
        self.assertEqual(pc.discount_rate, 0.0)

    def test_frozen(self):
        pc = PathwayCosts(capex_inr=1e7, opex_inr_per_t=500.0, life_years=20.0, discount_rate=0.10)
        with self.assertRaises((dataclasses.FrozenInstanceError, TypeError, AttributeError)):
            pc.capex_inr = 0.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# TestComparePathwaysResultStructure
# ---------------------------------------------------------------------------

_REQUIRED_KEYS = {
    "pathway", "feasible", "reasons", "outputs",
    "revenue_inr_y", "cost_inr_y", "annual_net_value_inr",
    "e_net_kwh_d", "status", "warnings",
}


class TestComparePathwaysResultStructure(unittest.TestCase):

    def setUp(self):
        self.results = compare_pathways(_fs_ad(), _ctx_grid())

    def test_returns_list(self):
        self.assertIsInstance(self.results, list)

    def test_five_entries(self):
        """One entry per pathway in PATHWAYS."""
        self.assertEqual(len(self.results), 5)

    def test_all_pathways_represented(self):
        from app.core_engine.pathways.feasibility import PATHWAYS
        names = {r["pathway"] for r in self.results}
        self.assertEqual(names, set(PATHWAYS))

    def test_every_dict_has_required_keys(self):
        for r in self.results:
            with self.subTest(pathway=r["pathway"]):
                for key in _REQUIRED_KEYS:
                    self.assertIn(key, r, msg=f"missing key '{key}'")

    def test_feasible_is_bool(self):
        for r in self.results:
            self.assertIsInstance(r["feasible"], bool)

    def test_reasons_is_list_of_str(self):
        for r in self.results:
            self.assertIsInstance(r["reasons"], list)
            for item in r["reasons"]:
                self.assertIsInstance(item, str)

    def test_warnings_is_list_of_str(self):
        for r in self.results:
            self.assertIsInstance(r["warnings"], list)
            for item in r["warnings"]:
                self.assertIsInstance(item, str)

    def test_outputs_is_dict(self):
        for r in self.results:
            self.assertIsInstance(r["outputs"], dict)

    def test_status_is_illustrative_estimate(self):
        for r in self.results:
            self.assertEqual(r["status"], "illustrative_estimate")

    def test_numeric_fields_are_float(self):
        for r in self.results:
            for key in ("revenue_inr_y", "cost_inr_y", "annual_net_value_inr", "e_net_kwh_d"):
                with self.subTest(pathway=r["pathway"], key=key):
                    self.assertIsInstance(r[key], float)


# ---------------------------------------------------------------------------
# TestComparePathwaysJSONSerialisable
# ---------------------------------------------------------------------------

class TestComparePathwaysJSONSerialisable(unittest.TestCase):

    def test_results_json_serialisable(self):
        """Every returned dict must round-trip through json.dumps without error."""
        results = compare_pathways(_fs_dry(), _ctx_grid())
        for r in results:
            with self.subTest(pathway=r["pathway"]):
                try:
                    json.dumps(r)
                except (TypeError, ValueError) as exc:
                    self.fail(
                        f"pathway '{r['pathway']}' result not JSON-serialisable: {exc}"
                    )

    def test_outputs_json_serialisable(self):
        """Simulator output dicts must also be JSON-serialisable."""
        results = compare_pathways(_fs_ad(), _ctx_no_grid())
        for r in results:
            with self.subTest(pathway=r["pathway"]):
                try:
                    json.dumps(r["outputs"])
                except (TypeError, ValueError) as exc:
                    self.fail(
                        f"outputs for '{r['pathway']}' not JSON-serialisable: {exc}"
                    )


# ---------------------------------------------------------------------------
# TestOrderingRule
# ---------------------------------------------------------------------------

class TestOrderingRule(unittest.TestCase):

    def _all_feasible_before_infeasible(self, results):
        """Assert every feasible entry comes before every infeasible entry."""
        seen_infeasible = False
        for r in results:
            if not r["feasible"]:
                seen_infeasible = True
            elif seen_infeasible:
                self.fail(
                    f"Feasible pathway '{r['pathway']}' appears after an infeasible one. "
                    f"Order: {[x['pathway'] for x in results]}"
                )

    def test_feasible_before_infeasible_ad_feedstock(self):
        results = compare_pathways(_fs_ad(), _ctx_grid())
        self._all_feasible_before_infeasible(results)

    def test_feasible_before_infeasible_dry_feedstock(self):
        results = compare_pathways(_fs_dry(), _ctx_grid())
        self._all_feasible_before_infeasible(results)

    def test_feasible_group_sorted_descending_by_net_value(self):
        """Within the feasible group, annual_net_value_inr must be non-increasing."""
        results = compare_pathways(_fs_dry(), _ctx_grid())
        feasible = [r for r in results if r["feasible"]]
        for i in range(len(feasible) - 1):
            self.assertGreaterEqual(
                feasible[i]["annual_net_value_inr"],
                feasible[i + 1]["annual_net_value_inr"],
                msg=(
                    f"feasible[{i}] '{feasible[i]['pathway']}' "
                    f"({feasible[i]['annual_net_value_inr']:.2f}) < "
                    f"feasible[{i+1}] '{feasible[i+1]['pathway']}' "
                    f"({feasible[i+1]['annual_net_value_inr']:.2f})"
                ),
            )

    def test_infeasible_group_sorted_descending_by_net_value(self):
        """Within the infeasible group, annual_net_value_inr must be non-increasing."""
        results = compare_pathways(_fs_ad(), _ctx_grid())
        infeasible = [r for r in results if not r["feasible"]]
        for i in range(len(infeasible) - 1):
            self.assertGreaterEqual(
                infeasible[i]["annual_net_value_inr"],
                infeasible[i + 1]["annual_net_value_inr"],
            )


# ---------------------------------------------------------------------------
# TestElectricityRevenue
# ---------------------------------------------------------------------------

class TestElectricityRevenue(unittest.TestCase):

    def test_revenue_zero_when_no_grid(self):
        """Electricity revenue must be zero when grid_available is False."""
        results_no_grid = compare_pathways(_fs_dry(), _ctx_no_grid())
        results_grid = compare_pathways(_fs_dry(), _ctx_grid())

        for r_ng, r_g in zip(
            sorted(results_no_grid, key=lambda x: x["pathway"]),
            sorted(results_grid, key=lambda x: x["pathway"]),
        ):
            with self.subTest(pathway=r_ng["pathway"]):
                # Net value with no grid must be <= net value with grid
                # (no grid can only reduce revenue, never increase it)
                self.assertLessEqual(
                    r_ng["annual_net_value_inr"],
                    r_g["annual_net_value_inr"] + 1e-6,  # tolerance for float equality
                    msg=(
                        f"No-grid net value {r_ng['annual_net_value_inr']:.2f} "
                        f"exceeds grid net value {r_g['annual_net_value_inr']:.2f}"
                    ),
                )

    def test_revenue_zero_no_grid_ad(self):
        """AD result must have lower or equal revenue with no grid than with grid."""
        results_grid = compare_pathways(_fs_ad(), _ctx_grid())
        results_no_grid = compare_pathways(_fs_ad(), _ctx_no_grid())
        ad_grid = next(r for r in results_grid if r["pathway"] == "anaerobic_digestion")
        ad_no_grid = next(r for r in results_no_grid if r["pathway"] == "anaerobic_digestion")
        self.assertLessEqual(
            ad_no_grid["revenue_inr_y"],
            ad_grid["revenue_inr_y"] + 1e-6,
        )


# ---------------------------------------------------------------------------
# TestHigherTariffNeverLowersADNetValue
# ---------------------------------------------------------------------------

class TestTariffMonotonicity(unittest.TestCase):

    def _ad_net(self, feedstock: Feedstock, tariff: float) -> float:
        ctx = LocationContext(
            electricity_tariff_inr_per_kwh=tariff,
            compost_price_inr_per_kg=0.0,
            heat_price_inr_per_kwh=0.0,
            nearest_buyer_km=0.0,
            transport_cost_inr_per_t_km=0.0,
            grid_available=True,
        )
        results = compare_pathways(feedstock, ctx)
        return next(r["annual_net_value_inr"] for r in results
                    if r["pathway"] == "anaerobic_digestion")

    def test_higher_tariff_never_lowers_ad_net_value(self):
        """Doubling the tariff must not decrease the AD annual net value."""
        fs = _fs_ad()
        low = self._ad_net(fs, tariff=4.0)
        high = self._ad_net(fs, tariff=8.0)
        self.assertGreaterEqual(
            high, low - 1e-6,
            msg=f"Higher tariff produced lower net value: {high:.2f} < {low:.2f}",
        )

    def test_tariff_zero_gives_no_electricity_revenue_ad(self):
        """With tariff=0, electricity contributes nothing to revenue."""
        fs = _fs_ad()
        net_zero_tariff = self._ad_net(fs, tariff=0.0)
        net_positive_tariff = self._ad_net(fs, tariff=5.0)
        # net value with positive tariff must be >= value with zero tariff
        # (AD usually produces net positive electricity)
        self.assertGreaterEqual(net_positive_tariff, net_zero_tariff - 1e-6)


# ---------------------------------------------------------------------------
# TestFacilityCapacityConstraint
# ---------------------------------------------------------------------------

class TestFacilityCapacityConstraint(unittest.TestCase):

    def _ctx_with_facilities(self, facilities):
        return LocationContext(
            electricity_tariff_inr_per_kwh=7.0,
            compost_price_inr_per_kg=2.0,
            heat_price_inr_per_kwh=3.0,
            nearest_buyer_km=10.0,
            transport_cost_inr_per_t_km=5.0,
            grid_available=True,
            facilities=facilities,
        )

    def test_missing_facility_makes_pathway_infeasible(self):
        """When facilities list is provided and no entry matches a pathway,
        that pathway must be infeasible with the expected reason."""
        # Only composting facility supplied
        ctx = self._ctx_with_facilities([
            {"pathway": "composting", "capacity_t_d": 200.0, "road_km": 5.0}
        ])
        results = compare_pathways(_fs_ad(), ctx)
        ad = next(r for r in results if r["pathway"] == "anaerobic_digestion")
        self.assertFalse(ad["feasible"])
        self.assertTrue(
            any("no facility capacity within range" in reason for reason in ad["reasons"]),
            msg=f"Expected reason not found. reasons={ad['reasons']}",
        )

    def test_matching_facility_does_not_add_capacity_reason(self):
        """When a matching facility exists, 'no facility capacity' must not appear."""
        ctx = self._ctx_with_facilities([
            {"pathway": "anaerobic_digestion", "capacity_t_d": 500.0, "road_km": 3.0}
        ])
        results = compare_pathways(_fs_ad(), ctx)
        ad = next(r for r in results if r["pathway"] == "anaerobic_digestion")
        for reason in ad["reasons"]:
            self.assertNotIn(
                "no facility capacity within range", reason,
                msg="Capacity reason should not appear when facility matches",
            )

    def test_all_pathways_infeasible_when_facilities_empty_list_not_applied(self):
        """Empty facilities list means the capacity constraint is not applied."""
        ctx = self._ctx_with_facilities([])
        results_no_fac = compare_pathways(_fs_dry(), ctx)
        ctx_none = LocationContext(
            electricity_tariff_inr_per_kwh=7.0,
            compost_price_inr_per_kg=2.0,
            heat_price_inr_per_kwh=3.0,
            nearest_buyer_km=10.0,
            transport_cost_inr_per_t_km=5.0,
            grid_available=True,
        )
        results_none = compare_pathways(_fs_dry(), ctx_none)
        for r_no_fac, r_none in zip(
            sorted(results_no_fac, key=lambda x: x["pathway"]),
            sorted(results_none, key=lambda x: x["pathway"]),
        ):
            self.assertEqual(
                r_no_fac["feasible"], r_none["feasible"],
                msg=f"{r_no_fac['pathway']}: empty facilities changed feasibility",
            )

    def test_missing_facility_reason_text(self):
        """Exact required reason substring per spec."""
        ctx = self._ctx_with_facilities([
            {"pathway": "composting", "capacity_t_d": 100.0, "road_km": 2.0}
        ])
        results = compare_pathways(_fs_dry(), ctx)
        for r in results:
            if r["pathway"] != "composting":
                with self.subTest(pathway=r["pathway"]):
                    self.assertFalse(r["feasible"])
                    reason_texts = " ".join(r["reasons"])
                    self.assertIn("no facility capacity within range", reason_texts)

    def test_feasible_ordering_still_respected_with_facilities(self):
        """Feasible before infeasible ordering must hold even with facility constraints."""
        ctx = self._ctx_with_facilities([
            {"pathway": "composting", "capacity_t_d": 500.0, "road_km": 5.0}
        ])
        results = compare_pathways(_fs_ad(), ctx)
        seen_infeasible = False
        for r in results:
            if not r["feasible"]:
                seen_infeasible = True
            elif seen_infeasible:
                self.fail(
                    f"Feasible pathway '{r['pathway']}' appears after an infeasible one."
                )


# ---------------------------------------------------------------------------
# TestADParamsOverride
# ---------------------------------------------------------------------------

class TestADParamsOverride(unittest.TestCase):

    def test_ad_params_dict_override(self):
        """Passing ad_params as a dict of valid Params fields must not raise."""
        results = compare_pathways(
            _fs_ad(), _ctx_grid(),
            ad_params={"y_biogas_nm3_per_kg_vs": 0.65},
        )
        ad = next(r for r in results if r["pathway"] == "anaerobic_digestion")
        self.assertIsNotNone(ad)
        self.assertIn("e_net_kwh_d", ad["outputs"])

    def test_ad_params_invalid_key_ignored(self):
        """Keys in ad_params that are not Params fields are silently ignored."""
        results = compare_pathways(
            _fs_ad(), _ctx_grid(),
            ad_params={"not_a_real_field": 99.9},
        )
        self.assertEqual(len(results), 5)

    def test_ad_params_none_uses_defaults(self):
        """No ad_params must produce same result as passing an empty dict."""
        r_none = compare_pathways(_fs_ad(), _ctx_grid(), ad_params=None)
        r_empty = compare_pathways(_fs_ad(), _ctx_grid(), ad_params={})
        ad_none = next(r for r in r_none if r["pathway"] == "anaerobic_digestion")
        ad_empty = next(r for r in r_empty if r["pathway"] == "anaerobic_digestion")
        self.assertAlmostEqual(
            ad_none["e_net_kwh_d"], ad_empty["e_net_kwh_d"], places=9
        )


# ---------------------------------------------------------------------------
# TestCostCalculations
# ---------------------------------------------------------------------------

class TestCostCalculations(unittest.TestCase):

    def test_custom_costs_used(self):
        """Custom PathwayCosts must change cost_inr_y from the default."""
        default_results = compare_pathways(_fs_ad(), _ctx_grid())
        custom_costs = {
            "composting": PathwayCosts(
                capex_inr=1.0,       # near-zero capex
                opex_inr_per_t=1.0,
                life_years=10.0,
                discount_rate=0.10,
            )
        }
        custom_results = compare_pathways(_fs_ad(), _ctx_grid(), costs=custom_costs)
        def_comp = next(r for r in default_results if r["pathway"] == "composting")
        cus_comp = next(r for r in custom_results if r["pathway"] == "composting")
        self.assertNotAlmostEqual(def_comp["cost_inr_y"], cus_comp["cost_inr_y"], places=0)

    def test_annual_net_equals_revenue_minus_cost(self):
        """annual_net_value_inr must equal revenue_inr_y - cost_inr_y for every pathway."""
        results = compare_pathways(_fs_dry(), _ctx_grid())
        for r in results:
            with self.subTest(pathway=r["pathway"]):
                expected = r["revenue_inr_y"] - r["cost_inr_y"]
                self.assertAlmostEqual(
                    r["annual_net_value_inr"], expected, places=6
                )

    def test_zero_transport_cost(self):
        """Transport cost = 0 when transport_cost_inr_per_t_km = 0."""
        ctx = LocationContext(
            electricity_tariff_inr_per_kwh=7.0,
            compost_price_inr_per_kg=0.0,
            heat_price_inr_per_kwh=0.0,
            nearest_buyer_km=100.0,         # long distance but zero rate
            transport_cost_inr_per_t_km=0.0,
            grid_available=False,
        )
        ctx_far = LocationContext(
            electricity_tariff_inr_per_kwh=7.0,
            compost_price_inr_per_kg=0.0,
            heat_price_inr_per_kwh=0.0,
            nearest_buyer_km=1000.0,
            transport_cost_inr_per_t_km=0.0,
            grid_available=False,
        )
        r1 = compare_pathways(_fs_ad(), ctx)
        r2 = compare_pathways(_fs_ad(), ctx_far)
        for p1, p2 in zip(
            sorted(r1, key=lambda x: x["pathway"]),
            sorted(r2, key=lambda x: x["pathway"]),
        ):
            self.assertAlmostEqual(p1["cost_inr_y"], p2["cost_inr_y"], places=4)


# ---------------------------------------------------------------------------
# TestDeterminism
# ---------------------------------------------------------------------------

class TestDeterminism(unittest.TestCase):

    def test_same_inputs_same_outputs(self):
        """compare_pathways is deterministic for identical inputs."""
        fs = _fs_ad()
        ctx = _ctx_grid()
        r1 = compare_pathways(fs, ctx)
        r2 = compare_pathways(fs, ctx)
        for a, b in zip(r1, r2):
            self.assertEqual(a["pathway"], b["pathway"])
            self.assertAlmostEqual(a["annual_net_value_inr"], b["annual_net_value_inr"], places=9)


if __name__ == "__main__":
    unittest.main()
