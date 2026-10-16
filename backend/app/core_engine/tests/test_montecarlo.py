"""
Tests for backend/app/core_engine/montecarlo.py

Coverage:
  - Dist: valid construction (all 4 kinds), invalid raises, frozen.
  - default_dists: 9 entries, all assumed, valid Params field names, evidence non-empty.
  - run_mc: determinism (same seed), sensitivity, percentile ordering,
    narrow-interval case, default run median range and p_net_nonpositive,
    top sensitivity is y_biogas_nm3_per_kg_vs, error cases (n<10, empty dists,
    unknown name), assumptions_note present, json.dumps works.
"""

import json
import math
import unittest

from app.core_engine.montecarlo import Dist, default_dists, run_mc
from app.core_engine.params import Params


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _narrow_dists():
    """One distribution per varying input, all very tight, for narrow-interval test."""
    return {
        "y_biogas_nm3_per_kg_vs": Dist(
            kind="uniform", args=(0.5499, 0.5501),
            evidence="test", assumed=False,
        ),
    }


# ===========================================================================
# Dist
# ===========================================================================

class TestDist(unittest.TestCase):

    # -- valid construction --------------------------------------------------

    def test_triangular_valid(self):
        d = Dist(kind="triangular", args=(0.2, 0.5, 0.8),
                 evidence="test", assumed=True)
        self.assertEqual(d.kind, "triangular")

    def test_normal_valid(self):
        d = Dist(kind="normal", args=(0.60, 0.03),
                 evidence="test", assumed=True, clip=(0.50, 0.70))
        self.assertEqual(d.clip, (0.50, 0.70))

    def test_uniform_valid(self):
        d = Dist(kind="uniform", args=(0.005, 0.03),
                 evidence="test", assumed=False)
        self.assertEqual(d.assumed, False)

    def test_lognormal_valid(self):
        d = Dist(kind="lognormal", args=(math.log(0.15), 0.3),
                 evidence="test", assumed=True)
        self.assertEqual(d.kind, "lognormal")

    def test_frozen(self):
        d = Dist(kind="uniform", args=(0.1, 0.2), evidence="e", assumed=False)
        with self.assertRaises(Exception):
            d.kind = "normal"  # type: ignore[misc]

    # -- invalid kind --------------------------------------------------------

    def test_invalid_kind_raises(self):
        with self.assertRaises(ValueError, msg="should reject unknown kind"):
            Dist(kind="beta", args=(2, 5), evidence="e", assumed=True)

    # -- empty evidence raises -----------------------------------------------

    def test_empty_evidence_raises(self):
        with self.assertRaises(ValueError):
            Dist(kind="uniform", args=(0.1, 0.2), evidence="", assumed=True)

    def test_whitespace_evidence_raises(self):
        with self.assertRaises(ValueError):
            Dist(kind="uniform", args=(0.1, 0.2), evidence="   ", assumed=True)

    # -- triangular validation -----------------------------------------------

    def test_triangular_mode_above_high_raises(self):
        with self.assertRaises(ValueError):
            Dist(kind="triangular", args=(0.1, 0.9, 0.5), evidence="e", assumed=True)

    def test_triangular_low_equals_high_raises(self):
        with self.assertRaises(ValueError):
            Dist(kind="triangular", args=(0.5, 0.5, 0.5), evidence="e", assumed=True)

    def test_triangular_mode_equals_low_is_ok(self):
        # low == mode is allowed
        d = Dist(kind="triangular", args=(0.3, 0.3, 0.8), evidence="e", assumed=True)
        self.assertEqual(d.args[0], 0.3)

    # -- normal validation ---------------------------------------------------

    def test_normal_sigma_zero_raises(self):
        with self.assertRaises(ValueError):
            Dist(kind="normal", args=(0.6, 0.0), evidence="e", assumed=True)

    def test_normal_sigma_negative_raises(self):
        with self.assertRaises(ValueError):
            Dist(kind="normal", args=(0.6, -1.0), evidence="e", assumed=True)

    # -- uniform validation --------------------------------------------------

    def test_uniform_low_equals_high_raises(self):
        with self.assertRaises(ValueError):
            Dist(kind="uniform", args=(0.5, 0.5), evidence="e", assumed=True)

    def test_uniform_low_greater_than_high_raises(self):
        with self.assertRaises(ValueError):
            Dist(kind="uniform", args=(0.8, 0.2), evidence="e", assumed=True)

    # -- lognormal validation ------------------------------------------------

    def test_lognormal_sigma_zero_raises(self):
        with self.assertRaises(ValueError):
            Dist(kind="lognormal", args=(math.log(0.15), 0.0), evidence="e", assumed=True)


