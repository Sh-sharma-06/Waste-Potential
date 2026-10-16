"""
Tests for backend/app/schemas/simulation.py

Coverage:
  - SimResults(**simulate(Params())) validates without error.
  - Unknown extra fields are rejected (extra="forbid").
  - SimRequest.overrides: bad key rejected, good key (hrt_days) accepted.
  - waste_mass_kg_day=0 rejected (gt=0 constraint).
  - UncertaintyResult(**run_mc(Params(), n=200)) validates.
  - Every SimResults field name ends in an expected unit suffix OR is in the
    explicit allowlist of non-suffixed names.
  - SimResponse round-trips correctly.
  - ParameterEntryModel validates from real CSV row.
  - UncertaintyRequest n/seed defaults and boundary constraints.
  - RuleWarningModel validates from a RuleWarning dataclass.
"""

import unittest

from pydantic import ValidationError

from app.core_engine.engine import simulate
from app.core_engine.montecarlo import run_mc
from app.core_engine.params import Params
from app.core_engine.risk_rules import RuleWarning
from app.schemas.simulation import (
    ParameterEntryModel,
    RuleWarningModel,
    SimRequest,
    SimResponse,
    SimResults,
    UncertaintyRequest,
    UncertaintyResult,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sim_result_dict():
    return simulate(Params())


def _mc_result_dict():
    return run_mc(Params(), n=200, seed=42)


# ===========================================================================
# SimResults
# ===========================================================================

class TestSimResults(unittest.TestCase):

    def test_validates_from_real_engine_output(self):
        """SimResults(**simulate(Params())) must not raise."""
        r = _sim_result_dict()
        sr = SimResults(**r)
        self.assertIsInstance(sr, SimResults)

    def test_extra_field_rejected(self):
        r = _sim_result_dict()
        r["unexpected_field"] = 99.0
        with self.assertRaises(ValidationError):
            SimResults(**r)

    def test_heat_deficit_is_bool(self):
        sr = SimResults(**_sim_result_dict())
        self.assertIsInstance(sr.heat_deficit, bool)

    def test_warnings_is_list_of_str(self):
        sr = SimResults(**_sim_result_dict())
        self.assertIsInstance(sr.warnings, list)

    def test_field_names_have_unit_suffix_or_are_allowlisted(self):
        """
        Every field name must either end with a recognised unit suffix
        or appear in the explicit allowlist of non-suffixed names.
        This test enforces that the schema stays self-documenting.
        """
        # Recognised unit suffixes (end-of-name)
        UNIT_SUFFIXES = (
            "_kg_d",        # kg/day
            "_nm3_d",       # Nm³/day
            "_kwh_d",       # kWh/day
            "_m3",          # m³  (digester_m3)
            "_kg",          # kg  (mass_residual_kg)
            "_kwh",         # kWh (standalone energy — none currently, but future-proof)
            "_per_kg_vs",   # Nm³/kg VS  (ch4_nm3_per_kg_vs)
        )
        # Non-suffixed names that are explicitly allowed
        ALLOWLIST = {
            "buswell_bound",        # dimensionless Nm³/kg VS ratio already named
            "vs_destruction",       # fraction (0-1)
            "ch4_nm3_per_kg_vs",    # ends in _per_kg_vs — covered above, also listed for clarity
            "mass_residual_kg",     # ends in _kg — covered above
            "heat_deficit",         # bool flag
            "out_of_range_inputs",  # list of strings
            "warnings",             # list of strings
            "status",               # str
        }

        import dataclasses
        from app.schemas.simulation import SimResults as _SR

        for field in dataclasses.fields(_SR.__pydantic_fields__) if False else []:
            pass  # not used; we iterate model_fields instead

        failures = []
        for name in SimResults.model_fields:
            if name in ALLOWLIST:
                continue
            if any(name.endswith(suffix) for suffix in UNIT_SUFFIXES):
                continue
            failures.append(name)

        self.assertEqual(
            failures, [],
            msg=(
                f"SimResults field(s) lack a unit suffix and are not in ALLOWLIST: "
                f"{failures}. Add them to ALLOWLIST or rename with a unit suffix."
            ),
        )


# ===========================================================================
# SimRequest
# ===========================================================================

class TestSimRequest(unittest.TestCase):

    def test_default_construction(self):
        req = SimRequest()
        self.assertEqual(req.process, "anaerobic_digestion")
        self.assertEqual(req.overrides, {})
        self.assertFalse(req.use_ml_yield)

    def test_waste_mass_zero_rejected(self):
        with self.assertRaises(ValidationError):
            SimRequest(waste_mass_kg_day=0.0)

    def test_waste_mass_negative_rejected(self):
        with self.assertRaises(ValidationError):
            SimRequest(waste_mass_kg_day=-100.0)

    def test_waste_mass_over_limit_rejected(self):
        with self.assertRaises(ValidationError):
            SimRequest(waste_mass_kg_day=2e6)

    def test_waste_mass_valid(self):
        req = SimRequest(waste_mass_kg_day=1000.0)
        self.assertEqual(req.waste_mass_kg_day, 1000.0)

    def test_override_bad_key_rejected(self):
        with self.assertRaises(ValidationError, msg="bad key should be rejected"):
            SimRequest(overrides={"not_a_params_field": 1.0})

    def test_override_good_key_accepted(self):
        req = SimRequest(overrides={"hrt_days": 25.0})
        self.assertEqual(req.overrides["hrt_days"], 25.0)

    def test_override_multiple_good_keys_accepted(self):
        req = SimRequest(overrides={"hrt_days": 25.0, "availability": 0.85})
        self.assertEqual(len(req.overrides), 2)

    def test_override_mixed_good_and_bad_rejected(self):
        with self.assertRaises(ValidationError):
            SimRequest(overrides={"hrt_days": 25.0, "bad_field": 0.5})

    def test_organic_fraction_out_of_range_rejected(self):
        with self.assertRaises(ValidationError):
            SimRequest(organic_fraction=1.5)

    def test_extra_field_rejected(self):
        with self.assertRaises(ValidationError):
            SimRequest(unknown_extra=True)


# ===========================================================================
# RuleWarningModel
# ===========================================================================

class TestRuleWarningModel(unittest.TestCase):

    def test_validates_from_rule_warning_dataclass(self):
        rw = RuleWarning(
            code="NEG_NET", severity="warning",
            stage="electricity generation",
            message="Net electricity is zero.",
            basis="engine_rule",
        )
        import dataclasses
        m = RuleWarningModel(**dataclasses.asdict(rw))
        self.assertEqual(m.code, "NEG_NET")
        self.assertEqual(m.basis, "engine_rule")

    def test_extra_field_rejected(self):
        with self.assertRaises(ValidationError):
            RuleWarningModel(
                code="X", severity="info", stage="s",
                message="m", basis="documented", extra="bad",
            )


# ===========================================================================
# SimResponse
# ===========================================================================

class TestSimResponse(unittest.TestCase):

    def _make_response(self):
        results = SimResults(**_sim_result_dict())
        return SimResponse(
            id="test-001",
            inputs={"waste_mass_kg_day": 1000.0},
            params={"hrt_days": 30.0},
            results=results,
            model_version="v0.1",
            audit_hash="abc123",
            status="illustrative_estimate",
            defaults_used_unvalidated=["hrt_days", "eta_el"],
        )

    def test_valid_construction(self):
        resp = self._make_response()
        self.assertEqual(resp.id, "test-001")
        self.assertEqual(resp.notes, {})
        self.assertEqual(resp.warnings_detail, [])
        self.assertEqual(resp.missing_inputs, [])

    def test_warnings_detail_accepts_rule_warning_models(self):
        import dataclasses
        rw = RuleWarning(code="NEG_NET", severity="warning",
                         stage="electricity generation",
                         message="msg", basis="engine_rule")
        resp = self._make_response()
        resp2 = resp.model_copy(update={
            "warnings_detail": [RuleWarningModel(**dataclasses.asdict(rw))]
        })
        self.assertEqual(len(resp2.warnings_detail), 1)

    def test_extra_field_rejected(self):
        with self.assertRaises(ValidationError):
            r = _sim_result_dict()
            SimResponse(
                id="x", inputs={}, params={},
                results=SimResults(**r),
                model_version="v0.1", audit_hash="h",
                status="s", defaults_used_unvalidated=[],
                unknown_extra_field="bad",
            )


# ===========================================================================
# ParameterEntryModel
# ===========================================================================

class TestParameterEntryModel(unittest.TestCase):

    def test_validates_from_csv_row(self):
        row = {
            "name": "hrt_days",
            "value": "30.0",
            "unit": "days",
            "mass_basis": "–",
            "status": "illustrative",
            "source": "TBD",
            "uncertainty": "TBD",
            "model_version": "v0.1",
            "description": "Hydraulic retention time",
        }
        m = ParameterEntryModel(**row)
        self.assertEqual(m.name, "hrt_days")
        self.assertEqual(m.unit, "days")

    def test_extra_field_rejected(self):
        with self.assertRaises(ValidationError):
            ParameterEntryModel(
                name="x", value="1", unit="u", mass_basis="–",
                status="illustrative", source="TBD", uncertainty="TBD",
                model_version="v0.1", description="d", extra="bad",
            )


# ===========================================================================
# UncertaintyRequest
# ===========================================================================

class TestUncertaintyRequest(unittest.TestCase):

    def test_defaults(self):
        req = UncertaintyRequest()
        self.assertEqual(req.n, 2000)
        self.assertEqual(req.seed, 42)

    def test_n_below_10_rejected(self):
        with self.assertRaises(ValidationError):
            UncertaintyRequest(n=9)

    def test_n_above_20000_rejected(self):
        with self.assertRaises(ValidationError):
            UncertaintyRequest(n=20001)

    def test_n_at_boundaries_accepted(self):
        self.assertEqual(UncertaintyRequest(n=10).n, 10)
        self.assertEqual(UncertaintyRequest(n=20000).n, 20000)

    def test_custom_seed(self):
        req = UncertaintyRequest(n=500, seed=7)
        self.assertEqual(req.seed, 7)


# ===========================================================================
# UncertaintyResult
# ===========================================================================

class TestUncertaintyResult(unittest.TestCase):

    def test_validates_from_real_run_mc(self):
        """UncertaintyResult(**run_mc(Params(), n=200)) must not raise."""
        r = _mc_result_dict()
        ur = UncertaintyResult(**r)
        self.assertIsInstance(ur, UncertaintyResult)
        self.assertEqual(ur.n, 200)
        self.assertEqual(ur.seed, 42)

    def test_percentile_ordering(self):
        ur = UncertaintyResult(**_mc_result_dict())
        self.assertLessEqual(ur.p2_5, ur.median)
        self.assertLessEqual(ur.median, ur.p97_5)

    def test_assumptions_note_is_str(self):
        ur = UncertaintyResult(**_mc_result_dict())
        self.assertIsInstance(ur.assumptions_note, str)

    def test_sensitivity_list(self):
        ur = UncertaintyResult(**_mc_result_dict())
        from app.schemas.simulation import _SensitivityItem
        self.assertIsInstance(ur.sensitivity, list)
        self.assertTrue(len(ur.sensitivity) > 0)
        self.assertIn("input", _SensitivityItem.model_fields)
        self.assertIn("abs_spearman", _SensitivityItem.model_fields)

    def test_extra_field_rejected(self):
        r = _mc_result_dict()
        r["unexpected"] = "bad"
        with self.assertRaises(ValidationError):
            UncertaintyResult(**r)


if __name__ == "__main__":
    unittest.main(verbosity=2)
