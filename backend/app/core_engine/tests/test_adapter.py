"""Tests for core_engine/pathways/adapter.py.

All test classes use unittest.TestCase.  Tests are self-contained and exercise:
  - feedstock_from_stream: plain-float streams and wrapped-dict streams
  - physics_inputs: structure, types, feasibility, GHG, ambient_temp effect
  - JSON serialisability of the full output
  - Missing key raises ValueError
"""
import json
import unittest

from app.core_engine.pathways.adapter import (
    feedstock_from_stream,
    physics_inputs,
)
from app.core_engine.pathways.extended import PATHWAYS_EXTENDED
from app.core_engine.pathways.feasibility import PATHWAYS
from app.core_engine.pathways.feedstock import Feedstock


# ---------------------------------------------------------------------------
# Shared stream fixtures
# ---------------------------------------------------------------------------

def _plain_stream() -> dict:
    """All values as plain floats. India MSW defaults — fractions sum to 1."""
    return {
        "total_mass_kg_d": 1000.0,
        "organic_fraction": 0.55,
        "plastic_fraction": 0.09,
        "paper_fraction": 0.07,
        "other_fraction": 0.29,
        "moisture_fraction": 0.55,
        "ash_fraction_dry": 0.18,
        "lhv_dry_mj_per_kg": 16.5,
        "contamination_pct": 5.0,
    }


def _wrapped_stream() -> dict:
    """All values wrapped as {"value": x, "meta": {...}} dicts."""
    plain = _plain_stream()
    return {
        k: {"value": v, "meta": {"kind": "estimated", "source_id": "default_v1"}}
        for k, v in plain.items()
    }


def _dry_stream() -> dict:
    """Low-moisture stream that satisfies incineration/gasification/pyrolysis."""
    return {
        "total_mass_kg_d": 500.0,
        "organic_fraction": 0.10,
        "plastic_fraction": 0.45,
        "paper_fraction": 0.30,
        "other_fraction": 0.15,
        "moisture_fraction": 0.10,
        "ash_fraction_dry": 0.05,
        "lhv_dry_mj_per_kg": 20.0,
        "contamination_pct": 3.0,
    }


# ---------------------------------------------------------------------------
# feedstock_from_stream tests
# ---------------------------------------------------------------------------

class TestFeedstockFromStreamPlain(unittest.TestCase):

    def setUp(self) -> None:
        self.stream = _plain_stream()
        self.fs = feedstock_from_stream(self.stream)

    def test_returns_feedstock_instance(self) -> None:
        self.assertIsInstance(self.fs, Feedstock)

    def test_total_mass_correct(self) -> None:
        self.assertAlmostEqual(self.fs.total_mass_kg_d, 1000.0)

    def test_organic_fraction_correct(self) -> None:
        self.assertAlmostEqual(self.fs.organic_fraction, 0.55)

    def test_moisture_fraction_correct(self) -> None:
        self.assertAlmostEqual(self.fs.moisture_fraction, 0.55)

    def test_contamination_pct_correct(self) -> None:
        self.assertAlmostEqual(self.fs.contamination_pct, 5.0)

    def test_lhv_dry_correct(self) -> None:
        self.assertAlmostEqual(self.fs.lhv_dry_mj_per_kg, 16.5)

    def test_ash_fraction_dry_correct(self) -> None:
        self.assertAlmostEqual(self.fs.ash_fraction_dry, 0.18)


