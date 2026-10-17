"""Tests for core_engine.pathways: feedstock validation and feasibility checks."""
import dataclasses
import unittest

from app.core_engine.pathways.feedstock import Feedstock
from app.core_engine.pathways.feasibility import PATHWAYS, Feasibility, check_pathway


# ---------------------------------------------------------------------------
# Helpers — pre-built valid feedstocks
# ---------------------------------------------------------------------------

def _fs(**overrides) -> Feedstock:
    """Return a valid base Feedstock with optional field overrides."""
    base = dict(
        total_mass_kg_d=1000.0,
        organic_fraction=0.50,
        plastic_fraction=0.20,
        paper_fraction=0.15,
        other_fraction=0.15,
        moisture_fraction=0.55,
        ash_fraction_dry=0.05,
        lhv_dry_mj_per_kg=12.0,
        contamination_pct=5.0,
    )
    base.update(overrides)
    return Feedstock(**base)


def _fs_dry(**overrides) -> Feedstock:
    """Low-moisture feedstock suited to thermal pathways."""
    base = dict(
        total_mass_kg_d=500.0,
        organic_fraction=0.10,
        plastic_fraction=0.45,
        paper_fraction=0.25,
        other_fraction=0.20,
        moisture_fraction=0.15,
        ash_fraction_dry=0.08,
        lhv_dry_mj_per_kg=18.0,
        contamination_pct=3.0,
    )
    base.update(overrides)
    return Feedstock(**base)


# ---------------------------------------------------------------------------
# Feedstock validation tests
# ---------------------------------------------------------------------------

class TestFeedstockValidation(unittest.TestCase):

    def test_valid_construction(self):
        fs = _fs()
        self.assertEqual(fs.total_mass_kg_d, 1000.0)

    def test_fractions_must_sum_to_one(self):
        with self.assertRaises(ValueError):
            _fs(organic_fraction=0.60)  # sum > 1

    def test_fractions_sum_too_low_raises(self):
        with self.assertRaises(ValueError):
            _fs(organic_fraction=0.30)  # sum < 1

    def test_negative_total_mass_raises(self):
        with self.assertRaises(ValueError):
            _fs(total_mass_kg_d=-1.0)

    def test_negative_lhv_raises(self):
        with self.assertRaises(ValueError):
            _fs(lhv_dry_mj_per_kg=-0.1)

    def test_fraction_above_one_raises(self):
        with self.assertRaises(ValueError):
            Feedstock(
                total_mass_kg_d=100.0,
                organic_fraction=1.1,
                plastic_fraction=0.0,
                paper_fraction=0.0,
                other_fraction=0.0,
                moisture_fraction=0.5,
                ash_fraction_dry=0.05,
                lhv_dry_mj_per_kg=10.0,
                contamination_pct=5.0,
            )

    def test_fraction_negative_raises(self):
        with self.assertRaises(ValueError):
            _fs(moisture_fraction=-0.01)

    def test_contamination_above_100_raises(self):
        with self.assertRaises(ValueError):
            _fs(contamination_pct=101.0)

    def test_contamination_negative_raises(self):
        with self.assertRaises(ValueError):
            _fs(contamination_pct=-1.0)

    def test_zero_total_mass_allowed(self):
        fs = _fs(total_mass_kg_d=0.0)
        self.assertEqual(fs.total_mass_kg_d, 0.0)

    def test_frozen(self):
        fs = _fs()
        with self.assertRaises((dataclasses.FrozenInstanceError, TypeError, AttributeError)):
            fs.total_mass_kg_d = 999.0  # type: ignore[misc]


# ---------------------------------------------------------------------------
# lhv_wet tests
# ---------------------------------------------------------------------------

