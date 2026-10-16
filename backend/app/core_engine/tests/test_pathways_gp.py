"""CI tests for gasification and pyrolysis pathway models."""
import unittest

from app.core_engine.pathways.feedstock import Feedstock
from app.core_engine.pathways.gasification import GasificationParams, simulate_gasification
from app.core_engine.pathways.pyrolysis import PyrolysisParams, simulate_pyrolysis


# ---------------------------------------------------------------------------
# Shared Feedstock fixtures
# ---------------------------------------------------------------------------

def _fs_dry() -> Feedstock:
    """1000 kg/d, moisture=0.10 — below both gasification (0.15) and pyrolysis (0.20) targets."""
    return Feedstock(
        total_mass_kg_d=1000.0,
        organic_fraction=0.10,
        plastic_fraction=0.45,
        paper_fraction=0.25,
        other_fraction=0.20,
        moisture_fraction=0.10,
        ash_fraction_dry=0.08,
        lhv_dry_mj_per_kg=15.0,
        contamination_pct=3.0,
    )


def _fs_wet() -> Feedstock:
    """1000 kg/d, moisture=0.55 — above both targets; triggers drying load."""
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


def _fs_zero() -> Feedstock:
    """Zero-mass feedstock — must give zero outputs, not errors."""
    return Feedstock(
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


# ===========================================================================
# GasificationParams validation
# ===========================================================================

class TestGasificationParams(unittest.TestCase):

    def test_defaults_construct(self):
        p = GasificationParams()
        self.assertEqual(p.cold_gas_efficiency, 0.70)
        self.assertEqual(p.eta_engine, 0.30)
        self.assertEqual(p.aux_kwh_per_t, 100.0)
        self.assertEqual(p.target_moisture, 0.15)

    def test_frozen(self):
        import dataclasses
        p = GasificationParams()
        with self.assertRaises((dataclasses.FrozenInstanceError, TypeError, AttributeError)):
            p.eta_engine = 0.5  # type: ignore[misc]

    def test_cold_gas_efficiency_zero_raises(self):
        with self.assertRaises(ValueError):
            GasificationParams(cold_gas_efficiency=0.0)

    def test_cold_gas_efficiency_above_one_raises(self):
        with self.assertRaises(ValueError):
            GasificationParams(cold_gas_efficiency=1.01)

    def test_eta_engine_zero_raises(self):
        with self.assertRaises(ValueError):
            GasificationParams(eta_engine=0.0)

    def test_eta_engine_above_one_raises(self):
        with self.assertRaises(ValueError):
            GasificationParams(eta_engine=1.01)

    def test_negative_aux_raises(self):
        with self.assertRaises(ValueError):
            GasificationParams(aux_kwh_per_t=-1.0)

    def test_target_moisture_one_raises(self):
        with self.assertRaises(ValueError):
            GasificationParams(target_moisture=1.0)

    def test_target_moisture_negative_raises(self):
        with self.assertRaises(ValueError):
            GasificationParams(target_moisture=-0.01)


# ===========================================================================
# simulate_gasification — structure
# ===========================================================================

class TestSimulateGasificationStructure(unittest.TestCase):

    def test_returns_dict(self):
        self.assertIsInstance(simulate_gasification(_fs_dry()), dict)

    def test_required_keys_present(self):
        r = simulate_gasification(_fs_dry())
        for key in ("dry_kg_d", "drying_kwh_d", "syngas_energy_kwh_d",
                    "e_gross_kwh_d", "aux_kwh_d", "e_net_kwh_d",
                    "char_kg_d", "warnings", "status"):
            self.assertIn(key, r, msg=f"Missing key: {key}")

    def test_status(self):
        self.assertEqual(simulate_gasification(_fs_dry())["status"], "illustrative_estimate")

    def test_warnings_list_of_str(self):
        r = simulate_gasification(_fs_dry())
        self.assertIsInstance(r["warnings"], list)
        for w in r["warnings"]:
            self.assertIsInstance(w, str)

    def test_e_net_equals_gross_minus_aux_minus_drying(self):
        r = simulate_gasification(_fs_dry())
        expected = r["e_gross_kwh_d"] - r["aux_kwh_d"] - r["drying_kwh_d"]
        self.assertAlmostEqual(r["e_net_kwh_d"], expected, places=10)

    def test_gross_le_syngas_energy(self):
        r = simulate_gasification(_fs_dry())
        self.assertLessEqual(r["e_gross_kwh_d"], r["syngas_energy_kwh_d"] + 1e-9)


# ===========================================================================
# simulate_gasification — negative input raises
# ===========================================================================

class TestSimulateGasificationNegativeInput(unittest.TestCase):

    def test_negative_total_mass_raises(self):
        # Feedstock itself rejects negative mass
        with self.assertRaises(ValueError):
            Feedstock(
                total_mass_kg_d=-1.0,
                organic_fraction=0.50, plastic_fraction=0.20,
                paper_fraction=0.15, other_fraction=0.15,
                moisture_fraction=0.10, ash_fraction_dry=0.05,
                lhv_dry_mj_per_kg=15.0, contamination_pct=3.0,
            )

    def test_bad_params_raise(self):
        with self.assertRaises(ValueError):
            GasificationParams(cold_gas_efficiency=-0.1)


# ===========================================================================
# simulate_gasification — zero mass gives zeros
# ===========================================================================

class TestSimulateGasificationZeroMass(unittest.TestCase):

    def test_zero_mass_gives_zero_dry(self):
        r = simulate_gasification(_fs_zero())
        self.assertEqual(r["dry_kg_d"], 0.0)

    def test_zero_mass_gives_zero_syngas(self):
        r = simulate_gasification(_fs_zero())
        self.assertEqual(r["syngas_energy_kwh_d"], 0.0)

    def test_zero_mass_gives_zero_aux(self):
        r = simulate_gasification(_fs_zero())
        self.assertEqual(r["aux_kwh_d"], 0.0)

    def test_zero_mass_gives_zero_char(self):
        r = simulate_gasification(_fs_zero())
        self.assertEqual(r["char_kg_d"], 0.0)


# ===========================================================================
# simulate_gasification — net energy falls as moisture rises
# ===========================================================================

class TestSimulateGasificationMoistureEffect(unittest.TestCase):

    def _make_fs(self, moisture: float) -> Feedstock:
        return Feedstock(
            total_mass_kg_d=1000.0,
            organic_fraction=0.10, plastic_fraction=0.45,
            paper_fraction=0.25, other_fraction=0.20,
            moisture_fraction=moisture,
            ash_fraction_dry=0.08,
            lhv_dry_mj_per_kg=15.0,
            contamination_pct=3.0,
        )

    def test_net_falls_as_moisture_rises(self):
        r_dry = simulate_gasification(self._make_fs(0.10))
        r_wet = simulate_gasification(self._make_fs(0.50))
        self.assertGreater(r_dry["e_net_kwh_d"], r_wet["e_net_kwh_d"])

    def test_drying_zero_when_at_or_below_target(self):
        r = simulate_gasification(self._make_fs(0.15))  # exactly at default target
        self.assertEqual(r["drying_kwh_d"], 0.0)

    def test_drying_positive_when_above_target(self):
        r = simulate_gasification(self._make_fs(0.40))
        self.assertGreater(r["drying_kwh_d"], 0.0)

    def test_warn_when_above_target_moisture(self):
        r = simulate_gasification(self._make_fs(0.40))
        self.assertTrue(any("moisture" in w for w in r["warnings"]))

    def test_no_moisture_warn_when_below_target(self):
        r = simulate_gasification(self._make_fs(0.10))
        self.assertFalse(any("moisture" in w for w in r["warnings"]))

    def test_warn_when_e_net_nonpositive(self):
        # Zero LHV → no syngas energy → e_net < 0
        fs = Feedstock(
            total_mass_kg_d=1000.0,
            organic_fraction=0.50, plastic_fraction=0.20,
            paper_fraction=0.15, other_fraction=0.15,
            moisture_fraction=0.10, ash_fraction_dry=0.05,
            lhv_dry_mj_per_kg=0.0, contamination_pct=5.0,
        )
        r = simulate_gasification(fs)
        self.assertTrue(any("e_net" in w for w in r["warnings"]))


# ===========================================================================
# simulate_gasification — hand-computed reference
# ===========================================================================

class TestSimulateGasificationReference(unittest.TestCase):
    """Reference: 1000 kg/d, moisture=0.10, lhv_dry=15.0, ash_dry=0.08.
    Params: cold_gas_efficiency=0.70, eta_engine=0.30, aux_kwh_per_t=100, target_moisture=0.15

    moisture=0.10 < target=0.15  → no drying
    dry_kg_d            = 1000 * (1 - 0.10)           = 900.0 kg/d
    drying_kwh_d        = 0.0
    syngas_energy_kwh_d = 900 * 15.0 / 3.6 * 0.70    = 900 * 4.16667 * 0.70
                        = 900 * 2.91667 = 2625.0 kWh/d
    e_gross_kwh_d       = 2625.0 * 0.30               = 787.5 kWh/d
    aux_kwh_d           = 100 * 1000/1000              = 100.0 kWh/d
    e_net_kwh_d         = 787.5 - 100.0 - 0.0         = 687.5 kWh/d
    char_kg_d           = 900 * 0.08 * 1.5            = 108.0 kg/d
    """

    def setUp(self):
        self.r = simulate_gasification(_fs_dry())

    def test_dry_kg_d(self):
        self.assertAlmostEqual(self.r["dry_kg_d"], 900.0, places=6)

    def test_drying_kwh_d(self):
        self.assertAlmostEqual(self.r["drying_kwh_d"], 0.0, places=6)

    def test_syngas_energy_kwh_d(self):
        # 900 * 15.0 / 3.6 * 0.70
        expected = 900.0 * 15.0 / 3.6 * 0.70
        self.assertAlmostEqual(self.r["syngas_energy_kwh_d"], expected, places=6)

    def test_e_gross_kwh_d(self):
        expected = 900.0 * 15.0 / 3.6 * 0.70 * 0.30
        self.assertAlmostEqual(self.r["e_gross_kwh_d"], expected, places=6)

    def test_aux_kwh_d(self):
        self.assertAlmostEqual(self.r["aux_kwh_d"], 100.0, places=6)

    def test_e_net_kwh_d(self):
        expected = 900.0 * 15.0 / 3.6 * 0.70 * 0.30 - 100.0
        self.assertAlmostEqual(self.r["e_net_kwh_d"], expected, places=6)

    def test_char_kg_d(self):
        # 900 * 0.08 * 1.5 = 108.0
        self.assertAlmostEqual(self.r["char_kg_d"], 108.0, places=6)


# ===========================================================================
# PyrolysisParams validation
# ===========================================================================

class TestPyrolysisParams(unittest.TestCase):

    def test_defaults_construct(self):
        p = PyrolysisParams()
        self.assertEqual(p.oil_yield, 0.40)
        self.assertEqual(p.char_yield, 0.30)
        self.assertEqual(p.gas_yield, 0.30)
        self.assertEqual(p.cp_kj_kg_k, 1.5)
        self.assertEqual(p.delta_t_k, 450.0)
        self.assertEqual(p.target_moisture, 0.20)

    def test_frozen(self):
        import dataclasses
        p = PyrolysisParams()
        with self.assertRaises((dataclasses.FrozenInstanceError, TypeError, AttributeError)):
            p.oil_yield = 0.5  # type: ignore[misc]

    def test_yields_sum_to_one(self):
        # Good: exactly 1.0
        p = PyrolysisParams(oil_yield=0.50, char_yield=0.30, gas_yield=0.20)
        self.assertAlmostEqual(p.oil_yield + p.char_yield + p.gas_yield, 1.0)

    def test_yields_not_summing_to_one_raises(self):
        with self.assertRaises(ValueError):
            PyrolysisParams(oil_yield=0.50, char_yield=0.30, gas_yield=0.30)  # sum = 1.10

    def test_yields_summing_too_low_raises(self):
        with self.assertRaises(ValueError):
            PyrolysisParams(oil_yield=0.30, char_yield=0.20, gas_yield=0.20)  # sum = 0.70

    def test_yield_negative_raises(self):
        with self.assertRaises(ValueError):
            PyrolysisParams(oil_yield=-0.1, char_yield=0.60, gas_yield=0.50)

    def test_negative_cp_raises(self):
        with self.assertRaises(ValueError):
            PyrolysisParams(cp_kj_kg_k=-0.1)

    def test_negative_delta_t_raises(self):
        with self.assertRaises(ValueError):
            PyrolysisParams(delta_t_k=-1.0)

    def test_target_moisture_one_raises(self):
        with self.assertRaises(ValueError):
            PyrolysisParams(target_moisture=1.0)


# ===========================================================================
# simulate_pyrolysis — structure
# ===========================================================================

class TestSimulatePyrolysisStructure(unittest.TestCase):

    def test_returns_dict(self):
        self.assertIsInstance(simulate_pyrolysis(_fs_dry()), dict)

    def test_required_keys_present(self):
        r = simulate_pyrolysis(_fs_dry())
        for key in ("dry_kg_d", "drying_kwh_d", "oil_kg_d", "char_kg_d",
                    "gas_kg_d", "product_energy_kwh_d", "process_heat_kwh_d",
                    "e_net_energy_kwh_d", "warnings", "status"):
            self.assertIn(key, r, msg=f"Missing key: {key}")

    def test_status(self):
        self.assertEqual(simulate_pyrolysis(_fs_dry())["status"], "illustrative_estimate")

    def test_warnings_list_of_str(self):
        r = simulate_pyrolysis(_fs_dry())
        self.assertIsInstance(r["warnings"], list)
        for w in r["warnings"]:
            self.assertIsInstance(w, str)

    def test_e_net_equals_product_minus_process(self):
        r = simulate_pyrolysis(_fs_dry())
        self.assertAlmostEqual(
            r["e_net_energy_kwh_d"],
            r["product_energy_kwh_d"] - r["process_heat_kwh_d"],
            places=10,
        )

    def test_product_masses_sum_to_dry(self):
        r = simulate_pyrolysis(_fs_dry())
        self.assertAlmostEqual(
            r["oil_kg_d"] + r["char_kg_d"] + r["gas_kg_d"],
            r["dry_kg_d"],
            places=10,
        )


# ===========================================================================
# simulate_pyrolysis — negative input raises
# ===========================================================================

class TestSimulatePyrolysisNegativeInput(unittest.TestCase):

    def test_negative_total_mass_rejected_by_feedstock(self):
        with self.assertRaises(ValueError):
            Feedstock(
                total_mass_kg_d=-1.0,
                organic_fraction=0.50, plastic_fraction=0.20,
                paper_fraction=0.15, other_fraction=0.15,
                moisture_fraction=0.10, ash_fraction_dry=0.05,
                lhv_dry_mj_per_kg=15.0, contamination_pct=3.0,
            )

    def test_bad_yields_raise(self):
        with self.assertRaises(ValueError):
            PyrolysisParams(oil_yield=0.60, char_yield=0.30, gas_yield=0.30)


# ===========================================================================
# simulate_pyrolysis — zero mass gives zeros, not errors
# ===========================================================================

class TestSimulatePyrolysisZeroMass(unittest.TestCase):

    def test_zero_mass_dry_kg_d(self):
        self.assertEqual(simulate_pyrolysis(_fs_zero())["dry_kg_d"], 0.0)

    def test_zero_mass_product_energy(self):
        self.assertEqual(simulate_pyrolysis(_fs_zero())["product_energy_kwh_d"], 0.0)

    def test_zero_mass_oil_char_gas(self):
        r = simulate_pyrolysis(_fs_zero())
        self.assertEqual(r["oil_kg_d"], 0.0)
        self.assertEqual(r["char_kg_d"], 0.0)
        self.assertEqual(r["gas_kg_d"], 0.0)

    def test_zero_mass_no_exception(self):
        # Must not raise
        simulate_pyrolysis(_fs_zero())


# ===========================================================================
# simulate_pyrolysis — net energy falls as moisture rises
# ===========================================================================

class TestSimulatePyrolysisMoistureEffect(unittest.TestCase):

    def _make_fs(self, moisture: float) -> Feedstock:
        return Feedstock(
            total_mass_kg_d=1000.0,
            organic_fraction=0.10, plastic_fraction=0.45,
            paper_fraction=0.25, other_fraction=0.20,
            moisture_fraction=moisture,
            ash_fraction_dry=0.08,
            lhv_dry_mj_per_kg=15.0,
            contamination_pct=3.0,
        )

    def test_net_falls_as_moisture_rises(self):
        r_dry = simulate_pyrolysis(self._make_fs(0.10))
        r_wet = simulate_pyrolysis(self._make_fs(0.50))
        self.assertGreater(r_dry["e_net_energy_kwh_d"], r_wet["e_net_energy_kwh_d"])

    def test_drying_zero_when_at_target(self):
        r = simulate_pyrolysis(self._make_fs(0.20))  # exactly at default target
        self.assertEqual(r["drying_kwh_d"], 0.0)

    def test_drying_positive_when_above_target(self):
        r = simulate_pyrolysis(self._make_fs(0.40))
        self.assertGreater(r["drying_kwh_d"], 0.0)

    def test_warn_when_above_target_moisture(self):
        r = simulate_pyrolysis(self._make_fs(0.40))
        self.assertTrue(any("moisture" in w for w in r["warnings"]))

    def test_warn_when_e_net_nonpositive(self):
        # Very wet + extreme delta_t → huge process heat dominates product energy → e_net < 0
        # dry_kg_d=450, product LHVs fixed (40/25/15 MJ/kg), product_energy≈3500 kWh/d
        # process_heat = 450*1.5*20000/3600 + drying ≈ 3750+275=4025 > 3500 → e_net < 0
        fs = Feedstock(
            total_mass_kg_d=1000.0,
            organic_fraction=0.50, plastic_fraction=0.20,
            paper_fraction=0.15, other_fraction=0.15,
            moisture_fraction=0.55, ash_fraction_dry=0.05,
            lhv_dry_mj_per_kg=1.0, contamination_pct=5.0,
        )
        p = PyrolysisParams(delta_t_k=20000.0)
        r = simulate_pyrolysis(fs, p)
        self.assertTrue(any("e_net" in w for w in r["warnings"]))


# ===========================================================================
# simulate_pyrolysis — hand-computed reference
# ===========================================================================

class TestSimulatePyrolysisReference(unittest.TestCase):
    """Reference: 1000 kg/d, moisture=0.10, lhv_dry=15.0, ash_dry=0.08.
    Params: oil=0.40, char=0.30, gas=0.30, cp=1.5, dT=450, target_moisture=0.20

    moisture=0.10 < target=0.20  → no drying
    dry_kg_d             = 1000 * 0.90                = 900.0 kg/d
    drying_kwh_d         = 0.0
    oil_kg_d             = 900 * 0.40                 = 360.0 kg/d
    char_kg_d            = 900 * 0.30                 = 270.0 kg/d
    gas_kg_d             = 900 * 0.30                 = 270.0 kg/d
    product_energy_kwh_d = (360*40 + 270*25 + 270*15)/3.6
                         = (14400 + 6750 + 4050)/3.6
                         = 25200 / 3.6               = 7000.0 kWh/d
    process_heat_kwh_d   = 900 * 1.5 * 450 / 3600 + 0
                         = 607500 / 3600             = 168.75 kWh/d
    e_net_energy_kwh_d   = 7000.0 - 168.75           = 6831.25 kWh/d
    """

    def setUp(self):
        self.r = simulate_pyrolysis(_fs_dry())

    def test_dry_kg_d(self):
        self.assertAlmostEqual(self.r["dry_kg_d"], 900.0, places=6)

    def test_drying_kwh_d(self):
        self.assertAlmostEqual(self.r["drying_kwh_d"], 0.0, places=6)

    def test_oil_kg_d(self):
        self.assertAlmostEqual(self.r["oil_kg_d"], 360.0, places=6)

    def test_char_kg_d(self):
        self.assertAlmostEqual(self.r["char_kg_d"], 270.0, places=6)

    def test_gas_kg_d(self):
        self.assertAlmostEqual(self.r["gas_kg_d"], 270.0, places=6)

    def test_product_energy_kwh_d(self):
        # (360*40 + 270*25 + 270*15)/3.6 = 25200/3.6 = 7000.0
        self.assertAlmostEqual(self.r["product_energy_kwh_d"], 7000.0, places=6)

    def test_process_heat_kwh_d(self):
        # 900 * 1.5 * 450 / 3600 = 168.75
        self.assertAlmostEqual(self.r["process_heat_kwh_d"], 168.75, places=6)

    def test_e_net_energy_kwh_d(self):
        # 7000.0 - 168.75 = 6831.25
        self.assertAlmostEqual(self.r["e_net_energy_kwh_d"], 6831.25, places=6)


if __name__ == "__main__":
    unittest.main()
