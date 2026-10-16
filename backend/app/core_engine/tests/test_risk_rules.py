"""
Tests for backend/app/core_engine/risk_rules.py

Coverage:
  - RuleWarning construction and frozen; invalid severity/basis raise ValueError.
  - stage_risks: 8 entries, required keys, non-empty text, model-explanation phrase.
  - rule_warnings: each rule fires on a crafted result dict; default Params() run
    produces no warnings; real engine cases for NEG_NET / BUSWELL_EXCEEDED /
    OUT_OF_RANGE; severity and basis values valid; contamination gating.
"""

import unittest
from dataclasses import replace

from app.core_engine.engine import simulate
from app.core_engine.params import Params
from app.core_engine.risk_rules import RuleWarning, rule_warnings, stage_risks


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _codes(warnings):
    return {w.code for w in warnings}


def _minimal_result(**overrides):
    """Return a minimal valid result dict with sane defaults, then apply overrides."""
    base = {
        "organic_kg_d": 450.0,
        "suitable_kg_d": 360.0,
        "e_net_kwh_d": 50.0,
        "ch4_nm3_per_kg_vs": 0.33,
        "buswell_bound": 0.551,
        "vs_destruction": 0.50,
        "heat_deficit": False,
        "out_of_range_inputs": [],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# RuleWarning dataclass
# ---------------------------------------------------------------------------

class TestRuleWarning(unittest.TestCase):

    def test_valid_construction(self):
        rw = RuleWarning(
            code="TEST", severity="warning", stage="digestion",
            message="test message", basis="engine_rule",
        )
        self.assertEqual(rw.code, "TEST")
        self.assertEqual(rw.severity, "warning")
        self.assertEqual(rw.basis, "engine_rule")

    def test_frozen(self):
        rw = RuleWarning(
            code="X", severity="info", stage="all",
            message="msg", basis="model_assumption",
        )
        with self.assertRaises(Exception):  # FrozenInstanceError
            rw.severity = "critical"  # type: ignore[misc]

    def test_invalid_severity_raises(self):
        with self.assertRaises(ValueError, msg="should reject unknown severity"):
            RuleWarning(code="X", severity="fatal", stage="all",
                        message="m", basis="engine_rule")

    def test_invalid_basis_raises(self):
        with self.assertRaises(ValueError, msg="should reject unknown basis"):
            RuleWarning(code="X", severity="info", stage="all",
                        message="m", basis="made_up")

    def test_all_valid_severity_values(self):
        for sev in ("info", "warning", "critical"):
            rw = RuleWarning(code="X", severity=sev, stage="s",
                             message="m", basis="documented")
            self.assertEqual(rw.severity, sev)

    def test_all_valid_basis_values(self):
        for basis in ("engine_rule", "model_assumption", "documented"):
            rw = RuleWarning(code="X", severity="info", stage="s",
                             message="m", basis=basis)
            self.assertEqual(rw.basis, basis)


# ---------------------------------------------------------------------------
# stage_risks
# ---------------------------------------------------------------------------

class TestStageRisks(unittest.TestCase):

    def setUp(self):
        self.stages = stage_risks()

    def test_returns_8_entries(self):
        self.assertEqual(len(self.stages), 8)

    def test_required_keys_present(self):
        for entry in self.stages:
            for key in ("stage", "potential_issue", "explanation"):
                self.assertIn(key, entry, f"missing '{key}' in entry: {entry}")

    def test_all_text_non_empty(self):
        for entry in self.stages:
            for key in ("stage", "potential_issue", "explanation"):
                self.assertTrue(entry[key].strip(), f"empty text for '{key}': {entry}")

    def test_model_explanation_phrase_present(self):
        for entry in self.stages:
            self.assertIn(
                "model", entry["explanation"].lower(),
                f"explanation does not mention 'model': {entry['stage']}"
            )

    def test_expected_stages_covered(self):
        stage_names = {e["stage"] for e in self.stages}
        for expected in ("reception", "sorting", "conditioning", "digestion",
                         "gas collection", "gas treatment",
                         "electricity generation", "digestate"):
            self.assertIn(expected, stage_names)


# ---------------------------------------------------------------------------
# rule_warnings — individual rule triggers (crafted dicts)
# ---------------------------------------------------------------------------

class TestRuleWarningsIsolated(unittest.TestCase):

    def test_neg_net_fires_when_e_net_zero(self):
        r = _minimal_result(e_net_kwh_d=0.0)
        codes = _codes(rule_warnings(r))
        self.assertIn("NEG_NET", codes)

    def test_neg_net_fires_when_e_net_negative(self):
        r = _minimal_result(e_net_kwh_d=-10.0)
        codes = _codes(rule_warnings(r))
        self.assertIn("NEG_NET", codes)

    def test_neg_net_silent_when_positive(self):
        r = _minimal_result(e_net_kwh_d=1.0)
        codes = _codes(rule_warnings(r))
        self.assertNotIn("NEG_NET", codes)

    def test_buswell_exceeded_fires(self):
        r = _minimal_result(ch4_nm3_per_kg_vs=0.80, buswell_bound=0.55)
        codes = _codes(rule_warnings(r))
        self.assertIn("BUSWELL_EXCEEDED", codes)

    def test_buswell_exceeded_silent_at_equal(self):
        r = _minimal_result(ch4_nm3_per_kg_vs=0.55, buswell_bound=0.55)
        codes = _codes(rule_warnings(r))
        self.assertNotIn("BUSWELL_EXCEEDED", codes)

    def test_vs_destruction_fires_above_limit(self):
        r = _minimal_result(vs_destruction=0.86)  # > 0.85
        codes = _codes(rule_warnings(r))
        self.assertIn("VS_DESTRUCTION", codes)

    def test_vs_destruction_silent_at_limit(self):
        r = _minimal_result(vs_destruction=0.85)  # exactly 0.85 — not exceeded
        codes = _codes(rule_warnings(r))
        self.assertNotIn("VS_DESTRUCTION", codes)

    def test_heat_deficit_fires_when_true(self):
        r = _minimal_result(heat_deficit=True)
        codes = _codes(rule_warnings(r))
        self.assertIn("HEAT_DEFICIT", codes)

    def test_heat_deficit_silent_when_false(self):
        r = _minimal_result(heat_deficit=False)
        codes = _codes(rule_warnings(r))
        self.assertNotIn("HEAT_DEFICIT", codes)

    def test_out_of_range_fires_when_list_non_empty(self):
        r = _minimal_result(out_of_range_inputs=["hrt_days"])
        codes = _codes(rule_warnings(r))
        self.assertIn("OUT_OF_RANGE", codes)

    def test_out_of_range_silent_when_empty(self):
        r = _minimal_result(out_of_range_inputs=[])
        codes = _codes(rule_warnings(r))
        self.assertNotIn("OUT_OF_RANGE", codes)

    def test_ml_extrapolation_fires(self):
        r = _minimal_result()
        codes = _codes(rule_warnings(r, extrapolation_flag=True))
        self.assertIn("ML_EXTRAPOLATION", codes)

    def test_ml_extrapolation_silent_by_default(self):
        r = _minimal_result()
        codes = _codes(rule_warnings(r))
        self.assertNotIn("ML_EXTRAPOLATION", codes)

    def test_missing_input_fires_when_key_absent(self):
        r = {"suitable_kg_d": 360.0}  # organic_kg_d and e_net_kwh_d missing
        codes = _codes(rule_warnings(r))
        self.assertIn("MISSING_INPUT", codes)

    def test_missing_input_fires_when_key_is_none(self):
        r = _minimal_result(e_net_kwh_d=None)
        codes = _codes(rule_warnings(r))
        self.assertIn("MISSING_INPUT", codes)

    def test_missing_input_silent_when_all_present(self):
        r = _minimal_result()
        codes = _codes(rule_warnings(r))
        self.assertNotIn("MISSING_INPUT", codes)

    def test_contamination_fires_above_threshold(self):
        r = _minimal_result()
        codes = _codes(rule_warnings(r, contamination_pct=15.0, contamination_threshold_pct=10.0))
        self.assertIn("CONTAMINATION", codes)

    def test_contamination_silent_at_or_below_threshold(self):
        r = _minimal_result()
        codes = _codes(rule_warnings(r, contamination_pct=10.0, contamination_threshold_pct=10.0))
        self.assertNotIn("CONTAMINATION", codes)

    def test_contamination_silent_when_only_one_arg_given(self):
        r = _minimal_result()
        # Only pct provided, no threshold — must NOT fire
        codes = _codes(rule_warnings(r, contamination_pct=15.0))
        self.assertNotIn("CONTAMINATION", codes)
        # Only threshold provided — must NOT fire
        codes = _codes(rule_warnings(r, contamination_threshold_pct=10.0))
        self.assertNotIn("CONTAMINATION", codes)

    def test_contamination_basis_is_model_assumption(self):
        r = _minimal_result()
        warnings = rule_warnings(r, contamination_pct=20.0, contamination_threshold_pct=10.0)
        cont = [w for w in warnings if w.code == "CONTAMINATION"]
        self.assertEqual(len(cont), 1)
        self.assertEqual(cont[0].basis, "model_assumption")


# ---------------------------------------------------------------------------
# rule_warnings — real engine results
# ---------------------------------------------------------------------------

class TestRuleWarningsRealEngine(unittest.TestCase):

    def test_default_params_produces_no_warnings(self):
        r = simulate(Params())
        warnings = rule_warnings(r)
        self.assertEqual(warnings, [],
                         msg=f"Expected no warnings for default Params, got: {[w.code for w in warnings]}")

    def test_zero_availability_gives_neg_net(self):
        r = simulate(replace(Params(), availability=0.0))
        codes = _codes(rule_warnings(r))
        self.assertIn("NEG_NET", codes)

    def test_high_yield_gives_buswell_exceeded(self):
        r = simulate(replace(Params(), y_biogas_nm3_per_kg_vs=1.5))
        codes = _codes(rule_warnings(r))
        self.assertIn("BUSWELL_EXCEEDED", codes)

    def test_hrt_5_gives_out_of_range(self):
        r = simulate(replace(Params(), hrt_days=5.0))
        codes = _codes(rule_warnings(r))
        self.assertIn("OUT_OF_RANGE", codes)

    def test_cold_high_u_gives_heat_deficit(self):
        r = simulate(replace(Params(), ambient_temp_c=-40, u_wall_w_m2k=5.0))
        codes = _codes(rule_warnings(r))
        self.assertIn("HEAT_DEFICIT", codes)


# ---------------------------------------------------------------------------
# Severity and basis validity of all emitted warnings
# ---------------------------------------------------------------------------

class TestRuleWarningValidity(unittest.TestCase):

    def _all_warnings(self):
        """Generate a set of scenarios that exercises every rule."""
        results = []
        # One scenario per rule
        results.append(rule_warnings(_minimal_result(e_net_kwh_d=-1.0)))
        results.append(rule_warnings(_minimal_result(ch4_nm3_per_kg_vs=1.0, buswell_bound=0.5)))
        results.append(rule_warnings(_minimal_result(vs_destruction=0.90)))
        results.append(rule_warnings(_minimal_result(heat_deficit=True)))
        results.append(rule_warnings(_minimal_result(out_of_range_inputs=["hrt_days"])))
        results.append(rule_warnings(_minimal_result(), extrapolation_flag=True))
        results.append(rule_warnings(_minimal_result(),
                                     contamination_pct=20.0, contamination_threshold_pct=5.0))
        results.append(rule_warnings({"organic_kg_d": None}))
        all_w = [w for batch in results for w in batch]
        return all_w

    def test_all_severities_valid(self):
        from app.core_engine.risk_rules import _VALID_SEVERITIES
        for w in self._all_warnings():
            self.assertIn(w.severity, _VALID_SEVERITIES, f"bad severity on {w.code}")

    def test_all_bases_valid(self):
        from app.core_engine.risk_rules import _VALID_BASES
        for w in self._all_warnings():
            self.assertIn(w.basis, _VALID_BASES, f"bad basis on {w.code}")

    def test_all_messages_non_empty(self):
        for w in self._all_warnings():
            self.assertTrue(w.message.strip(), f"empty message on {w.code}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