class TestLhvWet(unittest.TestCase):

    def test_zero_moisture_returns_dry_value(self):
        fs = _fs(moisture_fraction=0.0)
        self.assertAlmostEqual(fs.lhv_wet_mj_per_kg(), fs.lhv_dry_mj_per_kg, places=10)

    def test_formula_at_known_values(self):
        # lhv_dry=12, w=0.55 → 12*(1-0.55) - 2.44*0.55 = 5.4 - 1.342 = 4.058
        fs = _fs(moisture_fraction=0.55, lhv_dry_mj_per_kg=12.0)
        expected = 12.0 * 0.45 - 2.44 * 0.55
        self.assertAlmostEqual(fs.lhv_wet_mj_per_kg(), expected, places=10)

    def test_drops_as_moisture_rises(self):
        lo = _fs(moisture_fraction=0.10, lhv_dry_mj_per_kg=15.0)
        hi = _fs(moisture_fraction=0.50, lhv_dry_mj_per_kg=15.0)
        self.assertGreater(lo.lhv_wet_mj_per_kg(), hi.lhv_wet_mj_per_kg())

    def test_floored_at_zero(self):
        # Very wet, low dry LHV → formula goes negative
        fs = _fs(
            organic_fraction=0.10,
            plastic_fraction=0.10,
            paper_fraction=0.10,
            other_fraction=0.70,
            moisture_fraction=0.95,
            lhv_dry_mj_per_kg=1.0,
        )
        self.assertEqual(fs.lhv_wet_mj_per_kg(), 0.0)

    def test_lhv_wet_never_negative(self):
        for w in (0.0, 0.25, 0.50, 0.75, 1.0):
            fs = _fs(
                organic_fraction=0.25,
                plastic_fraction=0.25,
                paper_fraction=0.25,
                other_fraction=0.25,
                moisture_fraction=w,
                lhv_dry_mj_per_kg=5.0,
            )
            self.assertGreaterEqual(fs.lhv_wet_mj_per_kg(), 0.0)


# ---------------------------------------------------------------------------
# PATHWAYS constant
# ---------------------------------------------------------------------------

class TestPathwaysConstant(unittest.TestCase):

    def test_contains_five_entries(self):
        self.assertEqual(len(PATHWAYS), 5)

    def test_expected_names(self):
        expected = {
            "anaerobic_digestion", "composting", "incineration",
            "gasification", "pyrolysis",
        }
        self.assertEqual(set(PATHWAYS), expected)


# ---------------------------------------------------------------------------
# check_pathway — unknown name
# ---------------------------------------------------------------------------

class TestUnknownPathway(unittest.TestCase):

    def test_unknown_name_raises_value_error(self):
        with self.assertRaises(ValueError):
            check_pathway("landfill", _fs())

    def test_empty_name_raises_value_error(self):
        with self.assertRaises(ValueError):
            check_pathway("", _fs())


# ---------------------------------------------------------------------------
# Feasibility result structure
# ---------------------------------------------------------------------------

class TestFeasibilityStructure(unittest.TestCase):

    def test_returns_feasibility_instance(self):
        result = check_pathway("incineration", _fs_dry())
        self.assertIsInstance(result, Feasibility)

    def test_feasibility_is_frozen(self):
        result = check_pathway("incineration", _fs_dry())
        with self.assertRaises((dataclasses.FrozenInstanceError, TypeError, AttributeError)):
            result.feasible = False  # type: ignore[misc]

    def test_feasible_result_has_empty_reasons(self):
        result = check_pathway("anaerobic_digestion", _fs())
        if result.feasible:
            self.assertEqual(result.reasons, [])

    def test_infeasible_result_has_non_empty_reasons(self):
        # Low organic + low moisture → infeasible AD
        fs = _fs(
            organic_fraction=0.20,
            plastic_fraction=0.30,
            paper_fraction=0.25,
            other_fraction=0.25,
            moisture_fraction=0.30,
        )
        result = check_pathway("anaerobic_digestion", fs)
        self.assertFalse(result.feasible)
        self.assertTrue(len(result.reasons) > 0)
        for r in result.reasons:
            self.assertIsInstance(r, str)
            self.assertTrue(len(r) > 0)

    def test_basis_is_string(self):
        result = check_pathway("composting", _fs())
        self.assertIsInstance(result.basis, str)

    def test_pathway_name_echoed(self):
        result = check_pathway("pyrolysis", _fs_dry())
        self.assertEqual(result.pathway, "pyrolysis")


