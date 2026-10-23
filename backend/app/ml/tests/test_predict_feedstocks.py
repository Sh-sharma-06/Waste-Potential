"""Contract tests for predict.py: feedstock names and the required ch4_fraction."""

import unittest

import app.ml.yield_model.predict as predict_module
from app.ml.yield_model.feedstocks import FEEDSTOCK_NAMES
from app.ml.yield_model.predict import ILLUSTRATIVE_Y0_NM3_PER_KG_VS, estimate_illustrative_l1

OPERATING = {"hrt_days": 30.0, "temperature_c": 37.0}


class TestPredictContract(unittest.TestCase):
    def test_illustrative_table_matches_feedstock_contract(self):
        self.assertEqual(set(ILLUSTRATIVE_Y0_NM3_PER_KG_VS), set(FEEDSTOCK_NAMES))

    def test_every_contract_name_works_in_illustrative(self):
        for name in FEEDSTOCK_NAMES:
            with self.subTest(feedstock=name):
                res = estimate_illustrative_l1(name, OPERATING, ch4_fraction=0.6)
                self.assertEqual(res.model_version, "illustrative-l1-NOT-VALIDATED")

    def test_ch4_fraction_is_required(self):
        with self.assertRaises(TypeError):
            estimate_illustrative_l1("food", OPERATING)

    def test_no_hidden_default_fraction(self):
        self.assertFalse(hasattr(predict_module, "DEFAULT_CH4_FRACTION"))


if __name__ == "__main__":
    unittest.main()