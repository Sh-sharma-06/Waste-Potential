"""Tests for ceiling_with_lignin (synthetic example values, not real data)."""

import unittest

from app.core_engine.engine import BUSWELL, buswell_bound
from app.ml.yield_model.ceiling import ceiling_with_lignin


class TestCeilingWithLignin(unittest.TestCase):
    def test_equals_explicit_formula(self):
        c, p, lip, lig = 0.5, 0.2, 0.1, 0.2
        expected = c * BUSWELL["carb"] + p * BUSWELL["protein"] + lip * BUSWELL["lipid"]
        self.assertAlmostEqual(ceiling_with_lignin(c, p, lip, lig), expected, delta=1e-12)

    def test_zero_lignin_matches_buswell_bound(self):
        c, p, lip = 0.6, 0.3, 0.1
        self.assertAlmostEqual(
            ceiling_with_lignin(c, p, lip), buswell_bound((c, p, lip)), delta=1e-12
        )

    def test_lignin_lowers_the_ceiling(self):
        self.assertLess(
            ceiling_with_lignin(0.5, 0.2, 0.1, 0.2),
            ceiling_with_lignin(0.625, 0.25, 0.125, 0.0),
        )

    def test_lignin_out_of_range(self):
        with self.assertRaises(ValueError):
            ceiling_with_lignin(0.5, 0.3, 0.3, -0.1)
        with self.assertRaises(ValueError):
            ceiling_with_lignin(0.0, 0.0, 0.0, 1.0)

    def test_shares_must_sum_to_one(self):
        with self.assertRaises(ValueError):
            ceiling_with_lignin(0.5, 0.2, 0.1, 0.1)

    def test_negative_share_rejected(self):
        # Sums to 1.0 and lignin is valid, so only the negative share can trigger the error.
        with self.assertRaises(ValueError):
            ceiling_with_lignin(1.1, -0.1, 0.0, 0.0)

    def test_degradable_part_zero_rejected(self):
        with self.assertRaises(ValueError):
            ceiling_with_lignin(0.0, 0.0, 0.0, 0.9999999)


if __name__ == "__main__":
    unittest.main()