# ---------------------------------------------------------------------------
# anaerobic_digestion
# ---------------------------------------------------------------------------

class TestAnaerobicDigestion(unittest.TestCase):
    _NAME = "anaerobic_digestion"

    def test_feasible_example(self):
        # organic >= 0.30, moisture >= 0.50
        fs = _fs(organic_fraction=0.50, moisture_fraction=0.60,
                 plastic_fraction=0.20, paper_fraction=0.10, other_fraction=0.20)
        result = check_pathway(self._NAME, fs)
        self.assertTrue(result.feasible)
        self.assertEqual(result.reasons, [])

    def test_infeasible_low_organic(self):
        fs = _fs(organic_fraction=0.20, plastic_fraction=0.40,
                 paper_fraction=0.20, other_fraction=0.20, moisture_fraction=0.55)
        result = check_pathway(self._NAME, fs)
        self.assertFalse(result.feasible)
        self.assertTrue(any("organic" in r for r in result.reasons))

    def test_infeasible_low_moisture(self):
        fs = _fs(organic_fraction=0.50, moisture_fraction=0.30,
                 plastic_fraction=0.20, paper_fraction=0.10, other_fraction=0.20)
        result = check_pathway(self._NAME, fs)
        self.assertFalse(result.feasible)
        self.assertTrue(any("moisture" in r for r in result.reasons))

    def test_boundary_organic_exactly_at_limit_is_feasible(self):
        # organic_fraction == 0.30 exactly → feasible
        fs = _fs(organic_fraction=0.30, plastic_fraction=0.30,
                 paper_fraction=0.20, other_fraction=0.20, moisture_fraction=0.60)
        result = check_pathway(self._NAME, fs)
        self.assertTrue(result.feasible)

    def test_boundary_moisture_exactly_at_limit_is_feasible(self):
        fs = _fs(organic_fraction=0.50, moisture_fraction=0.50,
                 plastic_fraction=0.20, paper_fraction=0.10, other_fraction=0.20)
        result = check_pathway(self._NAME, fs)
        self.assertTrue(result.feasible)

    def test_reasons_text_non_empty_on_infeasible(self):
        fs = _fs(organic_fraction=0.10, plastic_fraction=0.40,
                 paper_fraction=0.25, other_fraction=0.25, moisture_fraction=0.20)
        result = check_pathway(self._NAME, fs)
        self.assertFalse(result.feasible)
        for r in result.reasons:
            self.assertGreater(len(r), 0)


# ---------------------------------------------------------------------------
# composting
# ---------------------------------------------------------------------------

class TestComposting(unittest.TestCase):
    _NAME = "composting"

    def test_feasible_example(self):
        fs = _fs(organic_fraction=0.55, plastic_fraction=0.15,
                 paper_fraction=0.15, other_fraction=0.15,
                 contamination_pct=5.0)
        result = check_pathway(self._NAME, fs)
        self.assertTrue(result.feasible)

    def test_infeasible_low_organic(self):
        fs = _fs(organic_fraction=0.30, plastic_fraction=0.30,
                 paper_fraction=0.20, other_fraction=0.20,
                 contamination_pct=5.0)
        result = check_pathway(self._NAME, fs)
        self.assertFalse(result.feasible)
        self.assertTrue(any("organic" in r for r in result.reasons))

    def test_infeasible_high_contamination(self):
        fs = _fs(organic_fraction=0.50, plastic_fraction=0.20,
                 paper_fraction=0.15, other_fraction=0.15,
                 contamination_pct=20.0)
        result = check_pathway(self._NAME, fs)
        self.assertFalse(result.feasible)
        self.assertTrue(any("contamination" in r for r in result.reasons))

    def test_boundary_organic_exactly_at_limit_is_feasible(self):
        fs = _fs(organic_fraction=0.40, plastic_fraction=0.30,
                 paper_fraction=0.15, other_fraction=0.15,
                 contamination_pct=5.0)
        result = check_pathway(self._NAME, fs)
        self.assertTrue(result.feasible)

    def test_boundary_contamination_exactly_at_limit_is_feasible(self):
        fs = _fs(organic_fraction=0.50, plastic_fraction=0.20,
                 paper_fraction=0.15, other_fraction=0.15,
                 contamination_pct=15.0)
        result = check_pathway(self._NAME, fs)
        self.assertTrue(result.feasible)

    def test_reasons_text_non_empty_on_infeasible(self):
        fs = _fs(organic_fraction=0.20, plastic_fraction=0.40,
                 paper_fraction=0.20, other_fraction=0.20,
                 contamination_pct=25.0)
        result = check_pathway(self._NAME, fs)
        self.assertFalse(result.feasible)
        for r in result.reasons:
            self.assertGreater(len(r), 0)