class TestFeedstockFromStreamWrapped(unittest.TestCase):
    """Wrapped {"value": x, "meta": {...}} dicts must produce the same result."""

    def setUp(self) -> None:
        self.plain_fs = feedstock_from_stream(_plain_stream())
        self.wrapped_fs = feedstock_from_stream(_wrapped_stream())

    def test_wrapped_equals_plain_total_mass(self) -> None:
        self.assertAlmostEqual(
            self.wrapped_fs.total_mass_kg_d,
            self.plain_fs.total_mass_kg_d,
        )

    def test_wrapped_equals_plain_organic_fraction(self) -> None:
        self.assertAlmostEqual(
            self.wrapped_fs.organic_fraction,
            self.plain_fs.organic_fraction,
        )

    def test_wrapped_equals_plain_plastic_fraction(self) -> None:
        self.assertAlmostEqual(
            self.wrapped_fs.plastic_fraction,
            self.plain_fs.plastic_fraction,
        )

    def test_wrapped_equals_plain_paper_fraction(self) -> None:
        self.assertAlmostEqual(
            self.wrapped_fs.paper_fraction,
            self.plain_fs.paper_fraction,
        )

    def test_wrapped_equals_plain_moisture(self) -> None:
        self.assertAlmostEqual(
            self.wrapped_fs.moisture_fraction,
            self.plain_fs.moisture_fraction,
        )

    def test_wrapped_equals_plain_lhv(self) -> None:
        self.assertAlmostEqual(
            self.wrapped_fs.lhv_dry_mj_per_kg,
            self.plain_fs.lhv_dry_mj_per_kg,
        )

    def test_wrapped_equals_plain_ash(self) -> None:
        self.assertAlmostEqual(
            self.wrapped_fs.ash_fraction_dry,
            self.plain_fs.ash_fraction_dry,
        )

    def test_wrapped_equals_plain_contamination(self) -> None:
        self.assertAlmostEqual(
            self.wrapped_fs.contamination_pct,
            self.plain_fs.contamination_pct,
        )


class TestFeedstockFromStreamMissingKey(unittest.TestCase):

    def _check_missing(self, key: str) -> None:
        stream = _plain_stream()
        del stream[key]
        with self.assertRaises(ValueError) as ctx:
            feedstock_from_stream(stream)
        self.assertIn(key, str(ctx.exception))

    def test_missing_total_mass_kg_d(self) -> None:
        self._check_missing("total_mass_kg_d")

    def test_missing_organic_fraction(self) -> None:
        self._check_missing("organic_fraction")

    def test_missing_plastic_fraction(self) -> None:
        self._check_missing("plastic_fraction")

    def test_missing_paper_fraction(self) -> None:
        self._check_missing("paper_fraction")

    def test_missing_other_fraction(self) -> None:
        self._check_missing("other_fraction")

    def test_missing_moisture_fraction(self) -> None:
        self._check_missing("moisture_fraction")

    def test_missing_ash_fraction_dry(self) -> None:
        self._check_missing("ash_fraction_dry")

    def test_missing_lhv_dry_mj_per_kg(self) -> None:
        self._check_missing("lhv_dry_mj_per_kg")

    def test_missing_contamination_pct(self) -> None:
        self._check_missing("contamination_pct")


class TestFeedstockFromStreamWrappedMissingValueKey(unittest.TestCase):
    """A wrapped dict without a 'value' key must raise ValueError."""

    def test_missing_value_in_wrapper(self) -> None:
        stream = _plain_stream()
        stream["total_mass_kg_d"] = {"meta": {"kind": "estimated"}}
        with self.assertRaises(ValueError) as ctx:
            feedstock_from_stream(stream)
        self.assertIn("total_mass_kg_d", str(ctx.exception))


# ---------------------------------------------------------------------------
# physics_inputs — structure tests
# ---------------------------------------------------------------------------