# ===========================================================================
# default_dists
# ===========================================================================

class TestDefaultDists(unittest.TestCase):

    def setUp(self):
        import dataclasses
        self.dd = default_dists()
        self.valid_fields = frozenset(
            f.name for f in dataclasses.fields(Params)
        )

    def test_nine_entries(self):
        self.assertEqual(len(self.dd), 9)

    def test_all_assumed(self):
        for name, d in self.dd.items():
            self.assertTrue(d.assumed, f"{name} should be assumed=True")

    def test_evidence_non_empty(self):
        for name, d in self.dd.items():
            self.assertTrue(d.evidence.strip(), f"{name} evidence is empty")

    def test_all_keys_are_valid_params_fields(self):
        for name in self.dd:
            self.assertIn(name, self.valid_fields, f"'{name}' is not a Params field")

    def test_expected_keys_present(self):
        expected = {
            "y_biogas_nm3_per_kg_vs", "ts_fraction", "suitable_fraction",
            "eta_el", "ch4_fraction", "availability", "vs_of_ts",
            "aux_mix_kwh_m3_d", "ch4_slip",
        }
        self.assertEqual(set(self.dd.keys()), expected)

    def test_ch4_fraction_has_clip(self):
        d = self.dd["ch4_fraction"]
        self.assertIsNotNone(d.clip)
        self.assertAlmostEqual(d.clip[0], 0.50)
        self.assertAlmostEqual(d.clip[1], 0.70)

    def test_lognormal_mu_is_log_015(self):
        d = self.dd["aux_mix_kwh_m3_d"]
        self.assertEqual(d.kind, "lognormal")
        self.assertAlmostEqual(d.args[0], math.log(0.15), places=9)


# ===========================================================================
# run_mc
# ===========================================================================

