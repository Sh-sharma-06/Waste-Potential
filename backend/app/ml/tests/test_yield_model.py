"""Unit tests for yield model components: L1 kinetics, domain guard, L2 residual, Buswell clamp, and leakage checks."""

import unittest
import numpy as np
from sklearn.model_selection import GroupKFold

from app.ml.yield_model.kinetic import kinetic, fit_kinetic
from app.ml.yield_model.domain_guard import DomainGuard
from app.ml.yield_model.residual_gbr import ResidualGBR
from app.ml.yield_model.evaluate import calculate_metrics, assert_no_leakage


class TestYieldModel(unittest.TestCase):
    """Test suite for Part B2 hybrid yield models."""

    def setUp(self):
        # Reproducible synthetic test dataset
        self.rng = np.random.default_rng(42)
        self.n_samples = 200
        self.n_plants = 20
        self.plant_ids = np.repeat(np.arange(self.n_plants), self.n_samples // self.n_plants)
        self.fs_idx = self.rng.integers(0, 4, size=self.n_samples)
        self.hrt = self.rng.uniform(10, 60, size=self.n_samples)
        self.olr = self.rng.uniform(1, 8, size=self.n_samples)
        self.temp = self.rng.uniform(30, 40, size=self.n_samples)
        self.cn = self.rng.uniform(10, 30, size=self.n_samples)

        # Baseline kinetic yields
        p_true = [0.85, 0.35, 0.50, 0.65, 0.4, 0.8]
        self.y_kinetic = kinetic(p_true, self.fs_idx, self.hrt)
        # Synthetic observations with non-linear factor
        self.y_obs = self.y_kinetic * (1.0 / (1.0 + (self.olr / 8.0) ** 2))

        # One-hot features + continuous variables
        oh = np.eye(4)[self.fs_idx]
        self.X = np.column_stack([oh, self.temp, self.hrt, self.olr, self.cn])

    def test_domain_guard_flags_out_of_domain(self):
        """DomainGuard must flag any observation whose features fall outside training min/max."""
        X_train = np.array([
            [1.0, 20.0, 2.0],
            [2.0, 30.0, 4.0],
            [1.5, 25.0, 3.0],
        ])
        guard = DomainGuard(X_train)

        # In-domain observation
        in_domain = np.array([1.5, 25.0, 3.0])
        self.assertFalse(guard.is_extrapolation(in_domain))
        self.assertFalse(guard.outside(in_domain.reshape(1, -1))[0])

        # Out-of-domain observations
        out_below = np.array([0.5, 25.0, 3.0])  # feature 0 < 1.0
        out_above = np.array([1.5, 35.0, 3.0])  # feature 1 > 30.0
        self.assertTrue(guard.is_extrapolation(out_below))
        self.assertTrue(guard.is_extrapolation(out_above))

        batch_test = np.array([
            [1.5, 25.0, 3.0],  # False
            [0.5, 25.0, 3.0],  # True
            [1.5, 35.0, 3.0],  # True
        ])
        flags = guard.outside(batch_test)
        np.testing.assert_array_equal(flags, np.array([False, True, True]))

    def test_flagged_rows_return_l1_not_ml(self):
        """When features are out-of-domain, hybrid predictions must strictly fall back to L1 kinetic values."""
        # Train on OLR <= 5.0
        train_mask = self.olr <= 5.0
        test_mask = self.olr > 5.0

        gbr = ResidualGBR()
        gbr.fit(self.X[train_mask], self.y_obs[train_mask], self.y_kinetic[train_mask])

        # Unguarded vs guarded predictions on test set (OLR > 5.0)
        pred_guarded, flags = gbr.predict_hybrid(
            self.X[test_mask],
            self.y_kinetic[test_mask],
            guarded=True
        )

        # All test rows must be flagged as extrapolation
        self.assertTrue(np.all(flags))
        # Guarded predictions must match L1 kinetic physics exactly
        np.testing.assert_allclose(pred_guarded, self.y_kinetic[test_mask], rtol=1e-7)

        # Unguarded predictions should NOT equal L1 kinetic values because ML learned residuals
        pred_unguarded, _ = gbr.predict_hybrid(
            self.X[test_mask],
            self.y_kinetic[test_mask],
            guarded=False
        )
        self.assertFalse(np.allclose(pred_unguarded, self.y_kinetic[test_mask]))

    def test_buswell_ceiling_clamps_biogas_basis(self):
        """When yield_type='biogas', ceiling is bound / ch4_fraction (0.551 / 0.60 = 0.91833 Nm3/kg VS)."""
        gbr = ResidualGBR()
        gbr.fit(self.X[:50], self.y_obs[:50], self.y_kinetic[:50])

        buswell_ch4 = 0.551
        ch4_frac = 0.60
        expected_biogas_ceiling = buswell_ch4 / ch4_frac  # ~0.918333

        # Force large kinetic baseline
        large_kinetic = np.full(10, 2.0)
        pred, _ = gbr.predict_hybrid(
            self.X[:10],
            large_kinetic,
            buswell_ch4_bound=buswell_ch4,
            ch4_fraction=ch4_frac,
            yield_type="biogas",
            guarded=False
        )

        self.assertTrue(np.all(pred <= expected_biogas_ceiling + 1e-9))
        self.assertTrue(np.allclose(pred, expected_biogas_ceiling))

    def test_buswell_ceiling_clamps_ch4_basis(self):
        """When yield_type='ch4', ceiling is applied directly as buswell_ch4_bound (0.551 Nm3 CH4/kg VS)."""
        gbr = ResidualGBR()
        gbr.fit(self.X[:50], self.y_obs[:50], self.y_kinetic[:50])

        buswell_ch4 = 0.551

        # Force large kinetic baseline
        large_kinetic = np.full(10, 1.5)
        pred, _ = gbr.predict_hybrid(
            self.X[:10],
            large_kinetic,
            buswell_ch4_bound=buswell_ch4,
            yield_type="ch4",
            guarded=False
        )

        self.assertTrue(np.all(pred <= buswell_ch4 + 1e-9))
        self.assertTrue(np.allclose(pred, buswell_ch4))

    def test_buswell_invalid_parameters_raise(self):
        """Invalid ch4_fraction or yield_type must raise ValueError."""
        gbr = ResidualGBR()
        gbr.fit(self.X[:20], self.y_obs[:20], self.y_kinetic[:20])

        with self.assertRaises(ValueError):
            gbr.predict_hybrid(self.X[:5], self.y_kinetic[:5], ch4_fraction=0.0)

        with self.assertRaises(ValueError):
            gbr.predict_hybrid(self.X[:5], self.y_kinetic[:5], yield_type="hydrogen")

    def test_assert_no_leakage_success(self):
        """assert_no_leakage should pass when disjoint groups are provided."""
        train_groups = ["study_1", "study_2", "study_3"]
        test_groups = ["study_4", "study_5"]
        # Should not raise
        assert_no_leakage(train_groups, test_groups)

    def test_assert_no_leakage_raises_on_overlap(self):
        """Deliberately leaking study IDs must raise ValueError naming the overlapping IDs."""
        train_groups = ["study_A", "study_B", "study_C", "study_D"]
        test_groups = ["study_C", "study_E"]  # study_C leaks!

        with self.assertRaises(ValueError) as ctx:
            assert_no_leakage(train_groups, test_groups)

        err_msg = str(ctx.exception)
        self.assertIn("Study/group leakage detected", err_msg)
        self.assertIn("study_C", err_msg)

    def test_no_study_leakage_groupkfold(self):
        """GroupKFold across synthetic plant IDs passes assert_no_leakage on every fold."""
        gkf = GroupKFold(n_splits=5)
        indices = np.arange(self.n_samples)

        for fold, (train_idx, test_idx) in enumerate(gkf.split(indices, groups=self.plant_ids)):
            assert_no_leakage(self.plant_ids[train_idx], self.plant_ids[test_idx])

    def test_kinetic_physics_properties(self):
        """Kinetic model must be monotonic in HRT and positive."""
        p = [0.85, 0.35, 0.50, 0.65, 0.4, 0.8]
        hrt_short = kinetic(p, 0, 15.0)
        hrt_long = kinetic(p, 0, 45.0)

        # Biogas yield increases with longer retention time
        self.assertGreater(hrt_long, hrt_short)
        self.assertGreater(hrt_short, 0.0)

    def test_evaluate_metrics(self):
        """Evaluation metrics calculate MAE, RMSE, bias, and MAPE correctly."""
        a = np.array([1.0, 2.0, 3.0])
        p = np.array([1.1, 1.9, 3.3])

        m = calculate_metrics(a, p)
        self.assertAlmostEqual(m["MAE"], 0.1666666, places=5)
        self.assertAlmostEqual(m["bias"], 0.10, places=5)
        self.assertGreater(m["RMSE"], 0.0)
        self.assertGreater(m["MAPE"], 0.0)


if __name__ == "__main__":
    unittest.main()