# ---------------------------------------------------------------------------
# incineration
# ---------------------------------------------------------------------------

class TestIncineration(unittest.TestCase):
    _NAME = "incineration"

    def test_feasible_example(self):
        # lhv_wet = 18*(1-0.15) - 2.44*0.15 = 15.3 - 0.366 = 14.934 > 7.0
        result = check_pathway(self._NAME, _fs_dry())
        self.assertTrue(result.feasible)

    def test_infeasible_low_lhv_wet(self):
        # lhv_dry=3, moisture=0.80 → lhv_wet = 3*0.2 - 2.44*0.8 = 0.6-1.952 < 0 → 0 < 7
        fs = _fs(
            organic_fraction=0.10,
            plastic_fraction=0.10,
            paper_fraction=0.10,
            other_fraction=0.70,
            moisture_fraction=0.80,
            lhv_dry_mj_per_kg=3.0,
        )
        result = check_pathway(self._NAME, fs)
        self.assertFalse(result.feasible)
        self.assertTrue(any("lhv_wet" in r for r in result.reasons))

    def test_boundary_lhv_wet_exactly_at_limit_is_feasible(self):
        # Solve: lhv_dry*(1-w) - 2.44*w = 7.0 with w=0.20
        # lhv_dry*0.80 - 0.488 = 7.0 → lhv_dry = 7.488/0.80 = 9.36
        fs = _fs(
            organic_fraction=0.20,
            plastic_fraction=0.30,
            paper_fraction=0.25,
            other_fraction=0.25,
            moisture_fraction=0.20,
            lhv_dry_mj_per_kg=9.36,
        )
        result = check_pathway(self._NAME, fs)
        self.assertTrue(result.feasible)

    def test_reasons_text_non_empty_on_infeasible(self):
        fs = _fs(moisture_fraction=0.90, lhv_dry_mj_per_kg=2.0,
                 organic_fraction=0.25, plastic_fraction=0.25,
                 paper_fraction=0.25, other_fraction=0.25)
        result = check_pathway(self._NAME, fs)
        self.assertFalse(result.feasible)
        for r in result.reasons:
            self.assertGreater(len(r), 0)


# ---------------------------------------------------------------------------
# gasification
# ---------------------------------------------------------------------------

