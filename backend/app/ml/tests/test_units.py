"""Unit tests for yield_model/units.py."""

import unittest
from app.ml.yield_model.units import convert_to_vs_yield, ConvertedYield


class TestUnits(unittest.TestCase):
    """Test suite for yield basis conversions."""

    def test_per_vs_passthrough(self):
        """Yield already on VS basis should pass through unchanged."""
        res = convert_to_vs_yield(0.55, from_basis="per_kg_vs", ch4_fraction=0.60)
        self.assertAlmostEqual(res.y_biogas_nm3_per_kg_vs, 0.55, places=6)
        self.assertAlmostEqual(res.y_ch4_nm3_per_kg_vs, 0.33, places=6)
        self.assertEqual(res.basis, "per kg VS")

    def test_per_ts_conversion(self):
        """Yield on TS basis should be divided by vs_of_ts."""
        # 0.55 Nm3/kg VS * 0.88 kg VS/kg TS = 0.484 Nm3/kg TS
        res = convert_to_vs_yield(0.484, from_basis="per_kg_ts", vs_of_ts=0.88, ch4_fraction=0.60)
        self.assertAlmostEqual(res.y_biogas_nm3_per_kg_vs, 0.55, places=6)
        self.assertAlmostEqual(res.y_ch4_nm3_per_kg_vs, 0.33, places=6)

    def test_per_fresh_conversion(self):
        """Yield on fresh basis should be divided by (ts_fraction * vs_of_ts)."""
        # fresh = 0.55 * (0.27 * 0.88) = 0.13068
        res = convert_to_vs_yield(
            0.13068,
            from_basis="per_kg_fresh",
            ts_fraction=0.27,
            vs_of_ts=0.88,
            ch4_fraction=0.60
        )
        self.assertAlmostEqual(res.y_biogas_nm3_per_kg_vs, 0.55, places=5)
        self.assertAlmostEqual(res.y_ch4_nm3_per_kg_vs, 0.33, places=5)

    def test_ch4_gas_type(self):
        """When input is CH4 yield, biogas should be calculated as ch4 / ch4_fraction."""
        res = convert_to_vs_yield(0.33, from_basis="per_kg_vs", ch4_fraction=0.60, gas_type="ch4")
        self.assertAlmostEqual(res.y_ch4_nm3_per_kg_vs, 0.33, places=6)
        self.assertAlmostEqual(res.y_biogas_nm3_per_kg_vs, 0.55, places=6)

    def test_negative_yield_raises(self):
        """Negative yields must raise ValueError."""
        with self.assertRaises(ValueError):
            convert_to_vs_yield(-0.1, from_basis="per_kg_vs")

    def test_missing_fractions_raise(self):
        """Missing required fractions must raise ValueError."""
        with self.assertRaises(ValueError):
            convert_to_vs_yield(0.5, from_basis="per_kg_ts")  # missing vs_of_ts

        with self.assertRaises(ValueError):
            convert_to_vs_yield(0.5, from_basis="per_kg_fresh", ts_fraction=0.25)  # missing vs_of_ts

        with self.assertRaises(ValueError):
            convert_to_vs_yield(0.5, from_basis="per_kg_fresh", vs_of_ts=0.8)  # missing ts_fraction

    def test_invalid_fraction_ranges_raise(self):
        """Fractions <= 0 or > 1 must raise ValueError."""
        with self.assertRaises(ValueError):
            convert_to_vs_yield(0.5, from_basis="per_kg_ts", vs_of_ts=0.0)

        with self.assertRaises(ValueError):
            convert_to_vs_yield(0.5, from_basis="per_kg_ts", vs_of_ts=1.5)

        with self.assertRaises(ValueError):
            convert_to_vs_yield(0.5, from_basis="per_kg_fresh", ts_fraction=-0.1, vs_of_ts=0.8)

        with self.assertRaises(ValueError):
            convert_to_vs_yield(0.5, from_basis="per_kg_vs", ch4_fraction=0.0)

    def test_unrecognized_options_raise(self):
        """Unknown basis or gas_type must raise ValueError."""
        with self.assertRaises(ValueError):
            convert_to_vs_yield(0.5, from_basis="unknown_basis")

        with self.assertRaises(ValueError):
            convert_to_vs_yield(0.5, from_basis="per_kg_vs", gas_type="hydrogen")


if __name__ == "__main__":
    unittest.main()
