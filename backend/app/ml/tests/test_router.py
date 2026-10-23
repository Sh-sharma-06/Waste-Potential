"""Tests for POST /ml/yield and GET /ml/models.

The bundle built here is a SYNTHETIC test fixture (made-up numbers, synthetic=True)
used only to exercise the routes. It is not a trained model and not real data.
"""

import os
import tempfile
import unittest
from unittest import mock

import numpy as np
from fastapi.testclient import TestClient

from app.core_engine.params import Params
from app.main import app
from app.ml.registry.store import ModelBundle, save_bundle
from app.ml.yield_model.ceiling import ceiling_with_lignin
from app.ml.yield_model.domain_guard import DomainGuard

client = TestClient(app)

BODY = {"feedstock": "food", "hrt_days": 30.0, "temperature_c": 37.0, "olr": 3.5, "c_n": 25.0}
# Chen-Hashimoto for the fixture: y0=0.6, mu=0.4, k=0.8, hrt=30
EXPECTED_BIOGAS = 0.6 * (1 - 0.8 / (30 * 0.4 - 1 + 0.8))


def _fixture_bundle() -> ModelBundle:
    # Feature vector = one-hot over feedstocks_seen (2) + temp, hrt, olr, c_n = 6 columns.
    guard = DomainGuard(
        bounds=(np.zeros(6), np.array([1, 1, 100, 100, 100, 100], dtype=float)),
        feedstocks_seen=["food", "manure"],
    )
    return ModelBundle(
        model_version="test-fixture",
        feedstocks_seen=["food", "manure"],
        kinetic_params={"y0": {"food": 0.6, "manure": 0.3}, "mu": 0.4, "k": 0.8},
        residual_model=None,
        domain_guard=guard,
        metrics={"cv_residual_std_log": 0.1, "l2_skipped": True},
        training_data_hash="test",
        synthetic=True,
    )


class _ModelDirCase(unittest.TestCase):
    def use_model_dir(self, with_bundle: bool) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        if with_bundle:
            save_bundle(_fixture_bundle(), target_dir=tmp.name)
        patcher = mock.patch.dict(os.environ, {"MODEL_DIR": tmp.name})
        patcher.start()
        self.addCleanup(patcher.stop)


class TestRoutesMounted(unittest.TestCase):
    def test_exact_paths(self):
        paths = app.openapi()["paths"]
        self.assertIn("/ml/yield", paths)
        self.assertIn("post", paths["/ml/yield"])
        self.assertIn("/ml/models", paths)
        self.assertIn("get", paths["/ml/models"])
        self.assertNotIn("/ml/ml/yield", paths)

class TestYieldWithoutModel(_ModelDirCase):
    def test_503_when_no_bundle(self):
        self.use_model_dir(with_bundle=False)
        r = client.post("/ml/yield", json=BODY)
        self.assertEqual(r.status_code, 503)
        self.assertIn("no trained model", r.json()["detail"].lower())

    def test_unknown_label_is_422_even_without_a_bundle(self):
        self.use_model_dir(with_bundle=False)
        r = client.post("/ml/yield", json={**BODY, "feedstock": "crop"})
        self.assertEqual(r.status_code, 422)
        detail = r.json()["detail"]
        for name in ("food", "manure", "crop_residue", "mixed"):
            self.assertIn(name, detail)

    def test_blank_label_is_422(self):
        self.use_model_dir(with_bundle=False)
        r = client.post("/ml/yield", json={**BODY, "feedstock": "  "})
        self.assertEqual(r.status_code, 422)

    def test_invalid_ch4_fraction_is_422(self):
        self.use_model_dir(with_bundle=False)
        for bad in (0, -0.2, 1.5):
            r = client.post("/ml/yield", json={**BODY, "ch4_fraction": bad})
            self.assertEqual(r.status_code, 422)

    def test_extra_field_is_422(self):
        self.use_model_dir(with_bundle=False)
        r = client.post("/ml/yield", json={**BODY, "unexpected": 1})
        self.assertEqual(r.status_code, 422)

    def test_partial_composition_is_422(self):
        self.use_model_dir(with_bundle=False)
        r = client.post("/ml/yield", json={**BODY, "carb": 0.6})
        self.assertEqual(r.status_code, 422)

    def test_composition_not_summing_to_one_is_422(self):
        self.use_model_dir(with_bundle=False)
        r = client.post(
            "/ml/yield",
            json={**BODY, "carb": 0.5, "protein": 0.2, "lipid": 0.1, "lignin": 0.1},
        )
        self.assertEqual(r.status_code, 422)


