"""
tests/test_schemas.py — Pydantic schema smoke-tests for simulation.py.

Required by the B1 spec:
  - SimResults(**simulate(Params())) validates without error.
  - Unknown extra field is rejected.
  - Every SimResults field name ends in a recognised unit suffix OR is on
    an explicit allowlist of dimensionless/flag/metadata names defined here.

All test classes use unittest.TestCase.
"""

import unittest

from pydantic import ValidationError

from app.core_engine.engine import simulate
from app.core_engine.montecarlo import run_mc
from app.core_engine.params import Params
from app.schemas.simulation import (
    SimRequest,
    SimResults,
    UncertaintyRequest,
    UncertaintyResult,
)


# ---------------------------------------------------------------------------
# Allowlist & suffix constants — single source of truth for the suffix test
# ---------------------------------------------------------------------------

# Recognised unit suffixes that may appear at the end of a SimResults field name.
UNIT_SUFFIXES: tuple = (
    "_kg_d",        # kilograms per day
    "_nm3_d",       # normal cubic metres per day (0 °C, 1 atm)
    "_kwh_d",       # kilowatt-hours per day
    "_m3",          # cubic metres (volume)
    "_c",           # degrees Celsius (temperature)
    "_days",        # days (time)
    "_kwh",         # kilowatt-hours (standalone energy)
    "_kg",          # kilograms (mass, not per day)
    "_per_kg_vs",   # Nm³ per kg volatile solids
)

# Dimensionless / flag / metadata field names that need no unit suffix.
DIMENSIONLESS_ALLOWLIST: frozenset = frozenset({
    # ratios / fractions (0–1)
    "buswell_bound",        # theoretical CH4 yield ceiling [Nm³/kg VS] — ratio named by convention
    "vs_destruction",       # VS destruction fraction [–]
    # per-VS already covered by _per_kg_vs suffix, listed for explicitness
    "ch4_nm3_per_kg_vs",
    # mass balance — ends in _kg, covered by suffix, listed for explicitness
    "mass_residual_kg",
    # boolean flags
    "heat_deficit",
    # list fields
    "out_of_range_inputs",
    "warnings",
    # string metadata
    "status",
})


# ===========================================================================
# SimResults schema tests
# ===========================================================================

class TestSimResultsSchema(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.raw = simulate(Params())
        cls.sr = SimResults(**cls.raw)

    def test_validates_from_real_engine_output(self):
        """simulate(Params()) output must parse into SimResults without error."""
        self.assertIsInstance(self.sr, SimResults)

    def test_unknown_extra_field_rejected(self):
        """extra='forbid' must cause ValidationError for any unknown key."""
        bad = dict(self.raw)
        bad["__intruder__"] = 42.0
        with self.assertRaises(ValidationError):
            SimResults(**bad)

    def test_every_field_has_unit_suffix_or_is_allowlisted(self):
        """
        Enforce that SimResults stays self-documenting: every field name must
        carry a unit suffix from UNIT_SUFFIXES or appear in DIMENSIONLESS_ALLOWLIST.
        This is a schema-level contract, not a runtime check.
        """
        violations = []
        for name in SimResults.model_fields:
            if name in DIMENSIONLESS_ALLOWLIST:
                continue
            if any(name.endswith(s) for s in UNIT_SUFFIXES):
                continue
            violations.append(name)

        self.assertEqual(
            violations,
            [],
            msg=(
                f"SimResults field(s) have no recognised unit suffix and are "
                f"not in DIMENSIONLESS_ALLOWLIST: {violations}.\n"
                f"Either rename with a suffix or add to DIMENSIONLESS_ALLOWLIST."
            ),
        )

    def test_heat_deficit_is_bool(self):
        self.assertIsInstance(self.sr.heat_deficit, bool)

    def test_warnings_is_list_of_str(self):
        self.assertIsInstance(self.sr.warnings, list)
        for item in self.sr.warnings:
            self.assertIsInstance(item, str)

    def test_out_of_range_inputs_is_list(self):
        self.assertIsInstance(self.sr.out_of_range_inputs, list)

    def test_e_net_kwh_d_golden(self):
        """Golden value: default Params() -> e_net_kwh_d ≈ 76.74 kWh/d."""
        self.assertAlmostEqual(self.sr.e_net_kwh_d, 76.7406, delta=0.01)

    def test_biogas_nm3_d_golden(self):
        """Golden value: default Params() -> biogas_nm3_d ≈ 47.04 Nm³/d."""
        self.assertAlmostEqual(self.sr.biogas_nm3_d, 47.0448, delta=0.01)


# ===========================================================================
# SimRequest schema tests
# ===========================================================================

class TestSimRequestSchema(unittest.TestCase):

    def test_default_construction(self):
        req = SimRequest()
        self.assertEqual(req.process, "anaerobic_digestion")
        self.assertFalse(req.use_ml_yield)
        self.assertEqual(req.overrides, {})

    def test_waste_mass_zero_rejected(self):
        with self.assertRaises(ValidationError):
            SimRequest(waste_mass_kg_day=0.0)

    def test_waste_mass_positive_accepted(self):
        req = SimRequest(waste_mass_kg_day=500.0)
        self.assertEqual(req.waste_mass_kg_day, 500.0)

    def test_override_unknown_key_rejected(self):
        with self.assertRaises(ValidationError):
            SimRequest(overrides={"__not_a_field__": 1.0})

    def test_override_valid_params_key_accepted(self):
        req = SimRequest(overrides={"hrt_days": 20.0})
        self.assertEqual(req.overrides["hrt_days"], 20.0)

    def test_extra_field_rejected(self):
        with self.assertRaises(ValidationError):
            SimRequest(unknown_kwarg=True)


# ===========================================================================
# UncertaintyRequest / UncertaintyResult
# ===========================================================================

class TestUncertaintySchemas(unittest.TestCase):

    def test_uncertainty_request_defaults(self):
        req = UncertaintyRequest()
        self.assertEqual(req.n, 2000)
        self.assertEqual(req.seed, 42)
        self.assertIsNone(req.distribution_overrides)

    def test_uncertainty_request_n_too_low_rejected(self):
        with self.assertRaises(ValidationError):
            UncertaintyRequest(n=5)

    def test_uncertainty_request_n_too_high_rejected(self):
        with self.assertRaises(ValidationError):
            UncertaintyRequest(n=99999)

    def test_uncertainty_request_distribution_overrides_accepted(self):
        req = UncertaintyRequest(
            n=100,
            distribution_overrides={
                "hrt_days": {"kind": "uniform", "args": [20.0, 40.0]}
            },
        )
        self.assertIn("hrt_days", req.distribution_overrides)

    def test_uncertainty_result_validates_from_run_mc(self):
        """UncertaintyResult(**run_mc(Params(), n=200)) must not raise."""
        raw = run_mc(Params(), n=200, seed=42)
        ur = UncertaintyResult(**raw)
        self.assertIsInstance(ur, UncertaintyResult)
        self.assertLessEqual(ur.p2_5, ur.median)
        self.assertLessEqual(ur.median, ur.p97_5)

    def test_uncertainty_result_extra_field_rejected(self):
        raw = run_mc(Params(), n=200, seed=42)
        raw["__intruder__"] = "bad"
        with self.assertRaises(ValidationError):
            UncertaintyResult(**raw)


if __name__ == "__main__":
    unittest.main(verbosity=2)