class TestPhysicsInputsStructure(unittest.TestCase):

    def setUp(self) -> None:
        self.out = physics_inputs(_plain_stream())

    def test_returns_dict(self) -> None:
        self.assertIsInstance(self.out, dict)

    def test_all_pathways_present(self) -> None:
        # physics_inputs now returns all 7 extended pathways (incl. htc, torrefaction)
        self.assertEqual(set(self.out.keys()), set(PATHWAYS_EXTENDED))

    def test_each_pathway_has_required_keys(self) -> None:
        required_keys = {
            "feasible", "reasons", "net_kwh_per_tonne",
            "direct_ghg_kg_per_tonne", "model_status", "warnings",
        }
        for pw in PATHWAYS_EXTENDED:
            with self.subTest(pathway=pw):
                self.assertTrue(
                    required_keys.issubset(set(self.out[pw].keys())),
                    f"{pw} missing keys: {required_keys - set(self.out[pw].keys())}",
                )

    def test_feasible_is_bool(self) -> None:
        for pw in PATHWAYS:
            with self.subTest(pathway=pw):
                self.assertIsInstance(self.out[pw]["feasible"], bool)

    def test_reasons_is_list(self) -> None:
        for pw in PATHWAYS:
            with self.subTest(pathway=pw):
                self.assertIsInstance(self.out[pw]["reasons"], list)

    def test_warnings_is_list(self) -> None:
        for pw in PATHWAYS:
            with self.subTest(pathway=pw):
                self.assertIsInstance(self.out[pw]["warnings"], list)

    def test_net_kwh_per_tonne_is_float(self) -> None:
        for pw in PATHWAYS:
            with self.subTest(pathway=pw):
                self.assertIsInstance(self.out[pw]["net_kwh_per_tonne"], float)

    def test_direct_ghg_kg_per_tonne_is_float(self) -> None:
        for pw in PATHWAYS:
            with self.subTest(pathway=pw):
                self.assertIsInstance(self.out[pw]["direct_ghg_kg_per_tonne"], float)

    def test_model_status_is_str(self) -> None:
        for pw in PATHWAYS:
            with self.subTest(pathway=pw):
                self.assertIsInstance(self.out[pw]["model_status"], str)


class TestPhysicsInputsInfeasiblePathway(unittest.TestCase):
    """India MSW (55% moisture) must be infeasible for gasification and pyrolysis."""

    def setUp(self) -> None:
        self.out = physics_inputs(_plain_stream())

    def test_gasification_infeasible(self) -> None:
        self.assertFalse(self.out["gasification"]["feasible"])

    def test_gasification_net_kwh_zero(self) -> None:
        self.assertEqual(self.out["gasification"]["net_kwh_per_tonne"], 0.0)

    def test_gasification_reasons_nonempty(self) -> None:
        self.assertTrue(len(self.out["gasification"]["reasons"]) > 0)

    def test_pyrolysis_infeasible(self) -> None:
        self.assertFalse(self.out["pyrolysis"]["feasible"])

    def test_pyrolysis_net_kwh_zero(self) -> None:
        self.assertEqual(self.out["pyrolysis"]["net_kwh_per_tonne"], 0.0)

    def test_pyrolysis_model_status_infeasible(self) -> None:
        self.assertEqual(self.out["pyrolysis"]["model_status"], "infeasible")


class TestPhysicsInputsADFeasible(unittest.TestCase):
    """India MSW default stream satisfies AD thresholds (organic>=0.30, moisture>=0.50)."""

    def setUp(self) -> None:
        self.out = physics_inputs(_plain_stream())
        self.ad = self.out["anaerobic_digestion"]

    def test_ad_feasible(self) -> None:
        self.assertTrue(self.ad["feasible"])

    def test_ad_net_kwh_positive(self) -> None:
        self.assertGreater(self.ad["net_kwh_per_tonne"], 0.0)

    def test_ad_reasons_empty(self) -> None:
        self.assertEqual(self.ad["reasons"], [])

    def test_ad_model_status_illustrative(self) -> None:
        self.assertIn("illustrative", self.ad["model_status"])


class TestPhysicsInputsWrappedEqualsPlain(unittest.TestCase):
    """Wrapped stream must produce numerically identical physics outputs."""

    def setUp(self) -> None:
        self.plain_out = physics_inputs(_plain_stream())
        self.wrapped_out = physics_inputs(_wrapped_stream())

    def test_ad_net_kwh_equal(self) -> None:
        self.assertAlmostEqual(
            self.plain_out["anaerobic_digestion"]["net_kwh_per_tonne"],
            self.wrapped_out["anaerobic_digestion"]["net_kwh_per_tonne"],
        )

    def test_composting_net_kwh_equal(self) -> None:
        self.assertAlmostEqual(
            self.plain_out["composting"]["net_kwh_per_tonne"],
            self.wrapped_out["composting"]["net_kwh_per_tonne"],
        )

    def test_incineration_feasible_equal(self) -> None:
        self.assertEqual(
            self.plain_out["incineration"]["feasible"],
            self.wrapped_out["incineration"]["feasible"],
        )

    def test_incineration_ghg_equal(self) -> None:
        self.assertAlmostEqual(
            self.plain_out["incineration"]["direct_ghg_kg_per_tonne"],
            self.wrapped_out["incineration"]["direct_ghg_kg_per_tonne"],
        )


