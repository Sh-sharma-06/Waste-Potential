"""Tests for validation.py.

All rows used below are TEST FIXTURES — synthetic data crafted to exercise
specific code paths.  They are NOT real measurements and carry no scientific
meaning.  Each fixture is labelled clearly.

Hand-computed metrics reference (obs=[10,20,30], pred=[12,18,33]):
    errors          = [2, 2, 3]
    sq_errors       = [4, 4, 9]
    biases          = [2, -2, 3]
    n               = 3
    mae             = (2 + 2 + 3) / 3               = 7/3   ≈ 2.333...
    rmse            = sqrt((4 + 4 + 9) / 3)          = sqrt(17/3) ≈ 2.380...
    bias            = (2 + (-2) + 3) / 3             = 1.0
    mape terms      = |2/10|*100, |(-2)/20|*100, |3/30|*100
                    = 20.0, 10.0, 10.0
    mape            = (20 + 10 + 10) / 3             = 40/3  ≈ 13.333...
    n_skipped       = 0 (no zeros in obs)
"""
from __future__ import annotations

import csv
import json
import math
import tempfile
import unittest
from pathlib import Path
from typing import Any, Dict, List

from app.core_engine.validation import (
    COMPOSITION_TOLERANCE_DIGITISED,
    COMPOSITION_TOLERANCE_REPORTED,
    load_observations,
    metrics,
    report,
    validate_bmp,
    validate_mass_loss,
    validate_net_energy,
)


# ---------------------------------------------------------------------------
# Shared fixture helpers
# ---------------------------------------------------------------------------

def _write_csv(rows: List[Dict[str, str]], path: Path) -> None:
    """Write a list of dicts to *path* as CSV."""
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fieldnames = list(rows[0].keys())
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


# TEST FIXTURE — BMP rows marked real; carb+protein+lipid = 1.0
def _bmp_real_rows(n: int = 5, vs_kg: float = 1.0,
                   obs_fraction: float = 0.80) -> List[Dict[str, Any]]:
    """Returns n real BMP rows where observed CH4 = obs_fraction * Buswell ceiling."""
    # carb=0.6, protein=0.2, lipid=0.2 → Buswell = 0.6*0.415+0.2*0.496+0.2*1.014
    #                                             = 0.249 + 0.0992 + 0.2028 = 0.551
    ceiling_per_kg = 0.6 * 0.415 + 0.2 * 0.496 + 0.2 * 1.014  # 0.551
    obs_ch4 = ceiling_per_kg * vs_kg * obs_fraction
    return [
        {
            "source_type": "real",
            "study_id": f"study_{i}",
            "source": "test fixture",
            "feedstock": "mixed_organic",
            "vs_kg": str(vs_kg),
            "observed_ch4_nm3": str(obs_ch4),
            "carb": "0.6",
            "protein": "0.2",
            "lipid": "0.2",
        }
        for i in range(n)
    ]


# TEST FIXTURE — net-energy rows with default Params fields
def _net_energy_rows(n: int = 5, obs_kwh: float = 50.0) -> List[Dict[str, Any]]:
    return [
        {
            "source_type": "real",
            "study_id": f"plant_{i}",
            "source": "test fixture",
            "observed_net_kwh_d": str(obs_kwh),
        }
        for i in range(n)
    ]