class TestYieldWithFixtureBundle(_ModelDirCase):
    def test_default_fraction_comes_from_params(self):
        self.use_model_dir(with_bundle=True)
        r = client.post("/ml/yield", json=BODY)
        self.assertEqual(r.status_code, 200)
        b = r.json()
        frac = Params().ch4_fraction
        self.assertEqual(b["ch4_fraction_source"], "default_illustrative")
        self.assertAlmostEqual(b["ch4_fraction_used"], frac, places=12)
        self.assertAlmostEqual(b["y_biogas_nm3_per_kg_vs"], EXPECTED_BIOGAS, places=9)
        self.assertAlmostEqual(b["y_ch4_nm3_per_kg_vs"], EXPECTED_BIOGAS * frac, places=9)
        self.assertEqual(b["basis"], "per kg VS")
        self.assertIn("0 C, 1 atm, dry", b["gas_basis"])
        self.assertNotIn("ceiling_check", b)
        self.assertTrue(any("SYNTHETIC" in w for w in b["warnings"]))
        self.assertTrue(any("ch4_fraction not supplied" in w for w in b["warnings"]))

    def test_request_fraction_is_used_and_round_trips(self):
        self.use_model_dir(with_bundle=True)
        r = client.post("/ml/yield", json={**BODY, "ch4_fraction": 0.5})
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertEqual(b["ch4_fraction_source"], "request")
        self.assertAlmostEqual(b["ch4_fraction_used"], 0.5, places=12)
        self.assertAlmostEqual(b["y_ch4_nm3_per_kg_vs"] / 0.5, b["y_biogas_nm3_per_kg_vs"], places=9)

    def test_ceiling_not_clipped(self):
        self.use_model_dir(with_bundle=True)
        comp = {"carb": 0.6, "protein": 0.2, "lipid": 0.1, "lignin": 0.1}
        r = client.post("/ml/yield", json={**BODY, "ch4_fraction": 0.6, **comp})
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertFalse(b["ceiling_check"]["clipped"])
        self.assertAlmostEqual(
            b["ceiling_check"]["ceiling_ch4_nm3_per_kg_vs"],
            ceiling_with_lignin(0.6, 0.2, 0.1, 0.1),
            places=12,
        )

    def test_ceiling_clips_methane_before_biogas_conversion(self):
        self.use_model_dir(with_bundle=True)
        comp = {"carb": 0.5, "protein": 0.0, "lipid": 0.0, "lignin": 0.5}
        r = client.post("/ml/yield", json={**BODY, "ch4_fraction": 0.6, **comp})
        self.assertEqual(r.status_code, 200)
        b = r.json()
        ceiling = ceiling_with_lignin(0.5, 0.0, 0.0, 0.5)
        self.assertTrue(b["ceiling_check"]["clipped"])
        self.assertAlmostEqual(b["y_ch4_nm3_per_kg_vs"], ceiling, places=12)
        self.assertAlmostEqual(b["y_biogas_nm3_per_kg_vs"], ceiling / 0.6, places=12)
        self.assertLessEqual(b["interval_low"], b["y_biogas_nm3_per_kg_vs"])

    def test_feedstock_not_in_bundle_is_422(self):
        self.use_model_dir(with_bundle=True)
        r = client.post("/ml/yield", json={**BODY, "feedstock": "mixed"})
        self.assertEqual(r.status_code, 422)
        self.assertIn("food", r.json()["detail"])


class TestModelsEndpoint(_ModelDirCase):
    def test_no_bundle(self):
        self.use_model_dir(with_bundle=False)
        r = client.get("/ml/models")
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertEqual(b["status"], "no_trained_model")
        self.assertEqual(b["models"], [])

    def test_with_bundle(self):
        self.use_model_dir(with_bundle=True)
        r = client.get("/ml/models")
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertEqual(b["status"], "ok")
        self.assertEqual(len(b["models"]), 1)
        self.assertTrue(b["models"][0]["synthetic"])
        self.assertEqual(b["models"][0]["feedstocks_seen"], ["food", "manure"])


if __name__ == "__main__":
    unittest.main()