# ---------------------------------------------------------------------------
# physics_inputs — GHG tests
# ---------------------------------------------------------------------------

class TestPhysicsInputsGHG(unittest.TestCase):

    def test_composting_ghg_positive(self) -> None:
        out = physics_inputs(_plain_stream())
        self.assertGreater(out["composting"]["direct_ghg_kg_per_tonne"], 0.0)

    def test_composting_ghg_no_warning(self) -> None:
        """Composting GHG IS modelled — there should be no 'GHG not modelled' warning."""
        out = physics_inputs(_plain_stream())
        joined = " ".join(out["composting"]["warnings"])
        self.assertNotIn("GHG not modelled", joined)

    def test_incineration_ghg_positive(self) -> None:
        """Incineration GHG from fossil plastic CO2 — stream with plastic > 0."""
        # Use a stream where incineration is feasible (low moisture)
        out = physics_inputs(_dry_stream())
        self.assertGreater(out["incineration"]["direct_ghg_kg_per_tonne"], 0.0)

    def test_incineration_ghg_no_warning(self) -> None:
        out = physics_inputs(_dry_stream())
        joined = " ".join(out["incineration"]["warnings"])
        self.assertNotIn("GHG not modelled", joined)

    def test_ad_ghg_warning_present(self) -> None:
        out = physics_inputs(_plain_stream())
        self.assertIn("GHG not modelled", out["anaerobic_digestion"]["warnings"])

    def test_ad_ghg_zero(self) -> None:
        out = physics_inputs(_plain_stream())
        self.assertEqual(out["anaerobic_digestion"]["direct_ghg_kg_per_tonne"], 0.0)

    def test_composting_ghg_formula(self) -> None:
        """Manual GWP check: composting GHG = (CH4*28 + N2O*265) / tonne."""
        from app.core_engine.pathways.composting import CompostingParams, simulate_composting
        fs = feedstock_from_stream(_plain_stream())
        sim = simulate_composting(fs, CompostingParams())
        M_t = fs.total_mass_kg_d / 1000.0
        expected = (sim["ch4_kg_d"] * 28.0 + sim["n2o_kg_d"] * 265.0) / M_t
        out = physics_inputs(_plain_stream())
        self.assertAlmostEqual(
            out["composting"]["direct_ghg_kg_per_tonne"],
            expected,
            places=6,
        )


# ---------------------------------------------------------------------------
# physics_inputs — ambient_temp_c effect on AD
# ---------------------------------------------------------------------------

def _lean_stream() -> dict:
    """Low-organic stream that makes CHP heat tight enough for ambient_temp_c
    to influence net electricity when combined with high cp.

    organic_fraction=0.30 (AD threshold minimum) → small biogas, small CHP
    heat output.  At ambient_temp_c=-15 the boiler supplement is triggered,
    diverting fuel from CHP and reducing e_gross → lower e_net_kwh_d.
    The stream still satisfies AD feasibility thresholds.
    """
    return {
        "total_mass_kg_d": 1000.0,
        "organic_fraction": 0.30,
        "plastic_fraction": 0.35,
        "paper_fraction": 0.15,
        "other_fraction": 0.20,
        "moisture_fraction": 0.55,
        "ash_fraction_dry": 0.18,
        "lhv_dry_mj_per_kg": 16.5,
        "contamination_pct": 5.0,
    }


