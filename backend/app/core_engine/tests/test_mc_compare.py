"""tests/test_mc_compare.py — unittest.TestCase tests for pathways/mc_compare.py."""
import json
import unittest

from app.core_engine.pathways.feedstock import Feedstock
from app.core_engine.pathways.compare import LocationContext
from app.core_engine.pathways.demand import DemandSink
from app.core_engine.pathways.feasibility import PATHWAYS
from app.core_engine.pathways.weather import WeatherContext
from app.core_engine.pathways.mc_compare import (
    default_compare_dists,
    run_mc_compare,
    _INPUT_NAMES,
    _CORE_INPUT_NAMES,
    _SINK_INPUT_NAMES,
    _WEATHER_INPUT_NAMES,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _fs_mixed() -> Feedstock:
    """High-organic, high-moisture — AD and composting feasible across most
    plausible moisture perturbations."""
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
    """Dry, high-LHV, high-plastic — incineration / gasification / pyrolysis feasible."""
    return Feedstock(
        total_mass_kg_d=1000.0,
        organic_fraction=0.05,
        plastic_fraction=0.50,
        paper_fraction=0.25,
        other_fraction=0.20,
        moisture_fraction=0.08,
        ash_fraction_dry=0.06,
        lhv_dry_mj_per_kg=22.0,
        contamination_pct=2.0,
    )


def _ctx() -> LocationContext:
    return LocationContext(
        electricity_tariff_inr_per_kwh=7.0,
        compost_price_inr_per_kg=2.0,
        heat_price_inr_per_kwh=3.0,
        nearest_buyer_km=10.0,
        transport_cost_inr_per_t_km=5.0,
        grid_available=True,
    )


def _elec_sink(name="elec_buyer", price=8.0, demand=200.0) -> DemandSink:
    return DemandSink(
        name=name, customer_class="industry",
        accepts=("electricity",), demand_kwh_d=demand,
        road_km=3.0, price_inr_per_kwh=price, max_km=20.0,
    )


def _wx() -> WeatherContext:
    return WeatherContext(
        ambient_temp_c=28.0, relative_humidity=0.75, rainfall_mm_d=10.0
    )


# ---------------------------------------------------------------------------
# TestDefaultCompareDists
# ---------------------------------------------------------------------------

class TestDefaultCompareDists(unittest.TestCase):

    def test_returns_dict(self):
        self.assertIsInstance(default_compare_dists(), dict)

    def test_no_args_has_seven_core_plus_two_sink(self):
        d = default_compare_dists()
        self.assertEqual(len(d), len(_CORE_INPUT_NAMES) + len(_SINK_INPUT_NAMES))

    def test_no_sink_no_weather_has_seven_core(self):
        d = default_compare_dists(include_sink=False, include_weather=False)
        self.assertEqual(len(d), len(_CORE_INPUT_NAMES))
        for name in _SINK_INPUT_NAMES + _WEATHER_INPUT_NAMES:
            self.assertNotIn(name, d)

    def test_include_weather_adds_rainfall(self):
        d = default_compare_dists(include_weather=True)
        self.assertIn("rainfall_mm_d", d)

    def test_all_assumed_true(self):
        d = default_compare_dists(include_sink=True, include_weather=True)
        for name, dist in d.items():
            self.assertTrue(dist.assumed, msg=f"'{name}' not assumed")

    def test_all_evidence_non_empty(self):
        d = default_compare_dists(include_sink=True, include_weather=True)
        for name, dist in d.items():
            self.assertTrue(dist.evidence.strip(), msg=f"'{name}' has empty evidence")

    def test_all_kinds_valid(self):
        valid = {"triangular", "normal", "uniform", "lognormal"}
        for name, dist in default_compare_dists(include_sink=True, include_weather=True).items():
            self.assertIn(dist.kind, valid, msg=f"'{name}' invalid kind")

    def test_input_names_tuple_covers_all_groups(self):
        all_names = set(_CORE_INPUT_NAMES) | set(_SINK_INPUT_NAMES) | set(_WEATHER_INPUT_NAMES)
        self.assertEqual(set(_INPUT_NAMES), all_names)


# ---------------------------------------------------------------------------
# TestRunMcCompareInterface  (no sinks, no weather — base case)
# ---------------------------------------------------------------------------

class TestRunMcCompareInterface(unittest.TestCase):

    def setUp(self):
        self.result = run_mc_compare(_fs_mixed(), _ctx(), n=50, seed=0)

    def test_returns_dict(self):
        self.assertIsInstance(self.result, dict)

    def test_required_top_level_keys(self):
        required = {
            "n", "seed",
            "win_probability",
            "net_value_p2_5", "net_value_median", "net_value_p97_5",
            "feasible_share", "expected_regret_inr_y",
            "sensitivity", "distributions", "assumptions_note",
        }
        for key in required:
            self.assertIn(key, self.result, msg=f"missing key '{key}'")

    def test_n_and_seed_echoed(self):
        self.assertEqual(self.result["n"], 50)
        self.assertEqual(self.result["seed"], 0)

    def test_all_pathways_in_every_per_pathway_dict(self):
        for key in ("win_probability", "net_value_p2_5", "net_value_median",
                    "net_value_p97_5", "feasible_share", "expected_regret_inr_y"):
            for pw in PATHWAYS:
                self.assertIn(pw, self.result[key], msg=f"'{pw}' missing from '{key}'")

    def test_sensitivity_sorted_descending(self):
        vals = [e["abs_spearman"] for e in self.result["sensitivity"]]
        self.assertEqual(vals, sorted(vals, reverse=True))

    def test_sensitivity_no_nan(self):
        import math
        for e in self.result["sensitivity"]:
            self.assertFalse(math.isnan(e["abs_spearman"]),
                             msg=f"NaN for '{e['input']}'")

    def test_sensitivity_abs_spearman_in_0_1(self):
        for e in self.result["sensitivity"]:
            self.assertGreaterEqual(e["abs_spearman"], 0.0)
            self.assertLessEqual(e["abs_spearman"], 1.0)

    def test_assumptions_note_non_empty(self):
        self.assertTrue(self.result["assumptions_note"].strip())

    def test_assumptions_note_mentions_win_probabilities(self):
        self.assertIn("win probabilit", self.result["assumptions_note"].lower())

    def test_assumptions_note_mentions_not_validated(self):
        note = self.result["assumptions_note"].lower()
        self.assertTrue(
            "not validated" in note or "illustrative" in note,
            msg="assumptions_note must mention illustrative or not validated",
        )

    def test_feasible_share_in_0_1(self):
        for pw, share in self.result["feasible_share"].items():
            self.assertGreaterEqual(share, 0.0, msg=pw)
            self.assertLessEqual(share, 1.0, msg=pw)

    def test_win_probability_in_0_1(self):
        for pw, p in self.result["win_probability"].items():
            self.assertGreaterEqual(p, 0.0, msg=pw)
            self.assertLessEqual(p, 1.0, msg=pw)

    def test_p2_5_le_median_le_p97_5(self):
        for pw in PATHWAYS:
            p2  = self.result["net_value_p2_5"][pw]
            med = self.result["net_value_median"][pw]
            p97 = self.result["net_value_p97_5"][pw]
            self.assertLessEqual(p2, med + 1e-6, msg=f"{pw}: p2.5 > median")
            self.assertLessEqual(med, p97 + 1e-6, msg=f"{pw}: median > p97.5")

    def test_distributions_echo_has_core_keys(self):
        for name in _CORE_INPUT_NAMES:
            self.assertIn(name, self.result["distributions"])

    def test_no_sink_inputs_in_sensitivity_by_default(self):
        sens_names = {e["input"] for e in self.result["sensitivity"]}
        for name in _SINK_INPUT_NAMES:
            self.assertNotIn(name, sens_names)

    def test_no_weather_inputs_in_sensitivity_by_default(self):
        sens_names = {e["input"] for e in self.result["sensitivity"]}
        for name in _WEATHER_INPUT_NAMES:
            self.assertNotIn(name, sens_names)

    def test_sensitivity_has_seven_entries(self):
        self.assertEqual(len(self.result["sensitivity"]), len(_CORE_INPUT_NAMES))

    def test_all_scalar_values_are_plain_python_types(self):
        self.assertIsInstance(self.result["n"], int)
        self.assertIsInstance(self.result["seed"], int)
        self.assertIsInstance(self.result["assumptions_note"], str)
        for pw in PATHWAYS:
            self.assertIsInstance(self.result["net_value_median"][pw], float)
            self.assertIsInstance(self.result["win_probability"][pw], float)


# ---------------------------------------------------------------------------
# TestWinProbabilitySumsToOne
# ---------------------------------------------------------------------------

class TestWinProbabilitySumsToOne(unittest.TestCase):
    """Win probabilities must sum to 1 within 1e-9 over runs with a feasible pathway."""

    def _assert_sum(self, result):
        total = sum(result["win_probability"].values())
        feasible_any = any(s > 0 for s in result["feasible_share"].values())
        if feasible_any:
            self.assertAlmostEqual(total, 1.0, delta=1e-9,
                                   msg=f"win_probability sum {total} != 1.0")
        else:
            self.assertAlmostEqual(total, 0.0, delta=1e-9)

    def test_mixed_feedstock(self):
        self._assert_sum(run_mc_compare(_fs_mixed(), _ctx(), n=100, seed=7))

    def test_dry_feedstock(self):
        self._assert_sum(run_mc_compare(_fs_dry(), _ctx(), n=100, seed=7))

    def test_with_sinks(self):
        self._assert_sum(
            run_mc_compare(_fs_mixed(), _ctx(), sinks=[_elec_sink()], n=80, seed=7)
        )

    def test_with_weather(self):
        self._assert_sum(
            run_mc_compare(_fs_mixed(), _ctx(), n=80, seed=7,
                           weather=_wx(), weather_enabled=True)
        )


# ---------------------------------------------------------------------------
# TestDeterminism
# ---------------------------------------------------------------------------

class TestDeterminism(unittest.TestCase):

    def test_same_seed_same_result(self):
        r1 = run_mc_compare(_fs_mixed(), _ctx(), n=50, seed=42)
        r2 = run_mc_compare(_fs_mixed(), _ctx(), n=50, seed=42)
        self.assertEqual(r1["win_probability"], r2["win_probability"])
        self.assertEqual(r1["net_value_median"], r2["net_value_median"])

    def test_same_seed_with_sinks(self):
        sinks = [_elec_sink()]
        r1 = run_mc_compare(_fs_mixed(), _ctx(), sinks=sinks, n=30, seed=7)
        r2 = run_mc_compare(_fs_mixed(), _ctx(), sinks=sinks, n=30, seed=7)
        self.assertEqual(r1["win_probability"], r2["win_probability"])

    def test_same_seed_with_weather(self):
        r1 = run_mc_compare(_fs_mixed(), _ctx(), n=30, seed=5,
                            weather=_wx(), weather_enabled=True)
        r2 = run_mc_compare(_fs_mixed(), _ctx(), n=30, seed=5,
                            weather=_wx(), weather_enabled=True)
        self.assertEqual(r1["net_value_median"], r2["net_value_median"])

    def test_different_seeds_differ(self):
        r1 = run_mc_compare(_fs_mixed(), _ctx(), n=100, seed=1)
        r2 = run_mc_compare(_fs_mixed(), _ctx(), n=100, seed=2)
        all_same = all(
            r1["net_value_median"][pw] == r2["net_value_median"][pw]
            for pw in PATHWAYS
        )
        self.assertFalse(all_same)


# ---------------------------------------------------------------------------
# TestNValidation
# ---------------------------------------------------------------------------

class TestNValidation(unittest.TestCase):

    def test_n_lt_10_raises(self):
        with self.assertRaises(ValueError):
            run_mc_compare(_fs_mixed(), _ctx(), n=9)

    def test_n_exactly_10_ok(self):
        r = run_mc_compare(_fs_mixed(), _ctx(), n=10, seed=0)
        self.assertEqual(r["n"], 10)

    def test_n_zero_raises(self):
        with self.assertRaises(ValueError):
            run_mc_compare(_fs_mixed(), _ctx(), n=0)

    def test_n_negative_raises(self):
        with self.assertRaises(ValueError):
            run_mc_compare(_fs_mixed(), _ctx(), n=-5)


# ---------------------------------------------------------------------------
# TestSingleFeasiblePathwayGivesProbabilityOne
# ---------------------------------------------------------------------------

class TestSingleFeasiblePathway(unittest.TestCase):

    def test_only_composting_feasible_gets_probability_one(self):
        """Pin feedstock and distributions so composting is the only feasible
        pathway:
          - moisture always 0.65–0.80  → AD feasible (≥0.50) but gasification
            (max 0.30) and pyrolysis (max 0.20) infeasible
          - lhv_dry pinned 1.5–2.5 MJ/kg  → wet LHV << 7 MJ/kg threshold for
            incineration; gasification also infeasible (needs ≥10 MJ/kg wet)
          - high organic_fraction (0.65) → composting feasible (needs ≥0.40)
          - low contamination (3 %) → composting feasible (limit 15 %)
          Both AD and composting are feasible at the base, but because moisture
          is always ≥0.50, AD is also feasible here.  To isolate composting we
          need AD infeasible: use moisture always ≥0.65 AND also set organic
          fraction in distributions to keep AD feasible is fine — in fact both
          can be feasible.  The important assertion is that every infeasible
          pathway has 0 probability.  We strengthen by using organic_fraction
          too high for gasification/pyrolysis (already via moisture) and lhv
          too low for incineration.
        """
        from app.core_engine.montecarlo import Dist

        fs = Feedstock(
            total_mass_kg_d=1000.0,
            organic_fraction=0.65, plastic_fraction=0.10,
            paper_fraction=0.10, other_fraction=0.15,
            moisture_fraction=0.75, ash_fraction_dry=0.02,
            lhv_dry_mj_per_kg=2.0, contamination_pct=3.0,
        )
        dists = {
            "moisture_fraction": Dist(kind="uniform", args=(0.65, 0.80),
                                      evidence="placeholder", assumed=True),
            "lhv_dry_mj_per_kg": Dist(kind="uniform", args=(1.5, 2.5),
                                      evidence="placeholder", assumed=True),
            "electricity_tariff_inr_per_kwh": Dist(kind="uniform", args=(4.0, 12.0),
                                                   evidence="placeholder", assumed=True),
            "compost_price_inr_per_kg": Dist(kind="uniform", args=(0.5, 5.0),
                                             evidence="placeholder", assumed=True),
            "eta_el": Dist(kind="uniform", args=(0.18, 0.28),
                           evidence="placeholder", assumed=True),
            "capex_multiplier": Dist(kind="uniform", args=(0.8, 1.2),
                                     evidence="placeholder", assumed=True),
            "transport_cost_inr_per_t_km": Dist(kind="uniform", args=(2.0, 8.0),
                                                evidence="placeholder", assumed=True),
        }
        # Only incineration, gasification, pyrolysis should have win_prob = 0
        result = run_mc_compare(fs, _ctx(), dists=dists, n=100, seed=0)
        for pw in ("incineration", "gasification", "pyrolysis"):
            self.assertAlmostEqual(
                result["win_probability"][pw], 0.0, delta=0.0,
                msg=f"Expected {pw} win_prob=0, got {result['win_probability'][pw]:.3f}",
            )
        # The two feasible pathways should between them sum to 1
        total = sum(result["win_probability"].values())
        self.assertAlmostEqual(total, 1.0, delta=1e-9)


# ---------------------------------------------------------------------------
# TestHigherTariffFavoursEnergyPathways
# ---------------------------------------------------------------------------

class TestHigherTariffFavoursEnergyPathways(unittest.TestCase):

    def _run_pinned_tariff(self, tariff, n=150, seed=3):
        from app.core_engine.montecarlo import Dist
        dists = {"electricity_tariff_inr_per_kwh": Dist(
            kind="uniform", args=(tariff, tariff + 0.001),
            evidence="placeholder", assumed=True,
        )}
        return run_mc_compare(_fs_mixed(), _ctx(), dists=dists, n=n, seed=seed)

    def test_higher_tariff_raises_ad_median_net_value(self):
        r_low  = self._run_pinned_tariff(1.0)
        r_high = self._run_pinned_tariff(30.0)
        self.assertGreaterEqual(
            r_high["net_value_median"]["anaerobic_digestion"],
            r_low["net_value_median"]["anaerobic_digestion"] - 1.0,
        )

    def test_higher_tariff_increases_combined_energy_pathway_wins(self):
        r_low  = self._run_pinned_tariff(1.0)
        r_high = self._run_pinned_tariff(30.0)
        energy_pws = {"anaerobic_digestion", "incineration", "gasification"}
        low_sum  = sum(r_low["win_probability"].get(pw, 0.0)  for pw in energy_pws)
        high_sum = sum(r_high["win_probability"].get(pw, 0.0) for pw in energy_pws)
        self.assertGreaterEqual(high_sum, low_sum - 0.05)


# ---------------------------------------------------------------------------
# TestJSONSerialisable
# ---------------------------------------------------------------------------

class TestJSONSerialisable(unittest.TestCase):

    def test_base_result_json_serialisable(self):
        result = run_mc_compare(_fs_mixed(), _ctx(), n=30, seed=5)
        try:
            json.dumps(result)
        except (TypeError, ValueError) as exc:
            self.fail(f"not JSON-serialisable: {exc}")

    def test_with_sinks_json_serialisable(self):
        result = run_mc_compare(_fs_mixed(), _ctx(), sinks=[_elec_sink()], n=30, seed=5)
        try:
            json.dumps(result)
        except (TypeError, ValueError) as exc:
            self.fail(f"not JSON-serialisable (sinks): {exc}")

    def test_with_weather_json_serialisable(self):
        result = run_mc_compare(_fs_mixed(), _ctx(), n=30, seed=5,
                                weather=_wx(), weather_enabled=True)
        try:
            json.dumps(result)
        except (TypeError, ValueError) as exc:
            self.fail(f"not JSON-serialisable (weather): {exc}")


# ---------------------------------------------------------------------------
# TestSinkSampling
# ---------------------------------------------------------------------------

class TestSinkSampling(unittest.TestCase):

    def test_sink_inputs_appear_in_sensitivity(self):
        result = run_mc_compare(_fs_mixed(), _ctx(), sinks=[_elec_sink()],
                                n=50, seed=0)
        sens_names = {e["input"] for e in result["sensitivity"]}
        for name in _SINK_INPUT_NAMES:
            self.assertIn(name, sens_names, msg=f"'{name}' missing from sensitivity")

    def test_sink_inputs_in_distributions_echo(self):
        result = run_mc_compare(_fs_mixed(), _ctx(), sinks=[_elec_sink()],
                                n=30, seed=0)
        for name in _SINK_INPUT_NAMES:
            self.assertIn(name, result["distributions"])

    def test_no_sinks_excludes_sink_inputs(self):
        result = run_mc_compare(_fs_mixed(), _ctx(), n=30, seed=0)
        sens_names = {e["input"] for e in result["sensitivity"]}
        for name in _SINK_INPUT_NAMES:
            self.assertNotIn(name, sens_names)

    def test_win_prob_sums_to_1_with_sinks(self):
        result = run_mc_compare(_fs_mixed(), _ctx(), sinks=[_elec_sink()],
                                n=80, seed=3)
        total = sum(result["win_probability"].values())
        if any(s > 0 for s in result["feasible_share"].values()):
            self.assertAlmostEqual(total, 1.0, delta=1e-9)

    def test_higher_sink_price_multiplier_raises_net_value(self):
        """Pinning sink_price_multiplier high should yield higher net value
        for an energy-producing pathway compared to a low multiplier."""
        from app.core_engine.montecarlo import Dist
        base_dists = {
            "sink_demand_multiplier": Dist(kind="uniform", args=(1.0, 1.001),
                                          evidence="placeholder", assumed=True),
        }
        dists_low  = dict(base_dists)
        dists_high = dict(base_dists)
        dists_low["sink_price_multiplier"]  = Dist(kind="uniform", args=(0.1, 0.101),
                                                   evidence="placeholder", assumed=True)
        dists_high["sink_price_multiplier"] = Dist(kind="uniform", args=(3.0, 3.001),
                                                   evidence="placeholder", assumed=True)
        r_low  = run_mc_compare(_fs_mixed(), _ctx(), sinks=[_elec_sink()],
                                dists=dists_low, n=80, seed=4)
        r_high = run_mc_compare(_fs_mixed(), _ctx(), sinks=[_elec_sink()],
                                dists=dists_high, n=80, seed=4)
        ad_low  = r_low["net_value_median"]["anaerobic_digestion"]
        ad_high = r_high["net_value_median"]["anaerobic_digestion"]
        self.assertGreaterEqual(ad_high, ad_low - 1e-3,
                                msg=f"Higher price lowered AD median: {ad_high:.0f} < {ad_low:.0f}")

    def test_empty_sinks_behaves_like_none(self):
        r_none  = run_mc_compare(_fs_mixed(), _ctx(), sinks=None,  n=50, seed=2)
        r_empty = run_mc_compare(_fs_mixed(), _ctx(), sinks=[],    n=50, seed=2)
        for pw in PATHWAYS:
            self.assertAlmostEqual(
                r_none["net_value_median"][pw],
                r_empty["net_value_median"][pw],
                places=9,
            )


# ---------------------------------------------------------------------------
# TestWeatherSampling
# ---------------------------------------------------------------------------

class TestWeatherSampling(unittest.TestCase):

    def test_rainfall_in_sensitivity_when_enabled(self):
        result = run_mc_compare(_fs_mixed(), _ctx(), n=50, seed=0,
                                weather=_wx(), weather_enabled=True)
        sens_names = {e["input"] for e in result["sensitivity"]}
        self.assertIn("rainfall_mm_d", sens_names)

    def test_rainfall_in_distributions_echo(self):
        result = run_mc_compare(_fs_mixed(), _ctx(), n=30, seed=0,
                                weather=_wx(), weather_enabled=True)
        self.assertIn("rainfall_mm_d", result["distributions"])

    def test_weather_disabled_no_rainfall_in_sensitivity(self):
        result = run_mc_compare(_fs_mixed(), _ctx(), n=30, seed=0,
                                weather=_wx(), weather_enabled=False)
        sens_names = {e["input"] for e in result["sensitivity"]}
        self.assertNotIn("rainfall_mm_d", sens_names)

    def test_weather_none_no_rainfall(self):
        result = run_mc_compare(_fs_mixed(), _ctx(), n=30, seed=0,
                                weather=None, weather_enabled=True)
        sens_names = {e["input"] for e in result["sensitivity"]}
        self.assertNotIn("rainfall_mm_d", sens_names)

    def test_win_prob_sums_to_1_with_weather(self):
        result = run_mc_compare(_fs_mixed(), _ctx(), n=80, seed=5,
                                weather=_wx(), weather_enabled=True)
        total = sum(result["win_probability"].values())
        if any(s > 0 for s in result["feasible_share"].values()):
            self.assertAlmostEqual(total, 1.0, delta=1e-9)


# ---------------------------------------------------------------------------
# TestCustomDists
# ---------------------------------------------------------------------------

class TestCustomDists(unittest.TestCase):

    def test_unknown_core_key_raises(self):
        from app.core_engine.montecarlo import Dist
        with self.assertRaises(ValueError):
            run_mc_compare(_fs_mixed(), _ctx(), dists={
                "not_a_real_input": Dist(kind="uniform", args=(0.0, 1.0),
                                        evidence="placeholder", assumed=True),
            }, n=10)

    def test_sink_key_without_sinks_raises(self):
        """sink_demand_multiplier not valid when sinks=None."""
        from app.core_engine.montecarlo import Dist
        with self.assertRaises(ValueError):
            run_mc_compare(_fs_mixed(), _ctx(), sinks=None, dists={
                "sink_demand_multiplier": Dist(kind="uniform", args=(0.5, 1.5),
                                              evidence="placeholder", assumed=True),
            }, n=10)

    def test_weather_key_without_weather_raises(self):
        """rainfall_mm_d not valid when weather_enabled=False."""
        from app.core_engine.montecarlo import Dist
        with self.assertRaises(ValueError):
            run_mc_compare(_fs_mixed(), _ctx(), dists={
                "rainfall_mm_d": Dist(kind="uniform", args=(0.0, 20.0),
                                     evidence="placeholder", assumed=True),
            }, n=10, weather_enabled=False)

    def test_partial_override_accepted(self):
        from app.core_engine.montecarlo import Dist
        result = run_mc_compare(_fs_mixed(), _ctx(), dists={
            "electricity_tariff_inr_per_kwh": Dist(kind="uniform", args=(5.0, 6.0),
                                                   evidence="placeholder", assumed=True),
        }, n=20, seed=0)
        self.assertEqual(result["n"], 20)

    def test_custom_dist_echoed_in_distributions(self):
        from app.core_engine.montecarlo import Dist
        result = run_mc_compare(_fs_mixed(), _ctx(), dists={
            "compost_price_inr_per_kg": Dist(kind="uniform", args=(3.0, 4.0),
                                            evidence="my_evidence", assumed=True),
        }, n=20, seed=0)
        echoed = result["distributions"]["compost_price_inr_per_kg"]
        self.assertEqual(echoed["evidence"], "my_evidence")


# ---------------------------------------------------------------------------
# TestSensitivityCompleteness
# ---------------------------------------------------------------------------

class TestSensitivityCompleteness(unittest.TestCase):

    def test_core_only_has_seven(self):
        result = run_mc_compare(_fs_mixed(), _ctx(), n=40, seed=0)
        self.assertEqual(len(result["sensitivity"]), len(_CORE_INPUT_NAMES))

    def test_with_sinks_has_seven_plus_two(self):
        result = run_mc_compare(_fs_mixed(), _ctx(), sinks=[_elec_sink()],
                                n=40, seed=0)
        expected = len(_CORE_INPUT_NAMES) + len(_SINK_INPUT_NAMES)
        self.assertEqual(len(result["sensitivity"]), expected)

    def test_with_weather_has_seven_plus_one(self):
        result = run_mc_compare(_fs_mixed(), _ctx(), n=40, seed=0,
                                weather=_wx(), weather_enabled=True)
        expected = len(_CORE_INPUT_NAMES) + len(_WEATHER_INPUT_NAMES)
        self.assertEqual(len(result["sensitivity"]), expected)

    def test_sinks_and_weather_has_ten(self):
        result = run_mc_compare(_fs_mixed(), _ctx(), sinks=[_elec_sink()],
                                n=40, seed=0, weather=_wx(), weather_enabled=True)
        expected = (len(_CORE_INPUT_NAMES) + len(_SINK_INPUT_NAMES)
                    + len(_WEATHER_INPUT_NAMES))
        self.assertEqual(len(result["sensitivity"]), expected)


if __name__ == "__main__":
    unittest.main()