class TestGasification(unittest.TestCase):
    _NAME = "gasification"

    def test_feasible_example(self):
        # NOTE: limit changed 0.30→0.15; moisture=0.15 <= 0.15, lhv_wet=18*(0.85)-2.44*0.15=14.934 >= 10
        result = check_pathway(self._NAME, _fs_dry())
        self.assertTrue(result.feasible)

    def test_infeasible_high_moisture(self):
        fs = _fs(moisture_fraction=0.65, lhv_dry_mj_per_kg=15.0)
        result = check_pathway(self._NAME, fs)
        self.assertFalse(result.feasible)
        self.assertTrue(any("moisture" in r for r in result.reasons))

    def test_infeasible_low_lhv_wet(self):
        # NOTE: limit changed 0.30→0.15; use moisture=0.10 (under 0.15 limit) so only lhv_wet fails
        # lhv_wet=5*(1-0.10)-2.44*0.10=4.5-0.244=4.256 < 10
        fs = _fs_dry(
            moisture_fraction=0.10,
            lhv_dry_mj_per_kg=5.0,
            organic_fraction=0.10,
            plastic_fraction=0.45,
            paper_fraction=0.25,
            other_fraction=0.20,
        )
        result = check_pathway(self._NAME, fs)
        self.assertFalse(result.feasible)
        self.assertTrue(any("lhv_wet" in r for r in result.reasons))

    def test_boundary_moisture_exactly_at_limit_is_feasible(self):
        # NOTE: limit changed 0.30→0.15; moisture=0.15 exactly, need lhv_wet >= 10
        # lhv_wet=16*(0.85)-2.44*0.15=13.6-0.366=13.234 >= 10 → feasible
        fs = _fs_dry(
            moisture_fraction=0.15,
            lhv_dry_mj_per_kg=16.0,
            organic_fraction=0.10,
            plastic_fraction=0.45,
            paper_fraction=0.25,
            other_fraction=0.20,
        )
        result = check_pathway(self._NAME, fs)
        self.assertTrue(result.feasible)

    def test_reasons_text_non_empty_on_infeasible(self):
        fs = _fs(moisture_fraction=0.70, lhv_dry_mj_per_kg=2.0)
        result = check_pathway(self._NAME, fs)
        self.assertFalse(result.feasible)
        for r in result.reasons:
            self.assertGreater(len(r), 0)

    # --- boundary tests added for blueprint limits (gasification max moisture 0.15) ---

    def test_boundary_moisture_exactly_0_15_is_feasible(self):
        """Gasification: moisture exactly 0.15 must be feasible (blueprint limit)."""
        # NOTE: new limit 0.15 (was 0.30)
        fs = _fs_dry(
            moisture_fraction=0.15,
            lhv_dry_mj_per_kg=16.0,
            organic_fraction=0.10,
            plastic_fraction=0.45,
            paper_fraction=0.25,
            other_fraction=0.20,
        )
        result = check_pathway(self._NAME, fs)
        self.assertTrue(result.feasible)
        self.assertNotIn("moisture", " ".join(result.reasons))

    def test_boundary_moisture_0_16_is_infeasible(self):
        """Gasification: moisture 0.16 must be infeasible (one above blueprint limit)."""
        # NOTE: new limit 0.15 (was 0.30); 0.16 > 0.15 → fails
        # fractions: 0.10+0.44+0.25+0.21=1.00
        fs = _fs_dry(
            moisture_fraction=0.16,
            lhv_dry_mj_per_kg=16.0,
            organic_fraction=0.10,
            plastic_fraction=0.44,
            paper_fraction=0.25,
            other_fraction=0.21,
        )
        result = check_pathway(self._NAME, fs)
        self.assertFalse(result.feasible)
        self.assertTrue(any("moisture" in r for r in result.reasons))
        self.assertTrue(any("0.15 limit" in r for r in result.reasons))


# ---------------------------------------------------------------------------
# pyrolysis
# ---------------------------------------------------------------------------