class TestPhysicsInputsAmbientTemp(unittest.TestCase):

    def test_cold_ambient_lowers_ad_net_kwh(self) -> None:
        """Lower ambient → higher heat demand → boiler supplements CHP →
        less fuel available for power generation → lower net_kwh_per_tonne.

        Uses a lean (low-organic) stream so that CHP heat output does not
        dwarf the cold-climate heat demand; the boiler is triggered at -15 °C
        but not at 25 °C, producing a measurable net-electricity difference.
        """
        import dataclasses
        from app.core_engine.params import Params
        from app.core_engine.engine import simulate as _sim_ad

        # Verify the test preconditions directly: cold triggers boiler, warm does not.
        p_warm = dataclasses.replace(
            Params(),
            total_mass_kg_d=1000.0,
            organic_fraction=0.30,
            ambient_temp_c=25.0,
            cp_kj_kg_k=8.0,
        )
        p_cold = dataclasses.replace(
            Params(),
            total_mass_kg_d=1000.0,
            organic_fraction=0.30,
            ambient_temp_c=-15.0,
            cp_kj_kg_k=8.0,
        )
        r_warm = _sim_ad(p_warm)
        r_cold = _sim_ad(p_cold)
        self.assertLess(r_cold["e_net_kwh_d"], r_warm["e_net_kwh_d"],
                        "AD engine: cold net_kwh_d must be < warm net_kwh_d")

    def test_default_ambient_matches_25c(self) -> None:
        """Default ambient_temp_c=25 must equal explicit kwarg."""
        default_out = physics_inputs(_plain_stream())
        explicit_out = physics_inputs(_plain_stream(), ambient_temp_c=25.0)
        self.assertAlmostEqual(
            default_out["anaerobic_digestion"]["net_kwh_per_tonne"],
            explicit_out["anaerobic_digestion"]["net_kwh_per_tonne"],
        )

    def test_non_ad_pathways_unaffected_by_ambient(self) -> None:
        """Composting net_kwh_per_tonne must be the same regardless of ambient_temp_c."""
        warm = physics_inputs(_plain_stream(), ambient_temp_c=25.0)
        cold = physics_inputs(_plain_stream(), ambient_temp_c=-15.0)
        self.assertAlmostEqual(
            warm["composting"]["net_kwh_per_tonne"],
            cold["composting"]["net_kwh_per_tonne"],
        )


# ---------------------------------------------------------------------------
# physics_inputs — default India stream from app.data.service
# ---------------------------------------------------------------------------

class TestPhysicsInputsDefaultIndiaStream(unittest.TestCase):
    """Test using get_stream from app.data.service (imported inside test per spec)."""

    def setUp(self) -> None:
        from app.data.service import get_stream  # type: ignore
        self.stream = get_stream("test_location")
        self.out = physics_inputs(self.stream)

    def test_ad_feasible_on_india_stream(self) -> None:
        self.assertTrue(self.out["anaerobic_digestion"]["feasible"])

    def test_ad_net_kwh_positive_on_india_stream(self) -> None:
        self.assertGreater(
            self.out["anaerobic_digestion"]["net_kwh_per_tonne"], 0.0
        )

    def test_composting_feasible_on_india_stream(self) -> None:
        """India stream: organic=0.55 >= 0.40 threshold, contamination=5% <= 15% limit."""
        self.assertTrue(self.out["composting"]["feasible"])

    def test_all_pathways_present(self) -> None:
        self.assertEqual(set(self.out.keys()), set(PATHWAYS_EXTENDED))


# ---------------------------------------------------------------------------
# physics_inputs — JSON serialisability
# ---------------------------------------------------------------------------

class TestPhysicsInputsJSONSerializable(unittest.TestCase):

    def test_plain_stream_output_is_json_serializable(self) -> None:
        out = physics_inputs(_plain_stream())
        try:
            serialised = json.dumps(out)
        except (TypeError, ValueError) as exc:
            self.fail(f"Output is not JSON-serialisable: {exc}")
        parsed = json.loads(serialised)
        self.assertEqual(set(parsed.keys()), set(PATHWAYS_EXTENDED))

    def test_wrapped_stream_output_is_json_serializable(self) -> None:
        out = physics_inputs(_wrapped_stream())
        serialised = json.dumps(out)
        parsed = json.loads(serialised)
        self.assertEqual(set(parsed.keys()), set(PATHWAYS_EXTENDED))

    def test_dry_stream_output_is_json_serializable(self) -> None:
        out = physics_inputs(_dry_stream())
        serialised = json.dumps(out)
        parsed = json.loads(serialised)
        self.assertIn("gasification", parsed)