# TEST FIXTURE — VS-destruction rows
def _vsd_rows(n: int = 5, obs_vsd: float = 0.40) -> List[Dict[str, Any]]:
    return [
        {
            "source_type": "real",
            "study_id": f"plant_{i}",
            "source": "test fixture",
            "observed_vs_destruction": str(obs_vsd),
        }
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# 1. metrics()
# ---------------------------------------------------------------------------

class TestMetrics(unittest.TestCase):

    # Hand-computed reference: obs=[10,20,30], pred=[12,18,33]
    # See module docstring for arithmetic.
    _OBS  = [10.0, 20.0, 30.0]
    _PRED = [12.0, 18.0, 33.0]

    def _ref(self) -> Dict[str, Any]:
        return {
            "n":        3,
            "mae":      7.0 / 3.0,
            "rmse":     math.sqrt(17.0 / 3.0),
            "bias":     1.0,
            "mape":     40.0 / 3.0,
            "n_mape":   3,
            "n_skipped": 0,
        }

    def test_reference_values(self):
        result = metrics(self._OBS, self._PRED)
        ref = self._ref()
        for key in ("n", "n_mape", "n_skipped"):
            self.assertEqual(result[key], ref[key])
        for key in ("mae", "rmse", "bias", "mape"):
            self.assertAlmostEqual(result[key], ref[key], delta=1e-9,
                                   msg=f"{key} mismatch")

    def test_n_equals_length(self):
        result = metrics(self._OBS, self._PRED)
        self.assertEqual(result["n"], 3)

    def test_mape_skips_zero_obs(self):
        result = metrics([0.0, 10.0], [5.0, 12.0])
        self.assertEqual(result["n_skipped"], 1)
        self.assertEqual(result["n_mape"], 1)
        # mape = |2/10|*100 = 20.0
        self.assertAlmostEqual(result["mape"], 20.0, delta=1e-9)

    def test_all_zero_obs_gives_none_mape(self):
        result = metrics([0.0, 0.0], [1.0, 2.0])
        self.assertIsNone(result["mape"])
        self.assertEqual(result["n_skipped"], 2)
        self.assertEqual(result["n_mape"], 0)

    def test_length_mismatch_raises(self):
        with self.assertRaises(ValueError) as ctx:
            metrics([1.0, 2.0], [1.0])
        self.assertIn("length mismatch", str(ctx.exception))

    def test_empty_raises(self):
        with self.assertRaises(ValueError) as ctx:
            metrics([], [])
        self.assertIn("n == 0", str(ctx.exception))

    def test_perfect_prediction(self):
        result = metrics([1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
        self.assertAlmostEqual(result["mae"], 0.0, delta=1e-12)
        self.assertAlmostEqual(result["rmse"], 0.0, delta=1e-12)
        self.assertAlmostEqual(result["bias"], 0.0, delta=1e-12)
        self.assertAlmostEqual(result["mape"], 0.0, delta=1e-12)

    def test_single_pair(self):
        result = metrics([4.0], [6.0])
        self.assertEqual(result["n"], 1)
        self.assertAlmostEqual(result["mae"], 2.0, delta=1e-12)
        self.assertAlmostEqual(result["bias"], 2.0, delta=1e-12)

    def test_rmse_ge_mae(self):
        result = metrics(self._OBS, self._PRED)
        self.assertGreaterEqual(result["rmse"], result["mae"])

    def test_result_keys(self):
        result = metrics(self._OBS, self._PRED)
        self.assertSetEqual(
            set(result.keys()),
            {"n", "mae", "rmse", "bias", "mape", "n_mape", "n_skipped"},
        )


# ---------------------------------------------------------------------------
# 2. load_observations()
# ---------------------------------------------------------------------------

class TestLoadObservations(unittest.TestCase):

    def test_real_rows_returned(self):
        rows = [
            {"source_type": "real",      "study_id": "s1", "source": "A", "val": "1"},
            {"source_type": "synthetic", "study_id": "s2", "source": "B", "val": "2"},
            {"source_type": "real",      "study_id": "s3", "source": "C", "val": "3"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "obs.csv"
            _write_csv(rows, p)
            real, rep = load_observations(p, ["val"])
        self.assertEqual(len(real), 2)
        self.assertEqual(rep["n_real"], 2)

    def test_synthetic_dropped_and_counted(self):
        rows = [
            {"source_type": "real",      "study_id": "s1", "source": "A", "v": "1"},
            {"source_type": "synthetic", "study_id": "s2", "source": "B", "v": "2"},
            {"source_type": "synthetic", "study_id": "s3", "source": "C", "v": "3"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "obs.csv"
            _write_csv(rows, p)
            _, rep = load_observations(p, ["v"])
        self.assertEqual(rep["n_synthetic_dropped"], 2)

    def test_all_synthetic_raises(self):
        rows = [
            {"source_type": "synthetic", "study_id": "s1", "source": "A", "v": "1"},
            {"source_type": "synthetic", "study_id": "s2", "source": "B", "v": "2"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "obs.csv"
            _write_csv(rows, p)
            with self.assertRaises(ValueError) as ctx:
                load_observations(p, ["v"])
        self.assertIn("no real observations", str(ctx.exception))

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            load_observations("/nonexistent/path/file.csv", ["col"])

    def test_missing_columns_reported(self):
        rows = [{"source_type": "real", "study_id": "s1", "source": "A"}]
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "obs.csv"
            _write_csv(rows, p)
            _, rep = load_observations(p, ["missing_col"])
        self.assertIn("missing_col", rep["missing_columns"])

    def test_other_source_type_counted(self):
        rows = [
            {"source_type": "real",    "study_id": "s1", "source": "A", "v": "1"},
            {"source_type": "unknown", "study_id": "s2", "source": "B", "v": "2"},
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            p = Path(tmpdir) / "obs.csv"
            _write_csv(rows, p)
            _, rep = load_observations(p, ["v"])
        self.assertEqual(rep["n_other_dropped"], 1)


# ---------------------------------------------------------------------------
# 3. validate_bmp()
# ---------------------------------------------------------------------------

class TestValidateBMP(unittest.TestCase):

    def test_basic_structure(self):
        rows = _bmp_real_rows(n=3, obs_fraction=0.80)
        result = validate_bmp(rows)
        self.assertIn("n", result)
        self.assertIn("ceiling_violations", result)
        self.assertIn("overall_metrics", result)
        self.assertIn("per_feedstock", result)
        self.assertIn("sample_sizes", result)
        self.assertEqual(result["status"], "illustrative_estimate")

    def test_no_ceiling_violations_when_below(self):
        rows = _bmp_real_rows(n=4, obs_fraction=0.80)
        result = validate_bmp(rows)
        self.assertEqual(result["ceiling_violations"], 0)

    def test_ceiling_violation_detected(self):
        # observed > ceiling: use obs_fraction > 1.0
        rows = _bmp_real_rows(n=3, obs_fraction=1.10)
        result = validate_bmp(rows)
        self.assertGreater(result["ceiling_violations"], 0)

    def test_n_matches_valid_rows(self):
        rows = _bmp_real_rows(n=5)
        result = validate_bmp(rows)
        self.assertEqual(result["n"], 5)

    def test_invalid_row_counted(self):
        rows = _bmp_real_rows(n=3)
        rows.append({
            "source_type": "real", "study_id": "bad", "source": "x",
            "feedstock": "bad", "vs_kg": "not_a_number",
            "observed_ch4_nm3": "1.0", "carb": "0.6",
            "protein": "0.2", "lipid": "0.2",
        })
        result = validate_bmp(rows)
        self.assertEqual(result["n_errors"], 1)
        self.assertEqual(result["n"], 3)

    def test_per_feedstock_contains_label(self):
        rows = _bmp_real_rows(n=4)
        result = validate_bmp(rows)
        self.assertIn("mixed_organic", result["per_feedstock"])

    def test_sample_sizes_match(self):
        rows = _bmp_real_rows(n=4)
        result = validate_bmp(rows)
        self.assertEqual(result["sample_sizes"]["mixed_organic"], 4)

    def test_overall_metrics_structure(self):
        rows = _bmp_real_rows(n=3)
        result = validate_bmp(rows)
        om = result["overall_metrics"]
        self.assertIsNotNone(om)
        for key in ("n", "mae", "rmse", "bias"):
            self.assertIn(key, om)


# ---------------------------------------------------------------------------
# 4. validate_net_energy()
# ---------------------------------------------------------------------------

class TestValidateNetEnergy(unittest.TestCase):

    def test_basic_structure(self):
        rows = _net_energy_rows(n=3)
        result = validate_net_energy(rows)
        for key in ("n", "n_invalid_params", "n_errors", "overall_metrics",
                    "per_plant", "total_warnings", "status"):
            self.assertIn(key, result)

    def test_n_matches_rows(self):
        rows = _net_energy_rows(n=4)
        result = validate_net_energy(rows)
        self.assertEqual(result["n"], 4)

    def test_invalid_params_reported_not_raised(self):
        rows = _net_energy_rows(n=2)
        # eta_boiler <= eta_th violates Params constraint
        rows.append({
            "source_type": "real", "study_id": "bad", "source": "x",
            "observed_net_kwh_d": "100.0",
            "eta_th": "0.90", "eta_boiler": "0.45",  # invalid: boiler <= th
        })
        result = validate_net_energy(rows)
        self.assertEqual(result["n_invalid_params"], 1)
        self.assertEqual(result["n"], 2)  # only 2 valid rows processed

    def test_missing_observed_counted_as_error(self):
        rows = [{"source_type": "real", "study_id": "s1", "source": "A"}]
        result = validate_net_energy(rows)
        self.assertEqual(result["n_errors"], 1)
        self.assertEqual(result["n"], 0)

    def test_per_plant_keyed_by_study_id(self):
        rows = _net_energy_rows(n=3)
        result = validate_net_energy(rows)
        for i in range(3):
            self.assertIn(f"plant_{i}", result["per_plant"])

    def test_params_override_applies(self):
        # Use y_biogas_nm3_per_kg_vs=0.0 → very low net energy
        row_low  = {"source_type": "real", "study_id": "p1", "source": "x",
                    "observed_net_kwh_d": "50.0", "y_biogas_nm3_per_kg_vs": "0.01"}
        row_high = {"source_type": "real", "study_id": "p2", "source": "x",
                    "observed_net_kwh_d": "50.0", "y_biogas_nm3_per_kg_vs": "0.80"}
        r_low  = validate_net_energy([row_low])
        r_high = validate_net_energy([row_high])
        # higher yield → higher predicted net energy
        self.assertLess(
            r_low["overall_metrics"]["bias"],
            r_high["overall_metrics"]["bias"],
        )


# ---------------------------------------------------------------------------
# 5. validate_mass_loss()
# ---------------------------------------------------------------------------

class TestValidateMassLoss(unittest.TestCase):

    def test_basic_structure(self):
        rows = _vsd_rows(n=3)
        result = validate_mass_loss(rows)
        for key in ("n", "n_invalid_params", "n_errors", "overall_metrics",
                    "per_plant", "status"):
            self.assertIn(key, result)

    def test_n_matches_valid_rows(self):
        rows = _vsd_rows(n=4)
        result = validate_mass_loss(rows)
        self.assertEqual(result["n"], 4)

    def test_missing_observed_counted(self):
        rows = [{"source_type": "real", "study_id": "s1", "source": "A"}]
        result = validate_mass_loss(rows)
        self.assertEqual(result["n_errors"], 1)

    def test_invalid_params_reported(self):
        rows = _vsd_rows(n=2)
        rows.append({
            "source_type": "real", "study_id": "bad", "source": "x",
            "observed_vs_destruction": "0.4",
            "eta_th": "0.90", "eta_boiler": "0.45",
        })
        result = validate_mass_loss(rows)
        self.assertEqual(result["n_invalid_params"], 1)

    def test_per_plant_present(self):
        rows = _vsd_rows(n=2)
        result = validate_mass_loss(rows)
        self.assertIn("plant_0", result["per_plant"])
        self.assertIn("plant_1", result["per_plant"])


# ---------------------------------------------------------------------------
# 6. report()
# ---------------------------------------------------------------------------

class TestReport(unittest.TestCase):

    def _bmp_result(self, n: int) -> Dict[str, Any]:
        return {"n": n, "status": "illustrative_estimate"}

    def _ne_result(self, n: int) -> Dict[str, Any]:
        return {"n": n, "status": "illustrative_estimate"}

    def _vsd_result(self, n: int) -> Dict[str, Any]:
        return {"n": n, "status": "illustrative_estimate"}

    def test_limitations_present(self):
        r = report({})
        self.assertIn("limitations", r)
        self.assertIsInstance(r["limitations"], list)
        self.assertGreater(len(r["limitations"]), 0)

    def test_fewer_than_10_rows_gives_empty_pathways(self):
        # TEST FIXTURE: 5 rows per quantity — below threshold of 10
        results = {
            "bmp":        self._bmp_result(5),
            "net_energy": self._ne_result(5),
            "mass_loss":  self._vsd_result(5),
        }
        r = report(results)
        self.assertEqual(r["pathways_validated"], [])
        self.assertIn("insufficient", r["message"])

    def test_10_or_more_rows_gives_ad_pathway(self):
        # TEST FIXTURE: 12 rows per quantity — at/above threshold
        results = {
            "bmp":        self._bmp_result(12),
            "net_energy": self._ne_result(12),
            "mass_loss":  self._vsd_result(12),
        }
        r = report(results)
        self.assertIn("anaerobic_digestion", r["pathways_validated"])

    def test_mixed_counts_below_threshold(self):
        # One quantity below threshold → not validated
        results = {
            "bmp":        self._bmp_result(15),
            "net_energy": self._ne_result(3),   # below 10
            "mass_loss":  self._vsd_result(15),
        }
        r = report(results)
        self.assertEqual(r["pathways_validated"], [])

    def test_empty_results_gives_empty_pathways(self):
        r = report({})
        self.assertEqual(r["pathways_validated"], [])

    def test_sub_results_forwarded(self):
        bmp_sub = self._bmp_result(12)
        results = {"bmp": bmp_sub, "net_energy": self._ne_result(12),
                   "mass_loss": self._vsd_result(12)}
        r = report(results)
        self.assertIn("bmp", r)
        self.assertIs(r["bmp"], bmp_sub)

    def test_status_is_illustrative_estimate(self):
        r = report({})
        self.assertEqual(r["status"], "illustrative_estimate")

    def test_json_serialisable(self):
        bmp_rows = _bmp_real_rows(n=3)
        bmp_result = validate_bmp(bmp_rows)
        ne_rows = _net_energy_rows(n=3)
        ne_result = validate_net_energy(ne_rows)
        vsd_rows = _vsd_rows(n=3)
        vsd_result = validate_mass_loss(vsd_rows)
        r = report({"bmp": bmp_result, "net_energy": ne_result,
                    "mass_loss": vsd_result})
        json.dumps(r)  # must not raise

    def test_no_pass_fail_threshold_in_limitations(self):
        r = report({})
        combined = " ".join(r["limitations"]).lower()
        self.assertIn("no pass/fail", combined)


# ---------------------------------------------------------------------------
# 7. JSON serialisability of individual functions
# ---------------------------------------------------------------------------

class TestJSONSerialisable(unittest.TestCase):

    def test_metrics_json(self):
        r = metrics([10.0, 20.0, 30.0], [12.0, 18.0, 33.0])
        json.dumps(r)

    def test_metrics_json_none_mape(self):
        r = metrics([0.0, 0.0], [1.0, 2.0])
        json.dumps(r)  # mape is None — must serialise

    def test_validate_bmp_json(self):
        rows = _bmp_real_rows(n=4)
        json.dumps(validate_bmp(rows))

    def test_validate_net_energy_json(self):
        rows = _net_energy_rows(n=3)
        json.dumps(validate_net_energy(rows))

    def test_validate_mass_loss_json(self):
        rows = _vsd_rows(n=3)
        json.dumps(validate_mass_loss(rows))


# ---------------------------------------------------------------------------
# 8. BMP composition sum tolerance and fitted rows
# ---------------------------------------------------------------------------

class TestBMPCompositionToleranceAndFittedRows(unittest.TestCase):
    """Tests for composition sum tolerance and fitted-row exclusion/reporting in validate_bmp.

    All rows used below are TEST FIXTURES — tiny synthetic rows crafted to exercise
    specific code paths. They are NOT real measurements and carry no scientific meaning.
    """

    def test_composition_sum_1_001_accepted_reported_and_flagged(self):
        # TEST FIXTURE — tiny row, shares sum = 0.601 + 0.2 + 0.2 = 1.001
        row = {
            "source_type": "real",
            "study_id": "fixture_reported_1001",
            "source": "test fixture",
            "feedstock": "test_feedstock",
            "vs_kg": "1.0",
            "observed_ch4_nm3": "0.4",
            "carb": "0.601",
            "protein": "0.2",
            "lipid": "0.2",
            "composition_method": "reported",
        }
        result = validate_bmp([row])
        self.assertEqual(result["n"], 1)
        self.assertEqual(result["n_errors"], 0)
        self.assertEqual(result["composition_rounded"]["reported"], 1)
        self.assertTrue(row.get("composition_rounded"))

    def test_composition_sum_1_003_rejected_reported(self):
        # TEST FIXTURE — tiny row, shares sum = 0.603 + 0.2 + 0.2 = 1.003 (|1.003 - 1| > 0.002)
        row = {
            "source_type": "real",
            "study_id": "fixture_reported_1003",
            "source": "test fixture",
            "feedstock": "test_feedstock",
            "vs_kg": "1.0",
            "observed_ch4_nm3": "0.4",
            "carb": "0.603",
            "protein": "0.2",
            "lipid": "0.2",
            "composition_method": "reported",
        }
        result = validate_bmp([row])
        self.assertEqual(result["n"], 0)
        self.assertEqual(result["n_errors"], 1)
        self.assertEqual(result["composition_rounded"]["reported"], 0)

    def test_composition_sum_1_003_accepted_digitised(self):
        # TEST FIXTURE — tiny row, shares sum = 0.603 + 0.2 + 0.2 = 1.003 (|1.003 - 1| <= 0.01)
        row = {
            "source_type": "real",
            "study_id": "fixture_digitised_1003",
            "source": "test fixture",
            "feedstock": "test_feedstock",
            "vs_kg": "1.0",
            "observed_ch4_nm3": "0.4",
            "carb": "0.603",
            "protein": "0.2",
            "lipid": "0.2",
            "composition_method": "digitised",
        }
        result = validate_bmp([row])
        self.assertEqual(result["n"], 1)
        self.assertEqual(result["n_errors"], 0)
        self.assertEqual(result["composition_rounded"]["digitised"], 1)
        self.assertTrue(row.get("composition_rounded"))

    def test_composition_sum_1_02_rejected_digitised(self):
        # TEST FIXTURE — tiny row, shares sum = 0.62 + 0.2 + 0.2 = 1.02 (|1.02 - 1| > 0.01)
        row = {
            "source_type": "real",
            "study_id": "fixture_digitised_102",
            "source": "test fixture",
            "feedstock": "test_feedstock",
            "vs_kg": "1.0",
            "observed_ch4_nm3": "0.4",
            "carb": "0.62",
            "protein": "0.2",
            "lipid": "0.2",
            "composition_method": "digitised",
        }
        result = validate_bmp([row])
        self.assertEqual(result["n"], 0)
        self.assertEqual(result["n_errors"], 1)
        self.assertEqual(result["composition_rounded"]["digitised"], 0)

    def test_ceiling_equals_explicit_formula_on_unscaled_shares(self):
        # TEST FIXTURE — tiny row with unscaled shares summing to 1.001
        # Formula: (0.601 * 0.415 + 0.2 * 0.496 + 0.2 * 1.014) * 2.0 = 1.10283
        row = {
            "source_type": "real",
            "study_id": "fixture_unscaled",
            "source": "test fixture",
            "feedstock": "test_feedstock",
            "vs_kg": "2.0",
            "observed_ch4_nm3": "1.0",
            "carb": "0.601",
            "protein": "0.2",
            "lipid": "0.2",
            "composition_method": "reported",
        }
        result = validate_bmp([row])
        expected_ceiling_nm3 = (0.601 * 0.415 + 0.2 * 0.496 + 0.2 * 1.014) * 2.0
        # metrics bias = predicted - observed
        expected_bias = expected_ceiling_nm3 - 1.0
        self.assertAlmostEqual(result["overall_metrics"]["bias"], expected_bias, delta=1e-9)

    def test_fitted_rows_counted_under_fitted_excluded_and_never_in_n_rows(self):
        # TEST FIXTURE — tiny synthetic rows: 2 measured rows and 2 fitted rows
        rows = [
            {
                "source_type": "real",
                "study_id": "study_meas_1",
                "source": "test fixture",
                "feedstock": "feed_a",
                "vs_kg": "1.0",
                "observed_ch4_nm3": "0.4",
                "carb": "0.6",
                "protein": "0.2",
                "lipid": "0.2",
                "measured_or_fitted": "measured",
            },
            {
                "source_type": "real",
                "study_id": "study_meas_2",
                "source": "test fixture",
                "feedstock": "feed_a",
                "vs_kg": "1.0",
                "observed_ch4_nm3": "0.45",
                "carb": "0.6",
                "protein": "0.2",
                "lipid": "0.2",
                "measured_or_fitted": "measured",
            },
            {
                "source_type": "real",
                "study_id": "study_fit_1",
                "source": "test fixture",
                "feedstock": "feed_b",
                "vs_kg": "1.0",
                "observed_ch4_nm3": "0.3",
                "carb": "0.6",
                "protein": "0.2",
                "lipid": "0.2",
                "measured_or_fitted": "fitted",
            },
            {
                "source_type": "real",
                "study_id": "study_fit_2",
                "source": "test fixture",
                "feedstock": "feed_b",
                "vs_kg": "1.0",
                "observed_ch4_nm3": "0.35",
                "carb": "0.6",
                "protein": "0.2",
                "lipid": "0.2",
                "measured_or_fitted": "fitted",
            },
        ]
        result = validate_bmp(rows)
        self.assertEqual(result["fitted_excluded"], 2)
        self.assertEqual(result["n"], 2)
        self.assertEqual(result["n_rows"], 2)

    def test_fitted_row_above_ceiling_appears_in_fitted_above_ceiling(self):
        # TEST FIXTURE — tiny synthetic rows:
        # ceiling = (0.6*0.415 + 0.2*0.496 + 0.2*1.014) * 1.0 = 0.551
        # fit_high has observed=0.60 > 0.551 (above ceiling)
        # fit_low has observed=0.40 <= 0.551 (below ceiling)
        rows = [
            {
                "source_type": "real",
                "study_id": "fit_high",
                "source": "test fixture",
                "feedstock": "manure",
                "vs_kg": "1.0",
                "observed_ch4_nm3": "0.60",
                "carb": "0.6",
                "protein": "0.2",
                "lipid": "0.2",
                "measured_or_fitted": "fitted",
            },
            {
                "source_type": "real",
                "study_id": "fit_low",
                "source": "test fixture",
                "feedstock": "sludge",
                "vs_kg": "1.0",
                "observed_ch4_nm3": "0.40",
                "carb": "0.6",
                "protein": "0.2",
                "lipid": "0.2",
                "measured_or_fitted": "fitted",
            },
        ]
        result = validate_bmp(rows)
        self.assertEqual(result["fitted_excluded"], 2)
        self.assertEqual(result["n"], 0)
        self.assertEqual(len(result["fitted_above_ceiling"]), 1)
        entry = result["fitted_above_ceiling"][0]
        self.assertEqual(entry.study_id, "fit_high")
        self.assertEqual(entry["study_id"], "fit_high")
        self.assertEqual(entry[0], "fit_high")
        self.assertEqual(entry.feedstock, "manure")
        self.assertEqual(entry["feedstock"], "manure")
        self.assertEqual(entry[1], "manure")
        self.assertAlmostEqual(entry.observed, 0.60, delta=1e-9)
        self.assertAlmostEqual(entry["observed"], 0.60, delta=1e-9)
        self.assertAlmostEqual(entry[2], 0.60, delta=1e-9)
        self.assertAlmostEqual(entry.ceiling, 0.551, delta=1e-9)
        self.assertAlmostEqual(entry["ceiling"], 0.551, delta=1e-9)
        self.assertAlmostEqual(entry[3], 0.551, delta=1e-9)

    def test_tolerance_module_constants(self):
        self.assertEqual(COMPOSITION_TOLERANCE_REPORTED, 0.002)
        self.assertEqual(COMPOSITION_TOLERANCE_DIGITISED, 0.01)


if __name__ == "__main__":
    unittest.main()
