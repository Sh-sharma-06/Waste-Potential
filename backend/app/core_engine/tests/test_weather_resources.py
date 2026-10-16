"""tests/test_weather_resources.py — unittest.TestCase tests for
pathways/weather.py and pathways/resources.py."""
import dataclasses
import unittest

from app.core_engine.pathways.feedstock import Feedstock
from app.core_engine.pathways.weather import (
    WeatherContext,
    adjust_feedstock_moisture,
    drying_energy_kwh_d,
)
from app.core_engine.pathways.resources import (
    ResourceLedger,
    ledger_from_result,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _fs() -> Feedstock:
    """Standard 1000 kg/d feedstock, moisture=0.55."""
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
    """Low-moisture feedstock, moisture=0.10."""
    return Feedstock(
        total_mass_kg_d=1000.0,
        organic_fraction=0.10,
        plastic_fraction=0.45,
        paper_fraction=0.25,
        other_fraction=0.20,
        moisture_fraction=0.10,
        ash_fraction_dry=0.08,
        lhv_dry_mj_per_kg=18.0,
        contamination_pct=3.0,
    )


def _wx_dry() -> WeatherContext:
    """Dry weather: 25 °C, 40 % RH, 0 mm/d rainfall."""
    return WeatherContext(ambient_temp_c=25.0, relative_humidity=0.40, rainfall_mm_d=0.0)


def _wx_wet() -> WeatherContext:
    """Wet weather: 30 °C, 90 % RH, 20 mm/d rainfall."""
    return WeatherContext(ambient_temp_c=30.0, relative_humidity=0.90, rainfall_mm_d=20.0)


# ===========================================================================
# TestWeatherContext
# ===========================================================================

class TestWeatherContext(unittest.TestCase):

    def test_valid_construction(self):
        wx = WeatherContext(ambient_temp_c=15.0, relative_humidity=0.60, rainfall_mm_d=5.0)
        self.assertEqual(wx.ambient_temp_c, 15.0)
        self.assertEqual(wx.relative_humidity, 0.60)
        self.assertEqual(wx.rainfall_mm_d, 5.0)

    def test_negative_ambient_temp_allowed(self):
        wx = WeatherContext(ambient_temp_c=-10.0, relative_humidity=0.50, rainfall_mm_d=0.0)
        self.assertEqual(wx.ambient_temp_c, -10.0)

    def test_zero_humidity_allowed(self):
        WeatherContext(ambient_temp_c=20.0, relative_humidity=0.0, rainfall_mm_d=0.0)

    def test_full_humidity_allowed(self):
        WeatherContext(ambient_temp_c=20.0, relative_humidity=1.0, rainfall_mm_d=0.0)

    def test_humidity_below_zero_raises(self):
        with self.assertRaises(ValueError):
            WeatherContext(ambient_temp_c=20.0, relative_humidity=-0.01, rainfall_mm_d=0.0)

    def test_humidity_above_one_raises(self):
        with self.assertRaises(ValueError):
            WeatherContext(ambient_temp_c=20.0, relative_humidity=1.01, rainfall_mm_d=0.0)

    def test_negative_rainfall_raises(self):
        with self.assertRaises(ValueError):
            WeatherContext(ambient_temp_c=20.0, relative_humidity=0.5, rainfall_mm_d=-1.0)

    def test_frozen(self):
        wx = _wx_dry()
        with self.assertRaises((dataclasses.FrozenInstanceError, TypeError, AttributeError)):
            wx.rainfall_mm_d = 10.0  # type: ignore[misc]


# ===========================================================================
# TestAdjustFeedstockMoisture
# ===========================================================================

class TestAdjustFeedstockMoisture(unittest.TestCase):

    # ------------------------------------------------------------------ #
    # disabled (default)                                                   #
    # ------------------------------------------------------------------ #

    def test_disabled_leaves_moisture_unchanged(self):
        fs = _fs()
        fs_out, note = adjust_feedstock_moisture(fs, _wx_wet(), enabled=False)
        self.assertEqual(fs_out.moisture_fraction, fs.moisture_fraction)

    def test_disabled_returns_same_feedstock_object_identity(self):
        fs = _fs()
        fs_out, _ = adjust_feedstock_moisture(fs, _wx_wet(), enabled=False)
        self.assertIs(fs_out, fs)

    def test_disabled_note_text(self):
        _, note = adjust_feedstock_moisture(_fs(), _wx_wet(), enabled=False)
        self.assertEqual(note, "weather moisture adjustment not applied")

    def test_disabled_zero_rainfall_no_change(self):
        fs = _fs()
        fs_out, _ = adjust_feedstock_moisture(fs, _wx_dry(), enabled=False)
        self.assertEqual(fs_out.moisture_fraction, fs.moisture_fraction)

    # ------------------------------------------------------------------ #
    # enabled                                                              #
    # ------------------------------------------------------------------ #

    def test_enabled_raises_moisture_with_rainfall(self):
        fs = _fs()
        fs_out, _ = adjust_feedstock_moisture(fs, _wx_wet(), enabled=True)
        self.assertGreater(fs_out.moisture_fraction, fs.moisture_fraction)

    def test_enabled_zero_rainfall_no_change(self):
        fs = _fs()
        fs_out, _ = adjust_feedstock_moisture(fs, _wx_dry(), enabled=True)
        # rainfall=0 → delta=0 → moisture unchanged
        self.assertEqual(fs_out.moisture_fraction, fs.moisture_fraction)

    def test_enabled_moisture_never_above_095(self):
        """Even with very heavy rainfall the moisture must not exceed 0.95."""
        very_wet = WeatherContext(ambient_temp_c=30.0, relative_humidity=1.0, rainfall_mm_d=500.0)
        fs_out, _ = adjust_feedstock_moisture(_fs(), very_wet, enabled=True)
        self.assertLessEqual(fs_out.moisture_fraction, 0.95)

    def test_enabled_moisture_capped_at_095(self):
        """High initial moisture + heavy rain → exactly 0.95."""
        fs_high = dataclasses.replace(_fs(), moisture_fraction=0.94)
        heavy = WeatherContext(ambient_temp_c=30.0, relative_humidity=1.0, rainfall_mm_d=1000.0)
        fs_out, _ = adjust_feedstock_moisture(fs_high, heavy, enabled=True)
        self.assertAlmostEqual(fs_out.moisture_fraction, 0.95, places=9)

    def test_enabled_note_contains_model_assumption(self):
        _, note = adjust_feedstock_moisture(_fs(), _wx_wet(), enabled=True)
        self.assertIn("MODEL ASSUMPTION", note)

    def test_enabled_note_contains_not_validated(self):
        _, note = adjust_feedstock_moisture(_fs(), _wx_wet(), enabled=True)
        self.assertIn("not validated", note)

    def test_enabled_arithmetic(self):
        """Hand-computed: moisture=0.55, rainfall=20 mm/d, sensitivity=0.05.
        delta = 0.05 * (20/10) = 0.05 * 2.0 = 0.10
        new_moisture = min(0.55 + 0.10, 0.95) = 0.65
        """
        fs = dataclasses.replace(_fs(), moisture_fraction=0.55)
        wx = WeatherContext(ambient_temp_c=25.0, relative_humidity=0.70, rainfall_mm_d=20.0)
        fs_out, _ = adjust_feedstock_moisture(fs, wx, enabled=True, sensitivity=0.05)
        self.assertAlmostEqual(fs_out.moisture_fraction, 0.65, places=10)

    def test_enabled_custom_sensitivity(self):
        """sensitivity=0.10 doubles the delta vs default 0.05."""
        fs = dataclasses.replace(_fs(), moisture_fraction=0.30)
        wx = WeatherContext(ambient_temp_c=20.0, relative_humidity=0.60, rainfall_mm_d=10.0)
        fs_out_half, _ = adjust_feedstock_moisture(fs, wx, enabled=True, sensitivity=0.05)
        fs_out_full, _ = adjust_feedstock_moisture(fs, wx, enabled=True, sensitivity=0.10)
        self.assertAlmostEqual(
            fs_out_full.moisture_fraction - fs.moisture_fraction,
            2.0 * (fs_out_half.moisture_fraction - fs.moisture_fraction),
            places=10,
        )

    def test_negative_sensitivity_raises(self):
        with self.assertRaises(ValueError):
            adjust_feedstock_moisture(_fs(), _wx_wet(), enabled=True, sensitivity=-0.01)

    def test_enabled_other_feedstock_fields_unchanged(self):
        """Adjustment must only change moisture_fraction, not other fields."""
        fs = _fs()
        fs_out, _ = adjust_feedstock_moisture(fs, _wx_wet(), enabled=True)
        self.assertEqual(fs_out.total_mass_kg_d, fs.total_mass_kg_d)
        self.assertEqual(fs_out.organic_fraction, fs.organic_fraction)
        self.assertEqual(fs_out.lhv_dry_mj_per_kg, fs.lhv_dry_mj_per_kg)
        self.assertEqual(fs_out.contamination_pct, fs.contamination_pct)

    def test_enabled_returns_valid_feedstock(self):
        """The returned Feedstock must pass its own __post_init__ validation."""
        fs_out, _ = adjust_feedstock_moisture(_fs(), _wx_wet(), enabled=True)
        self.assertIsInstance(fs_out, Feedstock)


# ===========================================================================
# TestDryingEnergyKwhD
# ===========================================================================

class TestDryingEnergyKwhD(unittest.TestCase):

    def test_zero_when_already_at_target(self):
        self.assertEqual(drying_energy_kwh_d(1000.0, 0.30, 0.30), 0.0)

    def test_zero_when_drier_than_target(self):
        """No drying needed when moisture_from < moisture_to."""
        self.assertEqual(drying_energy_kwh_d(1000.0, 0.10, 0.30), 0.0)

    def test_zero_when_zero_mass(self):
        self.assertEqual(drying_energy_kwh_d(0.0, 0.50, 0.15), 0.0)

    def test_positive_when_wetter_than_target(self):
        result = drying_energy_kwh_d(1000.0, 0.55, 0.15)
        self.assertGreater(result, 0.0)

    def test_reference_calculation(self):
        """Hand-computed reference (arithmetic in comment):
        mass = 1000 kg/d, moisture_from = 0.55, moisture_to = 0.15
        dry_mass = 1000 * (1 - 0.55) = 450 kg/d
        water_in_feed = 1000 * 0.55 = 550 kg/d
        water_at_target = 450 * 0.15 / (1 - 0.15) = 450 * 0.15 / 0.85
                        = 67.5 / 0.85 = 79.41176... kg/d
        moisture_to_remove = 550 - 79.41176... = 470.58823... kg/d
        drying_energy = 470.58823... * 2.26 / 3.6 = 295.327... kWh/d
        """
        expected = (1000.0 * 0.55 - 450.0 * 0.15 / 0.85) * 2.26 / 3.6
        result = drying_energy_kwh_d(1000.0, 0.55, 0.15)
        self.assertAlmostEqual(result, expected, places=6)

    def test_scales_linearly_with_mass(self):
        e1 = drying_energy_kwh_d(500.0, 0.50, 0.20)
        e2 = drying_energy_kwh_d(1000.0, 0.50, 0.20)
        self.assertAlmostEqual(e2, 2.0 * e1, places=10)

    def test_more_drying_needed_for_wetter_feed(self):
        e_moderate = drying_energy_kwh_d(1000.0, 0.40, 0.15)
        e_wet = drying_energy_kwh_d(1000.0, 0.60, 0.15)
        self.assertGreater(e_wet, e_moderate)

    def test_negative_mass_raises(self):
        with self.assertRaises(ValueError):
            drying_energy_kwh_d(-1.0, 0.50, 0.15)

    def test_moisture_from_at_one_raises(self):
        with self.assertRaises(ValueError):
            drying_energy_kwh_d(1000.0, 1.0, 0.15)

    def test_moisture_to_at_one_raises(self):
        with self.assertRaises(ValueError):
            drying_energy_kwh_d(1000.0, 0.50, 1.0)

    def test_moisture_from_negative_raises(self):
        with self.assertRaises(ValueError):
            drying_energy_kwh_d(1000.0, -0.01, 0.15)

    def test_moisture_to_negative_raises(self):
        with self.assertRaises(ValueError):
            drying_energy_kwh_d(1000.0, 0.50, -0.01)


# ===========================================================================
# TestResourceLedger
# ===========================================================================

class TestResourceLedger(unittest.TestCase):

    def test_valid_construction(self):
        rl = ResourceLedger(
            electricity_kwh_d=10.0,
            heat_kwh_d=5.0,
            water_kg_d=100.0,
            fuel_kwh_d=0.0,
            labour_note="not quantified",
        )
        self.assertEqual(rl.electricity_kwh_d, 10.0)

    def test_frozen(self):
        rl = ResourceLedger(
            electricity_kwh_d=10.0, heat_kwh_d=5.0, water_kg_d=100.0,
            fuel_kwh_d=0.0, labour_note="test",
        )
        with self.assertRaises((dataclasses.FrozenInstanceError, TypeError, AttributeError)):
            rl.electricity_kwh_d = 0.0  # type: ignore[misc]

    def test_negative_electricity_raises(self):
        with self.assertRaises(ValueError):
            ResourceLedger(
                electricity_kwh_d=-1.0, heat_kwh_d=0.0, water_kg_d=0.0,
                fuel_kwh_d=0.0, labour_note="x",
            )

    def test_negative_heat_raises(self):
        with self.assertRaises(ValueError):
            ResourceLedger(
                electricity_kwh_d=0.0, heat_kwh_d=-0.1, water_kg_d=0.0,
                fuel_kwh_d=0.0, labour_note="x",
            )

    def test_negative_fuel_raises(self):
        with self.assertRaises(ValueError):
            ResourceLedger(
                electricity_kwh_d=0.0, heat_kwh_d=0.0, water_kg_d=0.0,
                fuel_kwh_d=-0.5, labour_note="x",
            )

    def test_empty_labour_note_raises(self):
        with self.assertRaises(ValueError):
            ResourceLedger(
                electricity_kwh_d=0.0, heat_kwh_d=0.0, water_kg_d=0.0,
                fuel_kwh_d=0.0, labour_note="",
            )

    def test_negative_water_allowed(self):
        """water_kg_d may be negative (water removed from feedstock)."""
        rl = ResourceLedger(
            electricity_kwh_d=0.0, heat_kwh_d=0.0, water_kg_d=-50.0,
            fuel_kwh_d=0.0, labour_note="not quantified",
        )
        self.assertEqual(rl.water_kg_d, -50.0)


# ===========================================================================
# TestLedgerFromResult — five pathways using real simulator outputs
# ===========================================================================

class TestLedgerFromResult(unittest.TestCase):

    def _ad_result(self):
        from app.core_engine.pathways.compare import _run_ad
        return _run_ad(_fs(), None)

    def _composting_result(self):
        from app.core_engine.pathways.composting import simulate_composting
        return simulate_composting(_fs())

    def _incineration_result(self):
        from app.core_engine.pathways.incineration import simulate_incineration
        return simulate_incineration(_fs_dry())

    def _gasification_result(self):
        from app.core_engine.pathways.gasification import simulate_gasification
        return simulate_gasification(_fs_dry())

    def _pyrolysis_result(self):
        from app.core_engine.pathways.pyrolysis import simulate_pyrolysis
        return simulate_pyrolysis(_fs_dry())

    # ------------------------------------------------------------------ #
    # Anaerobic digestion                                                  #
    # ------------------------------------------------------------------ #

    def test_ad_returns_ledger(self):
        result = self._ad_result()
        ledger = ledger_from_result("anaerobic_digestion", result)
        self.assertIsInstance(ledger, ResourceLedger)

    def test_ad_electricity_equals_aux(self):
        result = self._ad_result()
        ledger = ledger_from_result("anaerobic_digestion", result)
        self.assertAlmostEqual(ledger.electricity_kwh_d, result["aux_kwh_d"], places=9)

    def test_ad_heat_equals_q_demand(self):
        result = self._ad_result()
        ledger = ledger_from_result("anaerobic_digestion", result)
        self.assertAlmostEqual(ledger.heat_kwh_d, result["q_demand_kwh_d"], places=9)

    def test_ad_water_equals_water_added(self):
        result = self._ad_result()
        ledger = ledger_from_result("anaerobic_digestion", result)
        self.assertAlmostEqual(ledger.water_kg_d, result["water_added_kg_d"], places=9)

    def test_ad_fuel_is_zero(self):
        ledger = ledger_from_result("anaerobic_digestion", self._ad_result())
        self.assertEqual(ledger.fuel_kwh_d, 0.0)

    # ------------------------------------------------------------------ #
    # Composting                                                           #
    # ------------------------------------------------------------------ #

    def test_composting_returns_ledger(self):
        result = self._composting_result()
        ledger = ledger_from_result("composting", result)
        self.assertIsInstance(ledger, ResourceLedger)

    def test_composting_electricity_equals_aux(self):
        result = self._composting_result()
        ledger = ledger_from_result("composting", result)
        self.assertAlmostEqual(ledger.electricity_kwh_d, result["aux_kwh_d"], places=9)

    def test_composting_heat_is_zero(self):
        ledger = ledger_from_result("composting", self._composting_result())
        self.assertEqual(ledger.heat_kwh_d, 0.0)

    def test_composting_water_is_zero(self):
        ledger = ledger_from_result("composting", self._composting_result())
        self.assertEqual(ledger.water_kg_d, 0.0)

    def test_composting_fuel_is_zero(self):
        ledger = ledger_from_result("composting", self._composting_result())
        self.assertEqual(ledger.fuel_kwh_d, 0.0)

    # ------------------------------------------------------------------ #
    # Incineration                                                         #
    # ------------------------------------------------------------------ #

    def test_incineration_returns_ledger(self):
        result = self._incineration_result()
        ledger = ledger_from_result("incineration", result)
        self.assertIsInstance(ledger, ResourceLedger)

    def test_incineration_electricity_equals_aux(self):
        result = self._incineration_result()
        ledger = ledger_from_result("incineration", result)
        self.assertAlmostEqual(ledger.electricity_kwh_d, result["aux_kwh_d"], places=9)

    def test_incineration_heat_is_zero(self):
        ledger = ledger_from_result("incineration", self._incineration_result())
        self.assertEqual(ledger.heat_kwh_d, 0.0)

    def test_incineration_fuel_is_zero(self):
        ledger = ledger_from_result("incineration", self._incineration_result())
        self.assertEqual(ledger.fuel_kwh_d, 0.0)

    # ------------------------------------------------------------------ #
    # Gasification                                                         #
    # ------------------------------------------------------------------ #

    def test_gasification_returns_ledger(self):
        result = self._gasification_result()
        ledger = ledger_from_result("gasification", result)
        self.assertIsInstance(ledger, ResourceLedger)

    def test_gasification_electricity_equals_aux_plus_drying(self):
        result = self._gasification_result()
        ledger = ledger_from_result("gasification", result)
        expected = result["aux_kwh_d"] + result["drying_kwh_d"]
        self.assertAlmostEqual(ledger.electricity_kwh_d, expected, places=9)

    def test_gasification_heat_is_zero(self):
        ledger = ledger_from_result("gasification", self._gasification_result())
        self.assertEqual(ledger.heat_kwh_d, 0.0)

    def test_gasification_fuel_is_zero(self):
        ledger = ledger_from_result("gasification", self._gasification_result())
        self.assertEqual(ledger.fuel_kwh_d, 0.0)

    # ------------------------------------------------------------------ #
    # Pyrolysis                                                            #
    # ------------------------------------------------------------------ #

    def test_pyrolysis_returns_ledger(self):
        result = self._pyrolysis_result()
        ledger = ledger_from_result("pyrolysis", result)
        self.assertIsInstance(ledger, ResourceLedger)

    def test_pyrolysis_fuel_equals_process_heat(self):
        result = self._pyrolysis_result()
        ledger = ledger_from_result("pyrolysis", result)
        self.assertAlmostEqual(ledger.fuel_kwh_d, result["process_heat_kwh_d"], places=9)

    def test_pyrolysis_electricity_is_zero(self):
        ledger = ledger_from_result("pyrolysis", self._pyrolysis_result())
        self.assertEqual(ledger.electricity_kwh_d, 0.0)

    def test_pyrolysis_heat_is_zero(self):
        ledger = ledger_from_result("pyrolysis", self._pyrolysis_result())
        self.assertEqual(ledger.heat_kwh_d, 0.0)

    # ------------------------------------------------------------------ #
    # Missing keys treated as 0.0                                          #
    # ------------------------------------------------------------------ #

    def test_missing_aux_kwh_d_defaults_to_zero(self):
        """If a result dict lacks aux_kwh_d, electricity_kwh_d must be 0.0."""
        ledger = ledger_from_result("composting", {})
        self.assertEqual(ledger.electricity_kwh_d, 0.0)

    def test_missing_process_heat_defaults_to_zero(self):
        ledger = ledger_from_result("pyrolysis", {})
        self.assertEqual(ledger.fuel_kwh_d, 0.0)

    def test_missing_keys_ad_all_zero(self):
        ledger = ledger_from_result("anaerobic_digestion", {})
        self.assertEqual(ledger.electricity_kwh_d, 0.0)
        self.assertEqual(ledger.heat_kwh_d, 0.0)
        self.assertEqual(ledger.water_kg_d, 0.0)
        self.assertEqual(ledger.fuel_kwh_d, 0.0)

    # ------------------------------------------------------------------ #
    # Unknown pathway                                                      #
    # ------------------------------------------------------------------ #

    def test_unknown_pathway_raises(self):
        with self.assertRaises(ValueError):
            ledger_from_result("not_a_pathway", {})

    def test_empty_string_pathway_raises(self):
        with self.assertRaises(ValueError):
            ledger_from_result("", {})

    def test_wrong_case_pathway_raises(self):
        with self.assertRaises(ValueError):
            ledger_from_result("Composting", {})

    # ------------------------------------------------------------------ #
    # Labour note                                                          #
    # ------------------------------------------------------------------ #

    def test_labour_note_non_empty_for_all_pathways(self):
        for pw in ("anaerobic_digestion", "composting", "incineration",
                   "gasification", "pyrolysis"):
            with self.subTest(pathway=pw):
                ledger = ledger_from_result(pw, {})
                self.assertTrue(ledger.labour_note.strip())


if __name__ == "__main__":
    unittest.main()