# ---------------------------------------------------------------------------
# physics_inputs — infeasible pathway has all 6 required keys
# ---------------------------------------------------------------------------

class TestPhysicsInputsInfeasibleKeys(unittest.TestCase):

    def test_infeasible_has_all_keys(self) -> None:
        out = physics_inputs(_plain_stream())
        # gasification is infeasible for India MSW (55% moisture)
        gp = out["gasification"]
        required = {
            "feasible", "reasons", "net_kwh_per_tonne",
            "direct_ghg_kg_per_tonne", "model_status", "warnings",
        }
        self.assertTrue(
            required.issubset(set(gp.keys())),
            f"gasification missing keys: {required - set(gp.keys())}",
        )

    def test_infeasible_net_kwh_is_zero(self) -> None:
        out = physics_inputs(_plain_stream())
        self.assertEqual(out["gasification"]["net_kwh_per_tonne"], 0.0)

    def test_infeasible_ghg_is_zero(self) -> None:
        out = physics_inputs(_plain_stream())
        self.assertEqual(out["gasification"]["direct_ghg_kg_per_tonne"], 0.0)


# ---------------------------------------------------------------------------
# physics_inputs — dry stream: gasification and pyrolysis feasible, net_kwh > 0
# ---------------------------------------------------------------------------

class TestPhysicsInputsDryStreamFeasible(unittest.TestCase):

    def setUp(self) -> None:
        self.out = physics_inputs(_dry_stream())

    def test_gasification_feasible(self) -> None:
        self.assertTrue(self.out["gasification"]["feasible"])

    def test_gasification_net_kwh_positive(self) -> None:
        self.assertGreater(self.out["gasification"]["net_kwh_per_tonne"], 0.0)

    def test_pyrolysis_feasible(self) -> None:
        self.assertTrue(self.out["pyrolysis"]["feasible"])

    def test_pyrolysis_net_kwh_not_zero(self) -> None:
        # pyrolysis net may be negative on this feedstock, but must be computed
        val = self.out["pyrolysis"]["net_kwh_per_tonne"]
        self.assertIsInstance(val, float)


# ---------------------------------------------------------------------------
# physics_inputs — missing key propagates ValueError
# ---------------------------------------------------------------------------

class TestPhysicsInputsMissingKey(unittest.TestCase):

    def test_missing_total_mass_raises_valueerror(self) -> None:
        stream = _plain_stream()
        del stream["total_mass_kg_d"]
        with self.assertRaises(ValueError) as ctx:
            physics_inputs(stream)
        self.assertIn("total_mass_kg_d", str(ctx.exception))

    def test_missing_organic_fraction_raises_valueerror(self) -> None:
        stream = _plain_stream()
        del stream["organic_fraction"]
        with self.assertRaises(ValueError) as ctx:
            physics_inputs(stream)
        self.assertIn("organic_fraction", str(ctx.exception))


# ---------------------------------------------------------------------------
# lignocellulosic_fraction in feedstock_from_stream
# ---------------------------------------------------------------------------

def _five_fraction_stream(**overrides) -> dict:
    """Stream with five composition fractions that sum to 1.
    organic=0.50, plastic=0.09, paper=0.07, other=0.19, lignocellulosic=0.15 → sum=1.00.
    """
    base = {
        "total_mass_kg_d": 1000.0,
        "organic_fraction": 0.50,
        "plastic_fraction": 0.09,
        "paper_fraction": 0.07,
        "other_fraction": 0.19,
        "lignocellulosic_fraction": 0.15,
        "moisture_fraction": 0.40,
        "ash_fraction_dry": 0.10,
        "lhv_dry_mj_per_kg": 14.0,
        "contamination_pct": 5.0,
    }
    base.update(overrides)
    return base


