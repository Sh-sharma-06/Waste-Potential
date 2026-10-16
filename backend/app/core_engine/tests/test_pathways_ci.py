"""CI tests for composting and incineration pathway models."""
import unittest

from app.core_engine.pathways.feedstock import Feedstock
from app.core_engine.pathways.composting import CompostingParams, simulate_composting
from app.core_engine.pathways.incineration import IncinerationParams, simulate_incineration


# ---------------------------------------------------------------------------
# Shared Feedstock fixtures
# ---------------------------------------------------------------------------

def _fs_default() -> Feedstock:
    """Standard 1000 kg/d feedstock matching the reference calculation."""
    return Feedstock(
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


def _fs_dry() -> Feedstock:
    """Low-moisture feedstock for incineration / net-positive tests."""
    return Feedstock(
        total_mass_kg_d=1000.0,
        organic_fraction=0.10,
        plastic_fraction=0.45,
        paper_fraction=0.25,
        other_fraction=0.20,
        moisture_fraction=0.15,
        ash_fraction_dry=0.08,
        lhv_dry_mj_per_kg=18.0,
        contamination_pct=3.0,
    )


# ===========================================================================
# CompostingParams validation
# ===========================================================================

class TestCompostingParams(unittest.TestCase):

    def test_defaults_construct(self):
        p = CompostingParams()
        self.assertEqual(p.vs_loss_fraction, 0.50)
        self.assertEqual(p.target_moisture, 0.40)
        self.assertEqual(p.aeration_kwh_per_t, 30.0)
        self.assertEqual(p.ch4_kg_per_t, 4.0)
        self.assertEqual(p.n2o_kg_per_t, 0.3)

    def test_frozen(self):
        import dataclasses
        p = CompostingParams()
        with self.assertRaises((dataclasses.FrozenInstanceError, TypeError, AttributeError)):
            p.vs_loss_fraction = 0.9  # type: ignore[misc]

    def test_vs_loss_zero_raises(self):
        with self.assertRaises(ValueError):
            CompostingParams(vs_loss_fraction=0.0)

    def test_vs_loss_above_one_raises(self):
        with self.assertRaises(ValueError):
            CompostingParams(vs_loss_fraction=1.01)

    def test_target_moisture_one_raises(self):
        with self.assertRaises(ValueError):
            CompostingParams(target_moisture=1.0)

    def test_negative_aeration_raises(self):
        with self.assertRaises(ValueError):
            CompostingParams(aeration_kwh_per_t=-1.0)

    def test_negative_ch4_factor_raises(self):
        with self.assertRaises(ValueError):
            CompostingParams(ch4_kg_per_t=-0.1)

    def test_negative_n2o_factor_raises(self):
        with self.assertRaises(ValueError):
            CompostingParams(n2o_kg_per_t=-0.01)


# ===========================================================================
# simulate_composting — structure and sanity
# ===========================================================================

class TestSimulateCompostingStructure(unittest.TestCase):

    def test_returns_dict(self):
        r = simulate_composting(_fs_default())
        self.assertIsInstance(r, dict)

    def test_required_keys_present(self):
        r = simulate_composting(_fs_default())
        for key in ("compost_kg_d", "mass_loss_kg_d", "aux_kwh_d",
                    "ch4_kg_d", "n2o_kg_d", "e_net_kwh_d",
                    "warnings", "status"):
            self.assertIn(key, r, msg=f"Missing key: {key}")

    def test_status_is_illustrative_estimate(self):
        self.assertEqual(simulate_composting(_fs_default())["status"], "illustrative_estimate")

    def test_warnings_is_list_of_str(self):
        r = simulate_composting(_fs_default())
        self.assertIsInstance(r["warnings"], list)
        for w in r["warnings"]:
            self.assertIsInstance(w, str)

    def test_e_net_is_negative(self):
        # composting has no energy product — e_net must be <= 0
        r = simulate_composting(_fs_default())
        self.assertLessEqual(r["e_net_kwh_d"], 0.0)

    def test_e_net_equals_negative_aux(self):
        r = simulate_composting(_fs_default())
        self.assertAlmostEqual(r["e_net_kwh_d"], -r["aux_kwh_d"], places=10)


class TestSimulateCompostingMassSanity(unittest.TestCase):

    def test_compost_le_input_default(self):
        r = simulate_composting(_fs_default())
        self.assertLessEqual(r["compost_kg_d"], _fs_default().total_mass_kg_d)

    def test_compost_le_input_high_organic(self):
        # High organic, high moisture — compost should still be <= input
        fs = Feedstock(
            total_mass_kg_d=500.0,
            organic_fraction=0.70,
            plastic_fraction=0.10,
            paper_fraction=0.10,
            other_fraction=0.10,
            moisture_fraction=0.60,
            ash_fraction_dry=0.05,
            lhv_dry_mj_per_kg=8.0,
            contamination_pct=5.0,
        )
        r = simulate_composting(fs)
        self.assertLessEqual(r["compost_kg_d"], fs.total_mass_kg_d + 1e-9)

    def test_mass_loss_plus_compost_equals_input(self):
        # mass_loss_kg_d = M - compost_kg_d
        r = simulate_composting(_fs_default())
        self.assertAlmostEqual(
            r["compost_kg_d"] + r["mass_loss_kg_d"],
            _fs_default().total_mass_kg_d,
            places=10,
        )

    def test_zero_input_gives_zero_outputs(self):
        fs = Feedstock(
            total_mass_kg_d=0.0,
            organic_fraction=0.50,
            plastic_fraction=0.20,
            paper_fraction=0.15,
            other_fraction=0.15,
            moisture_fraction=0.55,
            ash_fraction_dry=0.05,
            lhv_dry_mj_per_kg=12.0,
            contamination_pct=5.0,
        )
        r = simulate_composting(fs)
        self.assertEqual(r["compost_kg_d"], 0.0)
        self.assertEqual(r["aux_kwh_d"], 0.0)
        self.assertEqual(r["ch4_kg_d"], 0.0)
        self.assertEqual(r["n2o_kg_d"], 0.0)


class TestSimulateCompostingReference(unittest.TestCase):
    """Hand-computed reference for 1000 kg/d with all defaults.

    M = 1000, w = 0.55, organic_fraction = 0.50
    vs_loss_fraction = 0.50, target_moisture = 0.40
    aeration_kwh_per_t = 30, ch4_kg_per_t = 4, n2o_kg_per_t = 0.3

    dry_in         = 1000 * (1 - 0.55)       = 450.0 kg/d
    organic_dry    = 1000 * 0.50 * (1-0.55)  = 225.0 kg/d
    vs_loss        = 0.50 * 225.0            = 112.5 kg/d
    dry_out        = 450.0 - 112.5          = 337.5 kg/d
    compost_kg_d   = 337.5 / (1 - 0.40)     = 337.5 / 0.60 = 562.5 kg/d
    mass_loss_kg_d = 1000 - 562.5           = 437.5 kg/d
    aux_kwh_d      = 30 * 1000/1000         = 30.0 kWh/d
    e_net_kwh_d    = -30.0 kWh/d
    ch4_kg_d       = 4 * 1000/1000         = 4.0 kg/d
    n2o_kg_d       = 0.3 * 1000/1000       = 0.3 kg/d
    """

    def setUp(self):
        self.r = simulate_composting(_fs_default())

    def test_compost_kg_d(self):
        self.assertAlmostEqual(self.r["compost_kg_d"], 562.5, places=6)

    def test_mass_loss_kg_d(self):
        self.assertAlmostEqual(self.r["mass_loss_kg_d"], 437.5, places=6)

    def test_aux_kwh_d(self):
        self.assertAlmostEqual(self.r["aux_kwh_d"], 30.0, places=6)

    def test_e_net_kwh_d(self):
        self.assertAlmostEqual(self.r["e_net_kwh_d"], -30.0, places=6)

    def test_ch4_kg_d(self):
        self.assertAlmostEqual(self.r["ch4_kg_d"], 4.0, places=6)

    def test_n2o_kg_d(self):
        self.assertAlmostEqual(self.r["n2o_kg_d"], 0.3, places=6)


class TestSimulateCompostingWarnings(unittest.TestCase):

    def test_warn_when_compost_exceeds_input(self):
        # Contrive: very low vs_loss + very low target_moisture + very wet input
        # dry_in = 1000*0.05 = 50; vs_loss = 0.01*50*0.05 ≈ tiny; dry_out ≈ 50
        # compost = 50/(1-0.01) ≈ 50.5 < 1000 → need compost > M
        # Make moisture near 0, vs_loss tiny, target_moisture near 0 too:
        # dry_in=1000*0.99=990; vs_loss=0.01*990*0.80=7.92; dry_out=982.08
        # compost=982.08/(1-0.01)=992.0 < 1000 still...
        # Use target_moisture=0.0, vs_loss=0.001 → compost≈dry_in ≈ M*(1-w)
        # Need compost > M → dry_out/(1-tm) > M → dry_out > M*(1-tm)
        # With tm→0: dry_out ≈ M*(1-w), so need (1-w) > 1 → impossible.
        # Warning fires only when compost_kg_d > M which requires tm so high
        # that 1-tm < (1-vs_loss)*organic_frac_dry_contribution / (1-w).
        # Use: M=1000,w=0.10,organic=0.90,vs_loss=0.001,target_moisture=0.001
        # dry_in=900; organic_dry=900*0.90=810; vs_loss=0.81; dry_out=899.19
        # compost=899.19/(1-0.001)=899.19/0.999=899.19*1.001...=900.09 < 1000
        # Actually compost > M only when target_moisture is very high:
        # compost = dry_out/(1-tm) > M → dry_out > M*(1-tm)
        # 900*(1-eps) > 1000*(1-0.91) = 90 → trivially true but still < 1000
        # Proper trigger: target_moisture=0.95 → compost=dry_out/0.05
        # dry_in=450, vs_loss=0.50*225=112.5, dry_out=337.5
        # compost=337.5/0.05=6750 >> 1000 ✓
        p = CompostingParams(target_moisture=0.95)
        r = simulate_composting(_fs_default(), p)
        self.assertTrue(any("compost" in w for w in r["warnings"]))


# ===========================================================================
# IncinerationParams validation
# ===========================================================================

class TestIncinerationParams(unittest.TestCase):

    def test_defaults_construct(self):
        p = IncinerationParams()
        self.assertEqual(p.eta_el, 0.22)
        self.assertEqual(p.aux_kwh_per_t, 70.0)
        self.assertEqual(p.carbon_content_plastic, 0.75)

    def test_frozen(self):
        import dataclasses
        p = IncinerationParams()
        with self.assertRaises((dataclasses.FrozenInstanceError, TypeError, AttributeError)):
            p.eta_el = 0.5  # type: ignore[misc]

    def test_eta_el_zero_raises(self):
        with self.assertRaises(ValueError):
            IncinerationParams(eta_el=0.0)

    def test_eta_el_above_one_raises(self):
        with self.assertRaises(ValueError):
            IncinerationParams(eta_el=1.01)

    def test_negative_aux_raises(self):
        with self.assertRaises(ValueError):
            IncinerationParams(aux_kwh_per_t=-1.0)

    def test_carbon_content_above_one_raises(self):
        with self.assertRaises(ValueError):
            IncinerationParams(carbon_content_plastic=1.01)

    def test_carbon_content_negative_raises(self):
        with self.assertRaises(ValueError):
            IncinerationParams(carbon_content_plastic=-0.1)


# ===========================================================================
# simulate_incineration — structure and sanity
# ===========================================================================

class TestSimulateIncinerationStructure(unittest.TestCase):

    def test_returns_dict(self):
        self.assertIsInstance(simulate_incineration(_fs_dry()), dict)

    def test_required_keys_present(self):
        r = simulate_incineration(_fs_dry())
        for key in ("e_thermal_kwh_d", "e_gross_kwh_d", "aux_kwh_d",
                    "e_net_kwh_d", "ash_kg_d", "co2_fossil_kg_d",
                    "warnings", "status"):
            self.assertIn(key, r, msg=f"Missing key: {key}")

    def test_status_is_illustrative_estimate(self):
        self.assertEqual(simulate_incineration(_fs_dry())["status"], "illustrative_estimate")

    def test_warnings_is_list_of_str(self):
        r = simulate_incineration(_fs_dry())
        self.assertIsInstance(r["warnings"], list)
        for w in r["warnings"]:
            self.assertIsInstance(w, str)

    def test_gross_le_thermal(self):
        r = simulate_incineration(_fs_dry())
        self.assertLessEqual(r["e_gross_kwh_d"], r["e_thermal_kwh_d"] + 1e-9)

    def test_e_net_equals_gross_minus_aux(self):
        r = simulate_incineration(_fs_dry())
        self.assertAlmostEqual(
            r["e_net_kwh_d"], r["e_gross_kwh_d"] - r["aux_kwh_d"], places=10
        )


class TestSimulateIncinerationEnergy(unittest.TestCase):

    def test_net_rises_with_lhv(self):
        # Higher LHV dry → higher e_net
        fs_lo = Feedstock(
            total_mass_kg_d=1000.0,
            organic_fraction=0.10, plastic_fraction=0.45,
            paper_fraction=0.25, other_fraction=0.20,
            moisture_fraction=0.15, ash_fraction_dry=0.08,
            lhv_dry_mj_per_kg=10.0, contamination_pct=3.0,
        )
        fs_hi = Feedstock(
            total_mass_kg_d=1000.0,
            organic_fraction=0.10, plastic_fraction=0.45,
            paper_fraction=0.25, other_fraction=0.20,
            moisture_fraction=0.15, ash_fraction_dry=0.08,
            lhv_dry_mj_per_kg=20.0, contamination_pct=3.0,
        )
        r_lo = simulate_incineration(fs_lo)
        r_hi = simulate_incineration(fs_hi)
        self.assertGreater(r_hi["e_net_kwh_d"], r_lo["e_net_kwh_d"])

    def test_net_falls_with_moisture(self):
        # Same dry LHV; more moisture → lower lhv_wet → lower e_net
        fs_lo_w = Feedstock(
            total_mass_kg_d=1000.0,
            organic_fraction=0.10, plastic_fraction=0.45,
            paper_fraction=0.25, other_fraction=0.20,
            moisture_fraction=0.10, ash_fraction_dry=0.05,
            lhv_dry_mj_per_kg=15.0, contamination_pct=3.0,
        )
        fs_hi_w = Feedstock(
            total_mass_kg_d=1000.0,
            organic_fraction=0.10, plastic_fraction=0.45,
            paper_fraction=0.25, other_fraction=0.20,
            moisture_fraction=0.40, ash_fraction_dry=0.05,
            lhv_dry_mj_per_kg=15.0, contamination_pct=3.0,
        )
        r_lo = simulate_incineration(fs_lo_w)
        r_hi = simulate_incineration(fs_hi_w)
        self.assertGreater(r_lo["e_net_kwh_d"], r_hi["e_net_kwh_d"])

    def test_zero_lhv_gives_zero_gross(self):
        # lhv_dry=0 → lhv_wet=0 → e_thermal=0, e_gross=0
        fs = Feedstock(
            total_mass_kg_d=1000.0,
            organic_fraction=0.50, plastic_fraction=0.20,
            paper_fraction=0.15, other_fraction=0.15,
            moisture_fraction=0.55, ash_fraction_dry=0.05,
            lhv_dry_mj_per_kg=0.0, contamination_pct=5.0,
        )
        r = simulate_incineration(fs)
        self.assertEqual(r["e_gross_kwh_d"], 0.0)
        self.assertEqual(r["e_thermal_kwh_d"], 0.0)
        self.assertLessEqual(r["e_net_kwh_d"], 0.0)

    def test_zero_input_gives_zero_energy(self):
        fs = Feedstock(
            total_mass_kg_d=0.0,
            organic_fraction=0.50, plastic_fraction=0.20,
            paper_fraction=0.15, other_fraction=0.15,
            moisture_fraction=0.55, ash_fraction_dry=0.05,
            lhv_dry_mj_per_kg=12.0, contamination_pct=5.0,
        )
        r = simulate_incineration(fs)
        self.assertEqual(r["e_thermal_kwh_d"], 0.0)
        self.assertEqual(r["e_gross_kwh_d"], 0.0)
        self.assertEqual(r["aux_kwh_d"], 0.0)
        self.assertEqual(r["e_net_kwh_d"], 0.0)


class TestSimulateIncinerationAsh(unittest.TestCase):

    def test_ash_within_mass_balance(self):
        # ash_kg_d <= M * (1-moisture) since ash_fraction_dry <= 1
        fs = _fs_dry()
        r = simulate_incineration(fs)
        max_ash = fs.total_mass_kg_d * (1.0 - fs.moisture_fraction)
        self.assertLessEqual(r["ash_kg_d"], max_ash + 1e-9)

    def test_ash_zero_when_ash_fraction_zero(self):
        fs = Feedstock(
            total_mass_kg_d=1000.0,
            organic_fraction=0.50, plastic_fraction=0.20,
            paper_fraction=0.15, other_fraction=0.15,
            moisture_fraction=0.30, ash_fraction_dry=0.0,
            lhv_dry_mj_per_kg=12.0, contamination_pct=5.0,
        )
        r = simulate_incineration(fs)
        self.assertEqual(r["ash_kg_d"], 0.0)

    def test_ash_scales_with_mass(self):
        fs_lo = Feedstock(
            total_mass_kg_d=500.0,
            organic_fraction=0.50, plastic_fraction=0.20,
            paper_fraction=0.15, other_fraction=0.15,
            moisture_fraction=0.30, ash_fraction_dry=0.10,
            lhv_dry_mj_per_kg=12.0, contamination_pct=5.0,
        )
        fs_hi = Feedstock(
            total_mass_kg_d=1000.0,
            organic_fraction=0.50, plastic_fraction=0.20,
            paper_fraction=0.15, other_fraction=0.15,
            moisture_fraction=0.30, ash_fraction_dry=0.10,
            lhv_dry_mj_per_kg=12.0, contamination_pct=5.0,
        )
        self.assertAlmostEqual(
            simulate_incineration(fs_hi)["ash_kg_d"],
            2.0 * simulate_incineration(fs_lo)["ash_kg_d"],
            places=10,
        )


class TestSimulateIncinerationReference(unittest.TestCase):
    """Hand-computed reference for 1000 kg/d with default parameters.

    Feedstock: M=1000, moisture=0.55, lhv_dry=12.0, plastic=0.20, ash_dry=0.05
    Params:    eta_el=0.22, aux_kwh_per_t=70, carbon_content_plastic=0.75

    lhv_wet          = 12.0*(1-0.55) - 2.44*0.55 = 5.4 - 1.342 = 4.058 MJ/kg
    e_thermal_kwh_d  = 1000 * 4.058 / 3.6        = 1127.2222... kWh/d
    e_gross_kwh_d    = 1127.2222 * 0.22           = 247.9888... kWh/d
    aux_kwh_d        = 70 * 1000/1000             = 70.0 kWh/d
    e_net_kwh_d      = 247.9888 - 70.0            = 177.9888... kWh/d
    ash_kg_d         = 1000 * (1-0.55) * 0.05     = 1000*0.45*0.05 = 22.5 kg/d
    co2_fossil_kg_d  = 1000*0.20*0.75*(44/12)     = 150*(44/12) = 550.0 kg/d
    """

    def setUp(self):
        self.r = simulate_incineration(_fs_default())

    def test_lhv_wet(self):
        expected = 12.0 * 0.45 - 2.44 * 0.55  # = 4.058
        self.assertAlmostEqual(_fs_default().lhv_wet_mj_per_kg(), expected, places=10)

    def test_e_thermal_kwh_d(self):
        # 1000 * 4.058 / 3.6 = 1127.222...
        expected = 1000.0 * (12.0 * 0.45 - 2.44 * 0.55) / 3.6
        self.assertAlmostEqual(self.r["e_thermal_kwh_d"], expected, places=6)

    def test_e_gross_kwh_d(self):
        # 1127.222... * 0.22
        expected = 1000.0 * (12.0 * 0.45 - 2.44 * 0.55) / 3.6 * 0.22
        self.assertAlmostEqual(self.r["e_gross_kwh_d"], expected, places=6)

    def test_aux_kwh_d(self):
        self.assertAlmostEqual(self.r["aux_kwh_d"], 70.0, places=6)

    def test_e_net_kwh_d(self):
        expected = 1000.0 * (12.0 * 0.45 - 2.44 * 0.55) / 3.6 * 0.22 - 70.0
        self.assertAlmostEqual(self.r["e_net_kwh_d"], expected, places=6)

    def test_ash_kg_d(self):
        # 1000 * 0.45 * 0.05 = 22.5
        self.assertAlmostEqual(self.r["ash_kg_d"], 22.5, places=6)

    def test_co2_fossil_kg_d(self):
        # 1000 * 0.20 * 0.75 * (44/12) = 550.0
        expected = 1000.0 * 0.20 * 0.75 * (44.0 / 12.0)
        self.assertAlmostEqual(self.r["co2_fossil_kg_d"], expected, places=6)


class TestSimulateIncinerationWarnings(unittest.TestCase):

    def test_warn_when_e_net_nonpositive(self):
        # Zero LHV → e_gross=0, aux>0 → e_net < 0 → warning
        fs = Feedstock(
            total_mass_kg_d=1000.0,
            organic_fraction=0.50, plastic_fraction=0.20,
            paper_fraction=0.15, other_fraction=0.15,
            moisture_fraction=0.55, ash_fraction_dry=0.05,
            lhv_dry_mj_per_kg=0.0, contamination_pct=5.0,
        )
        r = simulate_incineration(fs)
        self.assertTrue(any("e_net" in w for w in r["warnings"]))

    def test_no_warning_when_net_positive(self):
        # Dry, high-LHV feedstock → net positive → no warning
        r = simulate_incineration(_fs_dry())
        self.assertFalse(any("e_net" in w for w in r["warnings"]))


if __name__ == "__main__":
    unittest.main()