class TestPyrolysis(unittest.TestCase):
    _NAME = "pyrolysis"

    def test_feasible_example(self):
        # NOTE: limit changed 0.20→0.10; _fs_dry() uses moisture=0.15 which is > 0.10
        # → use explicit moisture=0.10 so this feedstock is feasible
        fs = _fs_dry(
            moisture_fraction=0.10,
            organic_fraction=0.10,
            plastic_fraction=0.45,
            paper_fraction=0.25,
            other_fraction=0.20,
        )
        result = check_pathway(self._NAME, fs)
        self.assertTrue(result.feasible)

    def test_infeasible_high_moisture(self):
        # NOTE: limit changed 0.20→0.10; moisture=0.25 > 0.10 → still infeasible
        fs = _fs_dry(
            moisture_fraction=0.25,
            organic_fraction=0.10,
            plastic_fraction=0.45,
            paper_fraction=0.25,
            other_fraction=0.20,
        )
        result = check_pathway(self._NAME, fs)
        self.assertFalse(result.feasible)
        self.assertTrue(any("moisture" in r for r in result.reasons))

    def test_infeasible_low_plastic_paper(self):
        # moisture OK, but plastic+paper=0.05+0.05=0.10 < 0.40
        fs = Feedstock(
            total_mass_kg_d=500.0,
            organic_fraction=0.80,
            plastic_fraction=0.05,
            paper_fraction=0.05,
            other_fraction=0.10,
            moisture_fraction=0.10,
            ash_fraction_dry=0.05,
            lhv_dry_mj_per_kg=14.0,
            contamination_pct=2.0,
        )
        result = check_pathway(self._NAME, fs)
        self.assertFalse(result.feasible)
        self.assertTrue(any("plastic" in r for r in result.reasons))

    def test_boundary_moisture_exactly_at_limit_is_feasible(self):
        # NOTE: limit changed 0.20→0.10; moisture=0.10 exactly, plastic+paper >= 0.40
        fs = _fs_dry(
            moisture_fraction=0.10,
            organic_fraction=0.10,
            plastic_fraction=0.45,
            paper_fraction=0.25,
            other_fraction=0.20,
        )
        result = check_pathway(self._NAME, fs)
        self.assertTrue(result.feasible)

    def test_boundary_plastic_paper_exactly_at_limit_is_feasible(self):
        # plastic+paper = 0.40 exactly
        fs = Feedstock(
            total_mass_kg_d=500.0,
            organic_fraction=0.20,
            plastic_fraction=0.20,
            paper_fraction=0.20,
            other_fraction=0.40,
            moisture_fraction=0.10,
            ash_fraction_dry=0.05,
            lhv_dry_mj_per_kg=14.0,
            contamination_pct=2.0,
        )
        result = check_pathway(self._NAME, fs)
        self.assertTrue(result.feasible)

    def test_reasons_text_non_empty_on_infeasible(self):
        fs = Feedstock(
            total_mass_kg_d=300.0,
            organic_fraction=0.70,
            plastic_fraction=0.10,
            paper_fraction=0.10,
            other_fraction=0.10,
            moisture_fraction=0.50,
            ash_fraction_dry=0.05,
            lhv_dry_mj_per_kg=8.0,
            contamination_pct=3.0,
        )
        result = check_pathway(self._NAME, fs)
        self.assertFalse(result.feasible)
        for r in result.reasons:
            self.assertGreater(len(r), 0)

    # --- boundary tests added for blueprint limits (pyrolysis max moisture 0.10) ---

    def test_boundary_moisture_exactly_0_10_is_feasible(self):
        """Pyrolysis: moisture exactly 0.10 must be feasible (blueprint limit)."""
        # NOTE: new limit 0.10 (was 0.20)
        fs = _fs_dry(
            moisture_fraction=0.10,
            organic_fraction=0.10,
            plastic_fraction=0.45,
            paper_fraction=0.25,
            other_fraction=0.20,
        )
        result = check_pathway(self._NAME, fs)
        self.assertTrue(result.feasible)
        self.assertNotIn("moisture", " ".join(result.reasons))

    def test_boundary_moisture_0_11_is_infeasible(self):
        """Pyrolysis: moisture 0.11 must be infeasible (one above blueprint limit)."""
        # NOTE: new limit 0.10 (was 0.20); 0.11 > 0.10 → fails
        fs = _fs_dry(
            moisture_fraction=0.11,
            organic_fraction=0.10,
            plastic_fraction=0.45,
            paper_fraction=0.25,
            other_fraction=0.20,
        )
        result = check_pathway(self._NAME, fs)
        self.assertFalse(result.feasible)
        self.assertTrue(any("moisture" in r for r in result.reasons))
        self.assertTrue(any("0.1 limit" in r for r in result.reasons))


if __name__ == "__main__":
    unittest.main()