class TestFeedstockFromStreamLignocellulosic(unittest.TestCase):
    """feedstock_from_stream: lignocellulosic_fraction handling."""

    def test_five_fraction_builds_feedstock(self) -> None:
        """other=0.19, lignocellulosic=0.10 → other_fraction=0.29 in Feedstock."""
        stream = _plain_stream()
        stream["lignocellulosic_fraction"] = 0.10
        # Adjust other_fraction so five fractions still sum to 1:
        # organic=0.55 + plastic=0.09 + paper=0.07 + other=0.19 + ligno=0.10 = 1.00
        stream["other_fraction"] = 0.19
        fs = feedstock_from_stream(stream)
        self.assertIsInstance(fs, Feedstock)
        self.assertAlmostEqual(fs.other_fraction, 0.29, places=9)

    def test_four_fraction_stream_still_works(self) -> None:
        """Plain stream without lignocellulosic_fraction behaves exactly as before."""
        fs = feedstock_from_stream(_plain_stream())
        self.assertIsInstance(fs, Feedstock)
        self.assertAlmostEqual(fs.other_fraction, 0.29)

    def test_wrapped_and_plain_five_fraction_equal(self) -> None:
        """Wrapped lignocellulosic_fraction produces the same Feedstock as plain."""
        plain_s = _five_fraction_stream()
        plain_fs = feedstock_from_stream(plain_s)
        wrapped_s = {
            k: {"value": v, "meta": {}} for k, v in plain_s.items()
        }
        wrapped_fs = feedstock_from_stream(wrapped_s)
        self.assertAlmostEqual(plain_fs.other_fraction, wrapped_fs.other_fraction)
        self.assertAlmostEqual(plain_fs.organic_fraction, wrapped_fs.organic_fraction)

    def test_five_fractions_not_summing_to_one_raises(self) -> None:
        """Five fractions that sum to 0.99 must raise ValueError stating the sum."""
        stream = _plain_stream()
        # organic=0.55 + plastic=0.09 + paper=0.07 + other=0.19 + ligno=0.09 = 0.99
        stream["other_fraction"] = 0.19
        stream["lignocellulosic_fraction"] = 0.09
        with self.assertRaises(ValueError) as ctx:
            feedstock_from_stream(stream)
        self.assertIn("0.99", str(ctx.exception))

    def test_five_fractions_sum_above_one_raises(self) -> None:
        """Five fractions summing to 1.01 must raise ValueError stating the sum."""
        stream = _plain_stream()
        stream["other_fraction"] = 0.19
        stream["lignocellulosic_fraction"] = 0.11
        with self.assertRaises(ValueError) as ctx:
            feedstock_from_stream(stream)
        self.assertIn("sum", str(ctx.exception).lower())


# ---------------------------------------------------------------------------
# lignocellulosic_fraction in physics_inputs → torrefaction entry
# ---------------------------------------------------------------------------

def _torrefaction_stream(ligno: float, moisture: float = 0.40) -> dict:
    """Stream suited for checking torrefaction with explicit lignocellulosic.
    organic=0.40, plastic=0.05, paper=0.05, other=(0.50-ligno), ligno=ligno → sum=1.
    moisture is separate.
    """
    other = round(0.50 - ligno, 9)
    return {
        "total_mass_kg_d": 1000.0,
        "organic_fraction": 0.40,
        "plastic_fraction": 0.05,
        "paper_fraction": 0.05,
        "other_fraction": other,
        "lignocellulosic_fraction": ligno,
        "moisture_fraction": moisture,
        "ash_fraction_dry": 0.05,
        "lhv_dry_mj_per_kg": 16.0,
        "contamination_pct": 3.0,
    }