class TestRunMc(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        """Run once — the default n=1500 run used by several tests."""
        cls.result = run_mc(Params(), n=1500, seed=42)

    # -- determinism ---------------------------------------------------------

    def test_same_seed_same_result(self):
        r1 = run_mc(Params(), n=200, seed=7)
        r2 = run_mc(Params(), n=200, seed=7)
        self.assertEqual(r1["median"], r2["median"])
        self.assertEqual(r1["p2_5"],   r2["p2_5"])
        self.assertEqual(r1["p97_5"],  r2["p97_5"])

    def test_different_seed_different_result(self):
        r1 = run_mc(Params(), n=200, seed=1)
        r2 = run_mc(Params(), n=200, seed=2)
        self.assertNotEqual(r1["median"], r2["median"])

    # -- percentile ordering -------------------------------------------------

    def test_p2_5_le_median_le_p97_5(self):
        r = self.result
        self.assertLessEqual(r["p2_5"], r["median"])
        self.assertLessEqual(r["median"], r["p97_5"])

    # -- default run plausibility --------------------------------------------

    def test_median_in_expected_range(self):
        self.assertGreater(self.result["median"], 65.0)
        self.assertLess(self.result["median"], 85.0)

    def test_p_net_nonpositive_is_zero_for_default(self):
        self.assertEqual(self.result["p_net_nonpositive"], 0.0)

    # -- sensitivity ---------------------------------------------------------

    def test_top_sensitivity_is_y_biogas(self):
        top = self.result["sensitivity"][0]["input"]
        self.assertEqual(top, "y_biogas_nm3_per_kg_vs",
                         msg=f"Expected y_biogas_nm3_per_kg_vs on top, got {top}")

    def test_sensitivity_sorted_descending(self):
        s = self.result["sensitivity"]
        for i in range(len(s) - 1):
            self.assertGreaterEqual(s[i]["abs_spearman"], s[i + 1]["abs_spearman"])

    def test_sensitivity_values_in_0_1(self):
        for item in self.result["sensitivity"]:
            self.assertGreaterEqual(item["abs_spearman"], 0.0)
            self.assertLessEqual(item["abs_spearman"], 1.0)

    def test_sensitivity_no_nan(self):
        for item in self.result["sensitivity"]:
            self.assertFalse(math.isnan(item["abs_spearman"]),
                             msg=f"NaN abs_spearman for {item['input']}")

    # -- constant column gives 0.0 spearman ----------------------------------

    def test_constant_column_spearman_zero(self):
        """A distribution with near-zero width should give abs_spearman ~ 0 or valid float."""
        r = run_mc(Params(), dists=_narrow_dists(), n=50, seed=0)
        item = r["sensitivity"][0]
        self.assertFalse(math.isnan(item["abs_spearman"]))
        self.assertIsInstance(item["abs_spearman"], float)

    # -- narrow interval test ------------------------------------------------

    def test_narrow_dists_give_tight_interval(self):
        r = run_mc(Params(), dists=_narrow_dists(), n=100, seed=0)
        width = r["p97_5"] - r["p2_5"]
        # With y_biogas pinned to ~0.55, the interval should be very narrow
        self.assertLess(width, 5.0, msg=f"Expected narrow interval, got width={width:.3f}")

    # -- required output keys ------------------------------------------------

    def test_all_required_keys_present(self):
        required = {"n", "seed", "median", "p2_5", "p97_5",
                    "p_net_nonpositive", "runs_with_warnings",
                    "sensitivity", "distributions", "assumptions_note"}
        for key in required:
            self.assertIn(key, self.result, msg=f"Missing key: {key}")

    def test_n_and_seed_echoed(self):
        r = run_mc(Params(), n=100, seed=99)
        self.assertEqual(r["n"], 100)
        self.assertEqual(r["seed"], 99)

    # -- distributions echoed correctly --------------------------------------

    def test_distributions_echo_kind(self):
        dd = default_dists()
        r = run_mc(Params(), dists=dd, n=50, seed=0)
        for name, d in dd.items():
            self.assertEqual(r["distributions"][name]["kind"], d.kind)

    def test_distributions_clip_echoed(self):
        dd = default_dists()
        r = run_mc(Params(), dists=dd, n=50, seed=0)
        dist_ch4 = r["distributions"]["ch4_fraction"]
        self.assertIsNotNone(dist_ch4["clip"])

    # -- assumptions_note ----------------------------------------------------

    def test_assumptions_note_present_when_assumed(self):
        note = self.result["assumptions_note"]
        self.assertTrue(note.strip(), "assumptions_note should not be empty when dists are assumed")
        self.assertIn("credible", note.lower())

    def test_assumptions_note_empty_when_none_assumed(self):
        r = run_mc(Params(), dists=_narrow_dists()  # assumed=False
                   , n=50, seed=0)
        self.assertEqual(r["assumptions_note"], "")

    # -- JSON serialisable ---------------------------------------------------

    def test_json_dumps_works(self):
        try:
            json.dumps(self.result)
        except (TypeError, ValueError) as e:
            self.fail(f"json.dumps raised: {e}")

    def test_all_numerics_are_plain_python_floats(self):
        import numpy as np
        for key in ("median", "p2_5", "p97_5", "p_net_nonpositive"):
            val = self.result[key]
            self.assertNotIsInstance(val, np.floating,
                                     msg=f"{key} is numpy float, not plain Python float")
            self.assertIsInstance(val, float)

    # -- error cases ---------------------------------------------------------

    def test_n_lt_10_raises(self):
        with self.assertRaises(ValueError, msg="n=5 should raise"):
            run_mc(Params(), n=5)

    def test_empty_dists_raises(self):
        with self.assertRaises(ValueError):
            run_mc(Params(), dists={})

    def test_unknown_field_name_raises(self):
        bad_dists = {"not_a_real_field": Dist(
            kind="uniform", args=(0.1, 0.2), evidence="e", assumed=True
        )}
        with self.assertRaises(ValueError, msg="should reject unknown field name"):
            run_mc(Params(), dists=bad_dists)


if __name__ == "__main__":
    unittest.main(verbosity=2)
