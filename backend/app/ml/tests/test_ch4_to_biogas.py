"""Tests for ch4_to_biogas (synthetic example values, not real data)."""

import unittest

from app.ml.yield_model.units import ch4_to_biogas, convert_to_vs_yield


class TestCh4ToBiogas(unittest.TestCase):
    def test_basic_conversion(self):
        self.assertAlmostEqual(ch4_to_biogas(0.30, 0.60), 0.50, places=12)

    def test_fraction_of_one_is_identity(self):
        self.assertAlmostEqual(ch4_to_biogas(0.42, 1.0), 0.42, places=12)

    def test_invalid_fraction_raises(self):
        for bad in (0.0, -0.1, 1.01, float("nan")):
            with self.assertRaises(ValueError):
                ch4_to_biogas(0.3, bad)

    def test_invalid_yield_raises(self):
        for bad in (-0.1, float("nan")):
            with self.assertRaises(ValueError):
                ch4_to_biogas(bad, 0.6)

    def test_convert_to_vs_yield_uses_same_conversion(self):
        out = convert_to_vs_yield(0.30, "per_kg_vs", ch4_fraction=0.60, gas_type="ch4")
        self.assertAlmostEqual(out.y_biogas_nm3_per_kg_vs, ch4_to_biogas(0.30, 0.60), places=12)


if __name__ == "__main__":
    unittest.main()