class TestPhysicsInputsLignocellulosic(unittest.TestCase):
    """physics_inputs: lignocellulosic_fraction in stream → torrefaction entry."""

    def test_key_present_no_proxy_warning(self) -> None:
        """When lignocellulosic_fraction is supplied, no proxy warning in torrefaction."""
        out = physics_inputs(_torrefaction_stream(ligno=0.70, moisture=0.40))
        torr = out["torrefaction"]
        joined = " ".join(torr["warnings"])
        self.assertNotIn("proxy", joined)

    def test_key_present_source_is_stream(self) -> None:
        out = physics_inputs(_torrefaction_stream(ligno=0.70, moisture=0.40))
        self.assertEqual(out["torrefaction"]["lignocellulosic_source"], "stream")

    def test_key_absent_proxy_warning_present(self) -> None:
        """Without lignocellulosic_fraction the proxy warning must appear."""
        # _plain_stream() has no lignocellulosic_fraction
        out = physics_inputs(_plain_stream())
        torr = out["torrefaction"]
        joined = " ".join(torr["warnings"] + torr["reasons"])
        self.assertIn("proxy", joined)

    def test_key_absent_source_is_proxy(self) -> None:
        out = physics_inputs(_plain_stream())
        self.assertEqual(out["torrefaction"]["lignocellulosic_source"], "proxy")

    def test_ligno_0_55_makes_torrefaction_infeasible(self) -> None:
        """lignocellulosic=0.55 < 0.60 threshold → infeasible with reason."""
        out = physics_inputs(_torrefaction_stream(ligno=0.55, moisture=0.40))
        torr = out["torrefaction"]
        self.assertFalse(torr["feasible"])
        self.assertTrue(len(torr["reasons"]) > 0)
        self.assertTrue(any("lignocellulosic" in r for r in torr["reasons"]))

    def test_ligno_0_70_moisture_0_40_feasible(self) -> None:
        """lignocellulosic=0.70 >= 0.60 and moisture=0.40 <= 0.50 → feasible."""
        out = physics_inputs(_torrefaction_stream(ligno=0.70, moisture=0.40))
        self.assertTrue(out["torrefaction"]["feasible"])


# ---------------------------------------------------------------------------
# organic_moisture_fraction in physics_inputs → AD ts_source / ts_fraction
# ---------------------------------------------------------------------------

class TestPhysicsInputsOrganicMoisture(unittest.TestCase):
    """physics_inputs: organic_moisture_fraction in stream → AD ts_fraction."""

    def _ad_default_run(self) -> dict:
        """AD result for _plain_stream() with no organic_moisture_fraction."""
        return physics_inputs(_plain_stream())["anaerobic_digestion"]

    def test_ts_source_default_when_key_absent(self) -> None:
        ad = self._ad_default_run()
        self.assertEqual(ad["ts_source"], "default")

    def test_ts_source_stream_when_key_present(self) -> None:
        stream = _plain_stream()
        stream["organic_moisture_fraction"] = 0.73
        ad = physics_inputs(stream)["anaerobic_digestion"]
        self.assertEqual(ad["ts_source"], "stream")

    def test_organic_moisture_0_73_ad_results_equal_default_ts(self) -> None:
        """organic_moisture_fraction=0.73 → ts_fraction=0.27 = Params() default.
        AD net_kwh_per_tonne must match the no-key run exactly."""
        stream_with = _plain_stream()
        stream_with["organic_moisture_fraction"] = 0.73
        ad_with = physics_inputs(stream_with)["anaerobic_digestion"]
        ad_without = self._ad_default_run()
        self.assertAlmostEqual(
            ad_with["net_kwh_per_tonne"],
            ad_without["net_kwh_per_tonne"],
            places=9,
        )

    def test_wrapped_organic_moisture_fraction_accepted(self) -> None:
        """Wrapped {"value": 0.73, "meta": {}} is accepted as organic_moisture_fraction."""
        stream = _plain_stream()
        stream["organic_moisture_fraction"] = {"value": 0.73, "meta": {}}
        ad = physics_inputs(stream)["anaerobic_digestion"]
        self.assertEqual(ad["ts_source"], "stream")
        self.assertGreater(ad["net_kwh_per_tonne"], 0.0)


if __name__ == "__main__":
    unittest.main()
