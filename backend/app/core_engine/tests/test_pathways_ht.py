"""Tests for htc.py, torrefaction.py, and extended.py.

Hand-computed reference values (M = 1000 kg/d, default params):

HTC (original keys):
    hydrochar_kg_d          = 1000 * 0.135                  = 135.0
    hydrochar_energy_kwh_d  = 135.0 * 20.0 / 3.6            = 750.0
    heat_kwh_d              = 1000 * 0.158                  = 158.0
    aux_kwh_per_kg          = 0.005+0.006+0.012+0.005       = 0.028
    aux_kwh_d               = 1000 * 0.028                  = 28.0
    e_net_energy_kwh_d      = 750.0 - 158.0 - 28.0         = 564.0

HTC (new keys):
    gas_kg_d                = 1000 * 0.05                   = 50.0
    water_out_kg_d          = 1000 - 135.0 - 50.0          = 815.0
    mass closure check      = 135.0 + 815.0 + 50.0         = 1000.0 ✓
    reactor_heat_kwh_d      = 1000 * 4.0 * (220-25) / 3600 * (1-0.60)
                            = 1000 * 4.0 * 195 / 3600 * 0.40
                            = 1000 * 780 / 3600 * 0.40
                            = 216.6667 * 0.40               = 86.6667 kWh/d

Torrefaction (original keys, M=1000, moisture=0.30):
    pellets_kg_d            = 1000 * 0.633                  = 633.0
    pellet_energy_kwh_d     = 633.0 * 19.7 / 3.6
                            = 12468.1 / 3.6 ≈ 3463.361111...
                              (19.7 * 633 = 12468.1)
    dryer_heat_kwh_d        = 1000 * 0.0349                 = 34.9
    aux_kwh_per_kg          = 0.005+0.018+0.0209+0.003      = 0.0469
    aux_kwh_d               = 1000 * 0.0469                 = 46.9
    e_net_energy_kwh_d      = pellet_energy - 34.9 - 46.9
                            = 12468.1/3.6 - 81.8

Torrefaction (new keys, M=1000, moisture=0.30, default params):
    dry_feed_kg_d           = 1000 * (1 - 0.30)            = 700.0
    torrefied_solid_kg_d    = 700.0 * 0.70                 = 490.0
    predry_energy_kwh_d:    moisture=0.30 > target=0.10 → needs drying
        water_to_remove     = 1000 * (0.30-0.10)/(1-0.10)
                            = 1000 * 0.20/0.90             = 222.222...
        predry_energy_kwh_d = 222.222... * 2.26 / 3.6      = 139.506... kWh/d
    pellet_energy_density_mj_per_kg = 19.7  (same as hhv_mj_per_kg)
    energy_yield_fraction   = pellet_energy_kwh_d / (dry_feed * lhv_dry / 3.6)
        with lhv_dry=19.7:  = (633*19.7/3.6) / (700*19.7/3.6)
                            = 633/700                       = 0.904286...
"""
from __future__ import annotations

import json
import unittest

from app.core_engine.pathways.extended import PATHWAYS_EXTENDED, check_extended
from app.core_engine.pathways.feasibility import PATHWAYS
from app.core_engine.pathways.feedstock import Feedstock
from app.core_engine.pathways.htc import HTCParams, simulate_htc
from app.core_engine.pathways.torrefaction import TorrefactionParams, simulate_torrefaction

# ---------------------------------------------------------------------------
# Shared feedstock builders
# ---------------------------------------------------------------------------

def _make_feedstock(
    mass: float = 1000.0,
    moisture: float = 0.60,
    organic: float = 0.50,
    plastic: float = 0.20,
    paper: float = 0.10,
    other: float = 0.20,
) -> Feedstock:
    """Helper — fractions must sum to 1.0."""
    return Feedstock(
        total_mass_kg_d=mass,
        organic_fraction=organic,
        plastic_fraction=plastic,
        paper_fraction=paper,
        other_fraction=other,
        moisture_fraction=moisture,
        ash_fraction_dry=0.05,
        lhv_dry_mj_per_kg=12.0,
        contamination_pct=5.0,
    )


# ---------------------------------------------------------------------------
# HTC tests
# ---------------------------------------------------------------------------

class TestSimulateHTC(unittest.TestCase):

    def _ref_1000(self):
        """Hand-computed reference values for M = 1000, default params."""
        M = 1000.0
        hydrochar_kg_d          = M * 0.135                       # 135.0
        hydrochar_energy_kwh_d  = hydrochar_kg_d * 20.0 / 3.6    # 750.0
        heat_kwh_d              = M * 0.158                       # 158.0
        aux_kwh_d               = M * (0.005 + 0.006 + 0.012 + 0.005)  # 28.0
        e_net                   = hydrochar_energy_kwh_d - heat_kwh_d - aux_kwh_d  # 564.0
        return {
            "hydrochar_kg_d": hydrochar_kg_d,
            "hydrochar_energy_kwh_d": hydrochar_energy_kwh_d,
            "heat_kwh_d": heat_kwh_d,
            "aux_kwh_d": aux_kwh_d,
            "e_net_energy_kwh_d": e_net,
        }

    def test_reference_values_1000_kg_d(self):
        fs = _make_feedstock(mass=1000.0, moisture=0.60)
        result = simulate_htc(fs)
        ref = self._ref_1000()
        for key, expected in ref.items():
            self.assertAlmostEqual(
                result[key], expected, delta=1e-6,
                msg=f"{key}: expected {expected}, got {result[key]}",
            )

    def test_linear_scaling(self):
        """Result scales linearly with mass."""
        fs1 = _make_feedstock(mass=1000.0, moisture=0.60)
        fs2 = _make_feedstock(mass=2000.0, moisture=0.60)
        r1 = simulate_htc(fs1)
        r2 = simulate_htc(fs2)
        for key in ("hydrochar_kg_d", "hydrochar_energy_kwh_d",
                    "heat_kwh_d", "aux_kwh_d", "e_net_energy_kwh_d"):
            self.assertAlmostEqual(r2[key], 2.0 * r1[key], delta=1e-9,
                                   msg=f"Linear scaling failed for {key}")

    def test_zero_mass_gives_zeros(self):
        fs = _make_feedstock(mass=0.0, moisture=0.60)
        result = simulate_htc(fs)
        for key in ("hydrochar_kg_d", "hydrochar_energy_kwh_d",
                    "heat_kwh_d", "aux_kwh_d", "e_net_energy_kwh_d"):
            self.assertEqual(result[key], 0.0)

    def test_negative_mass_raises(self):
        with self.assertRaises(ValueError):
            simulate_htc(Feedstock(
                total_mass_kg_d=-1.0,
                organic_fraction=0.5, plastic_fraction=0.2,
                paper_fraction=0.1, other_fraction=0.2,
                moisture_fraction=0.6, ash_fraction_dry=0.05,
                lhv_dry_mj_per_kg=12.0, contamination_pct=5.0,
            ))

    def test_negative_param_raises(self):
        with self.assertRaises(ValueError):
            HTCParams(hydrochar_dry_kg_per_kg=-0.1)

    def test_status_is_illustrative_estimate(self):
        result = simulate_htc(_make_feedstock())
        self.assertEqual(result["status"], "illustrative_estimate")

    def test_warnings_is_list(self):
        result = simulate_htc(_make_feedstock())
        self.assertIsInstance(result["warnings"], list)

    def test_net_energy_warning_when_negative(self):
        # Force near-zero yield to get negative net energy
        params = HTCParams(
            hydrochar_dry_kg_per_kg=0.001,
            hhv_mj_per_kg=1.0,
            heat_kwh_per_kg=10.0,
        )
        result = simulate_htc(_make_feedstock(mass=1000.0), params=params)
        self.assertTrue(result["e_net_energy_kwh_d"] <= 0)
        self.assertTrue(any("e_net_energy_kwh_d" in w for w in result["warnings"]))

    def test_json_serialisable(self):
        result = simulate_htc(_make_feedstock())
        json.dumps(result)  # must not raise

    def test_all_keys_present(self):
        result = simulate_htc(_make_feedstock())
        expected_keys = {
            "hydrochar_kg_d", "hydrochar_energy_kwh_d",
            "heat_kwh_d", "aux_kwh_d", "e_net_energy_kwh_d",
            "gas_kg_d", "water_out_kg_d", "reactor_heat_kwh_d",
            "warnings", "status",
        }
        self.assertEqual(set(result.keys()), expected_keys)

    # --- new keys: hand-computed reference ----------------------------------

    def test_new_keys_reference_values_1000_kg_d(self):
        # Hand-computed reference (M=1000, moisture=0.60, default params):
        #   gas_kg_d         = 1000 * 0.05               = 50.0
        #   water_out_kg_d   = 1000 - 135.0 - 50.0      = 815.0
        #   reactor_heat_kwh_d = 1000*4.0*(220-25)/3600*(1-0.60)
        #                      = 1000*4.0*195/3600*0.40  = 86.6667 kWh/d
        fs = _make_feedstock(mass=1000.0, moisture=0.60)
        result = simulate_htc(fs)
        self.assertAlmostEqual(result["gas_kg_d"], 50.0, delta=1e-6)
        self.assertAlmostEqual(result["water_out_kg_d"], 815.0, delta=1e-6)
        expected_reactor_heat = 1000.0 * 4.0 * (220.0 - 25.0) / 3600.0 * (1.0 - 0.60)
        self.assertAlmostEqual(result["reactor_heat_kwh_d"], expected_reactor_heat, delta=1e-6)

    def test_process_water_non_negative_default(self):
        fs = _make_feedstock(mass=1000.0, moisture=0.60)
        result = simulate_htc(fs)
        self.assertGreaterEqual(result["water_out_kg_d"], 0.0)

    def test_mass_closure(self):
        # hydrochar_kg_d + water_out_kg_d + gas_kg_d must equal M within 1e-6
        fs = _make_feedstock(mass=1000.0, moisture=0.60)
        result = simulate_htc(fs)
        total = result["hydrochar_kg_d"] + result["water_out_kg_d"] + result["gas_kg_d"]
        self.assertAlmostEqual(total, 1000.0, delta=1e-6,
                               msg="Mass closure: hydrochar + water + gas != M")

    def test_reactor_heat_falls_as_recovery_rises(self):
        # Higher heat_recovery_fraction → lower reactor_heat_kwh_d
        fs = _make_feedstock(mass=1000.0, moisture=0.60)
        r_low  = simulate_htc(fs, HTCParams(heat_recovery_fraction=0.20))
        r_mid  = simulate_htc(fs, HTCParams(heat_recovery_fraction=0.60))
        r_high = simulate_htc(fs, HTCParams(heat_recovery_fraction=0.90))
        self.assertGreater(r_low["reactor_heat_kwh_d"],  r_mid["reactor_heat_kwh_d"])
        self.assertGreater(r_mid["reactor_heat_kwh_d"],  r_high["reactor_heat_kwh_d"])

    def test_reactor_heat_linear_in_recovery(self):
        # At recovery=0.0: heat = M*cp*dT/3600; at recovery=1.0: heat = 0
        fs = _make_feedstock(mass=1000.0, moisture=0.60)
        r0 = simulate_htc(fs, HTCParams(heat_recovery_fraction=0.0))
        r1 = simulate_htc(fs, HTCParams(heat_recovery_fraction=1.0))
        expected_full = 1000.0 * 4.0 * (220.0 - 25.0) / 3600.0  # no recovery
        self.assertAlmostEqual(r0["reactor_heat_kwh_d"], expected_full, delta=1e-6)
        self.assertAlmostEqual(r1["reactor_heat_kwh_d"], 0.0, delta=1e-9)

    def test_water_out_negative_triggers_warning(self):
        # Extreme hydrochar yield to force water_out < 0
        params = HTCParams(hydrochar_dry_kg_per_kg=0.96)
        fs = _make_feedstock(mass=1000.0, moisture=0.60)
        result = simulate_htc(fs, params=params)
        self.assertLess(result["water_out_kg_d"], 0.0)
        self.assertTrue(any("water_out_kg_d" in w for w in result["warnings"]))

    def test_reactor_heat_divergence_warning(self):
        # Make reactor_heat_kwh_d >> heat_kwh_d (> 50% difference)
        params = HTCParams(heat_recovery_fraction=0.0, cp_kj_kg_k=40.0)
        fs = _make_feedstock(mass=1000.0, moisture=0.60)
        result = simulate_htc(fs, params=params)
        self.assertTrue(any("differ by" in w for w in result["warnings"]),
                        msg="Expected divergence warning not found")

    def test_new_keys_linear_scaling(self):
        fs1 = _make_feedstock(mass=500.0,  moisture=0.60)
        fs2 = _make_feedstock(mass=1000.0, moisture=0.60)
        r1 = simulate_htc(fs1)
        r2 = simulate_htc(fs2)
        for key in ("gas_kg_d", "water_out_kg_d", "reactor_heat_kwh_d"):
            self.assertAlmostEqual(r2[key], 2.0 * r1[key], delta=1e-9,
                                   msg=f"Linear scaling failed for {key}")


# ---------------------------------------------------------------------------
# Torrefaction tests
# ---------------------------------------------------------------------------

class TestSimulateTorrefaction(unittest.TestCase):

    def _ref_1000(self):
        """Hand-computed reference values for M = 1000, default params."""
        M = 1000.0
        pellets_kg_d           = M * 0.633                        # 633.0
        pellet_energy_kwh_d    = pellets_kg_d * 19.7 / 3.6       # 633*19.7/3.6
        dryer_heat_kwh_d       = M * 0.0349                      # 34.9
        aux_kwh_d              = M * (0.005 + 0.018 + 0.0209 + 0.003)  # 46.9
        e_net                  = pellet_energy_kwh_d - dryer_heat_kwh_d - aux_kwh_d
        return {
            "pellets_kg_d": pellets_kg_d,
            "pellet_energy_kwh_d": pellet_energy_kwh_d,
            "dryer_heat_kwh_d": dryer_heat_kwh_d,
            "aux_kwh_d": aux_kwh_d,
            "e_net_energy_kwh_d": e_net,
        }

    def test_reference_values_1000_kg_d(self):
        # moisture 0.30 (dry enough for torrefaction) and organic 0.50
        fs = _make_feedstock(mass=1000.0, moisture=0.30, organic=0.50,
                             plastic=0.20, paper=0.10, other=0.20)
        result = simulate_torrefaction(fs)
        ref = self._ref_1000()
        for key, expected in ref.items():
            self.assertAlmostEqual(
                result[key], expected, delta=1e-6,
                msg=f"{key}: expected {expected}, got {result[key]}",
            )

    def test_linear_scaling(self):
        fs1 = _make_feedstock(mass=500.0,  moisture=0.30, organic=0.50,
                              plastic=0.20, paper=0.10, other=0.20)
        fs2 = _make_feedstock(mass=1000.0, moisture=0.30, organic=0.50,
                              plastic=0.20, paper=0.10, other=0.20)
        r1 = simulate_torrefaction(fs1)
        r2 = simulate_torrefaction(fs2)
        for key in ("pellets_kg_d", "pellet_energy_kwh_d",
                    "dryer_heat_kwh_d", "aux_kwh_d", "e_net_energy_kwh_d"):
            self.assertAlmostEqual(r2[key], 2.0 * r1[key], delta=1e-9,
                                   msg=f"Linear scaling failed for {key}")

    def test_zero_mass_gives_zeros(self):
        fs = _make_feedstock(mass=0.0, moisture=0.30, organic=0.50,
                             plastic=0.20, paper=0.10, other=0.20)
        result = simulate_torrefaction(fs)
        for key in ("pellets_kg_d", "pellet_energy_kwh_d",
                    "dryer_heat_kwh_d", "aux_kwh_d", "e_net_energy_kwh_d"):
            self.assertEqual(result[key], 0.0)

    def test_negative_mass_raises(self):
        with self.assertRaises(ValueError):
            simulate_torrefaction(Feedstock(
                total_mass_kg_d=-1.0,
                organic_fraction=0.5, plastic_fraction=0.2,
                paper_fraction=0.1, other_fraction=0.2,
                moisture_fraction=0.3, ash_fraction_dry=0.05,
                lhv_dry_mj_per_kg=12.0, contamination_pct=5.0,
            ))

    def test_negative_param_raises(self):
        with self.assertRaises(ValueError):
            TorrefactionParams(pellet_kg_per_kg=-0.1)

    def test_status_is_illustrative_estimate(self):
        fs = _make_feedstock(mass=1000.0, moisture=0.30, organic=0.50,
                             plastic=0.20, paper=0.10, other=0.20)
        result = simulate_torrefaction(fs)
        self.assertEqual(result["status"], "illustrative_estimate")

    def test_warnings_is_list(self):
        fs = _make_feedstock(mass=1000.0, moisture=0.30, organic=0.50,
                             plastic=0.20, paper=0.10, other=0.20)
        result = simulate_torrefaction(fs)
        self.assertIsInstance(result["warnings"], list)

    def test_net_energy_warning_when_negative(self):
        params = TorrefactionParams(
            pellet_kg_per_kg=0.001,
            hhv_mj_per_kg=1.0,
            dryer_heat_kwh_per_kg=50.0,
        )
        fs = _make_feedstock(mass=1000.0, moisture=0.30, organic=0.50,
                             plastic=0.20, paper=0.10, other=0.20)
        result = simulate_torrefaction(fs, params=params)
        self.assertTrue(result["e_net_energy_kwh_d"] <= 0)
        self.assertTrue(any("e_net_energy_kwh_d" in w for w in result["warnings"]))

    def test_json_serialisable(self):
        fs = _make_feedstock(mass=1000.0, moisture=0.30, organic=0.50,
                             plastic=0.20, paper=0.10, other=0.20)
        result = simulate_torrefaction(fs)
        json.dumps(result)

    def test_all_keys_present(self):
        fs = _make_feedstock(mass=1000.0, moisture=0.30, organic=0.50,
                             plastic=0.20, paper=0.10, other=0.20)
        result = simulate_torrefaction(fs)
        expected_keys = {
            "pellets_kg_d", "pellet_energy_kwh_d",
            "dryer_heat_kwh_d", "aux_kwh_d", "e_net_energy_kwh_d",
            "dry_feed_kg_d", "torrefied_solid_kg_d",
            "predry_energy_kwh_d", "pellet_energy_density_mj_per_kg",
            "warnings", "status",
        }
        self.assertEqual(set(result.keys()), expected_keys)

    def test_energy_yield_fraction_key_absent_by_default(self):
        fs = _make_feedstock(mass=1000.0, moisture=0.30, organic=0.50,
                             plastic=0.20, paper=0.10, other=0.20)
        result = simulate_torrefaction(fs)
        self.assertNotIn("energy_yield_fraction", result)

    def test_energy_yield_fraction_present_when_lhv_supplied(self):
        fs = _make_feedstock(mass=1000.0, moisture=0.30, organic=0.50,
                             plastic=0.20, paper=0.10, other=0.20)
        result = simulate_torrefaction(fs, lhv_dry_mj_per_kg=19.7)
        self.assertIn("energy_yield_fraction", result)

    # --- new keys: hand-computed reference ----------------------------------

    def test_new_keys_reference_values_1000_kg_d(self):
        # Hand-computed (M=1000, moisture=0.30, default params):
        #   dry_feed_kg_d        = 1000*(1-0.30)         = 700.0
        #   torrefied_solid_kg_d = 700.0*0.70            = 490.0
        #   water_to_remove      = 1000*(0.30-0.10)/(1-0.10)
        #                        = 1000*0.20/0.90        = 222.222...
        #   predry_energy_kwh_d  = 222.222...*2.26/3.6   = 139.506... kWh/d
        #   pellet_energy_density_mj_per_kg              = 19.7
        fs = _make_feedstock(mass=1000.0, moisture=0.30, organic=0.50,
                             plastic=0.20, paper=0.10, other=0.20)
        result = simulate_torrefaction(fs)
        self.assertAlmostEqual(result["dry_feed_kg_d"], 700.0, delta=1e-6)
        self.assertAlmostEqual(result["torrefied_solid_kg_d"], 490.0, delta=1e-6)
        water_to_remove = 1000.0 * (0.30 - 0.10) / (1.0 - 0.10)  # 222.222...
        expected_predry = water_to_remove * 2.26 / 3.6
        self.assertAlmostEqual(result["predry_energy_kwh_d"], expected_predry, delta=1e-6)
        self.assertAlmostEqual(result["pellet_energy_density_mj_per_kg"], 19.7, delta=1e-9)

    def test_energy_yield_fraction_reference(self):
        # energy_yield_fraction = pellet_energy / (dry_feed * lhv_dry / 3.6)
        # with lhv_dry=19.7 and hhv=19.7: = (633*19.7/3.6)/(700*19.7/3.6) = 633/700
        fs = _make_feedstock(mass=1000.0, moisture=0.30, organic=0.50,
                             plastic=0.20, paper=0.10, other=0.20)
        result = simulate_torrefaction(fs, lhv_dry_mj_per_kg=19.7)
        expected = (1000.0 * 0.633 * 19.7 / 3.6) / (700.0 * 19.7 / 3.6)  # 633/700
        self.assertAlmostEqual(result["energy_yield_fraction"], expected, delta=1e-6)

    def test_predry_energy_zero_when_already_dry(self):
        # moisture=0.05 < target_moisture=0.10 → no pre-drying needed
        fs = _make_feedstock(mass=1000.0, moisture=0.05, organic=0.50,
                             plastic=0.20, paper=0.10, other=0.20)
        result = simulate_torrefaction(fs)
        self.assertEqual(result["predry_energy_kwh_d"], 0.0)

    def test_predry_energy_rises_with_moisture(self):
        # Higher moisture → more water to remove → higher predry energy
        fs_low  = _make_feedstock(mass=1000.0, moisture=0.20, organic=0.50,
                                  plastic=0.20, paper=0.10, other=0.20)
        fs_high = _make_feedstock(mass=1000.0, moisture=0.40, organic=0.50,
                                  plastic=0.20, paper=0.10, other=0.20)
        r_low  = simulate_torrefaction(fs_low)
        r_high = simulate_torrefaction(fs_high)
        self.assertGreater(r_high["predry_energy_kwh_d"],
                           r_low["predry_energy_kwh_d"])

    def test_torrefied_solid_le_dry_feed(self):
        # mass_yield <= 1.0 → torrefied_solid_kg_d <= dry_feed_kg_d always
        fs = _make_feedstock(mass=1000.0, moisture=0.30, organic=0.50,
                             plastic=0.20, paper=0.10, other=0.20)
        result = simulate_torrefaction(fs)
        self.assertLessEqual(result["torrefied_solid_kg_d"],
                             result["dry_feed_kg_d"] + 1e-9)

    def test_new_keys_linear_scaling(self):
        fs1 = _make_feedstock(mass=500.0,  moisture=0.30, organic=0.50,
                              plastic=0.20, paper=0.10, other=0.20)
        fs2 = _make_feedstock(mass=1000.0, moisture=0.30, organic=0.50,
                              plastic=0.20, paper=0.10, other=0.20)
        r1 = simulate_torrefaction(fs1)
        r2 = simulate_torrefaction(fs2)
        for key in ("dry_feed_kg_d", "torrefied_solid_kg_d", "predry_energy_kwh_d"):
            self.assertAlmostEqual(r2[key], 2.0 * r1[key], delta=1e-9,
                                   msg=f"Linear scaling failed for {key}")


# ---------------------------------------------------------------------------
# Extended registry tests
# ---------------------------------------------------------------------------

class TestPathwaysExtended(unittest.TestCase):

    def test_pathways_unchanged_len_5(self):
        self.assertEqual(len(PATHWAYS), 5)

    def test_pathways_extended_len_7(self):
        self.assertEqual(len(PATHWAYS_EXTENDED), 7)

    def test_pathways_extended_contains_htc_and_torrefaction(self):
        self.assertIn("htc", PATHWAYS_EXTENDED)
        self.assertIn("torrefaction", PATHWAYS_EXTENDED)

    def test_pathways_extended_contains_all_original(self):
        for p in PATHWAYS:
            self.assertIn(p, PATHWAYS_EXTENDED)

    def test_check_extended_unknown_raises(self):
        with self.assertRaises(ValueError):
            check_extended("unknown_pathway", _make_feedstock())

    # HTC feasibility
    def test_htc_feasible_high_moisture(self):
        # moisture=0.65 >= 0.50 and organic=0.50 (default) >= 0.50 → feasible
        fs = _make_feedstock(moisture=0.65)
        f = check_extended("htc", fs)
        self.assertTrue(f.feasible)
        self.assertEqual(f.reasons, [])

    def test_htc_feasible_exact_threshold(self):
        # moisture=0.50 and organic=0.50 (both at minimum) → feasible
        fs = _make_feedstock(moisture=0.50)
        f = check_extended("htc", fs)
        self.assertTrue(f.feasible)

    def test_htc_infeasible_low_moisture(self):
        fs = _make_feedstock(moisture=0.30)
        f = check_extended("htc", fs)
        self.assertFalse(f.feasible)
        self.assertTrue(len(f.reasons) >= 1)
        self.assertTrue(any("moisture" in r for r in f.reasons))

    def test_htc_infeasible_low_organic(self):
        # organic=0.45 < 0.50 minimum, moisture=0.70 is fine
        fs = _make_feedstock(moisture=0.70, organic=0.45,
                             plastic=0.25, paper=0.10, other=0.20)
        f = check_extended("htc", fs)
        self.assertFalse(f.feasible)
        self.assertTrue(any("organic_fraction" in r for r in f.reasons))

    def test_htc_infeasible_both_conditions(self):
        # organic=0.45 < 0.50 AND moisture=0.30 < 0.50 → two reasons
        fs = _make_feedstock(moisture=0.30, organic=0.45,
                             plastic=0.25, paper=0.10, other=0.20)
        f = check_extended("htc", fs)
        self.assertFalse(f.feasible)
        self.assertEqual(len(f.reasons), 2)
        self.assertTrue(any("moisture" in r for r in f.reasons))
        self.assertTrue(any("organic_fraction" in r for r in f.reasons))

    # Torrefaction feasibility
    # NOTE: test_torrefaction_feasible updated — new rule requires
    # lignocellulosic_fraction >= 0.60; organic=0.50 (proxy) < 0.60 is
    # infeasible when lignocellulosic_fraction is not supplied.
    # Pass lignocellulosic_fraction=0.70 explicitly to test the feasible path.
    def test_torrefaction_feasible(self):
        fs = _make_feedstock(moisture=0.30, organic=0.50,
                             plastic=0.20, paper=0.10, other=0.20)
        f = check_extended("torrefaction", fs, lignocellulosic_fraction=0.70)
        self.assertTrue(f.feasible)
        self.assertEqual(f.reasons, [])

    def test_torrefaction_infeasible_high_moisture(self):
        fs = _make_feedstock(moisture=0.65, organic=0.50,
                             plastic=0.20, paper=0.10, other=0.20)
        f = check_extended("torrefaction", fs, lignocellulosic_fraction=0.70)
        self.assertFalse(f.feasible)
        self.assertTrue(any("moisture" in r for r in f.reasons))

    def test_torrefaction_infeasible_low_organic(self):
        # moisture ok, lignocellulosic_fraction below threshold
        # NOTE: updated to check "lignocellulosic_fraction" in reason (was "organic_fraction")
        # The new rule checks lignocellulosic_fraction; proxy adds a separate note.
        fs = _make_feedstock(moisture=0.30, organic=0.20,
                             plastic=0.30, paper=0.10, other=0.40)
        f = check_extended("torrefaction", fs)  # no lignocellulosic arg → proxy
        self.assertFalse(f.feasible)
        self.assertTrue(any("lignocellulosic_fraction" in r for r in f.reasons))

    def test_torrefaction_infeasible_both_reasons(self):
        # moisture too high AND lignocellulosic too low (via proxy organic=0.20)
        # NOTE: updated — now 3 reasons: moisture fail, proxy note, ligno fail
        fs = _make_feedstock(moisture=0.65, organic=0.20,
                             plastic=0.30, paper=0.10, other=0.40)
        f = check_extended("torrefaction", fs)  # no lignocellulosic arg → proxy
        self.assertFalse(f.feasible)
        self.assertEqual(len(f.reasons), 3)

    def test_torrefaction_feasible_with_explicit_lignocellulosic(self):
        # When lignocellulosic_fraction >= 0.60, no proxy note, feasible
        fs = _make_feedstock(moisture=0.30, organic=0.50,
                             plastic=0.20, paper=0.10, other=0.20)
        f = check_extended("torrefaction", fs, lignocellulosic_fraction=0.65)
        self.assertTrue(f.feasible)
        self.assertEqual(f.reasons, [])

    def test_torrefaction_infeasible_explicit_lignocellulosic_below_threshold(self):
        # lignocellulosic_fraction=0.55 < 0.60 → infeasible, no proxy note
        fs = _make_feedstock(moisture=0.30, organic=0.50,
                             plastic=0.20, paper=0.10, other=0.20)
        f = check_extended("torrefaction", fs, lignocellulosic_fraction=0.55)
        self.assertFalse(f.feasible)
        self.assertTrue(any("lignocellulosic_fraction" in r for r in f.reasons))
        self.assertFalse(any("proxy" in r for r in f.reasons))

    def test_torrefaction_proxy_warning_present_when_arg_omitted(self):
        # Proxy note is in reasons when lignocellulosic_fraction not supplied
        fs = _make_feedstock(moisture=0.30, organic=0.70,
                             plastic=0.10, paper=0.10, other=0.10)
        f = check_extended("torrefaction", fs)  # no lignocellulosic arg
        self.assertTrue(any("proxy" in r for r in f.reasons))

    def test_check_extended_delegates_to_check_pathway(self):
        """Existing pathways: feasibility result matches check_pathway directly."""
        from app.core_engine.pathways.feasibility import check_pathway
        fs = _make_feedstock(moisture=0.10, organic=0.50,
                             plastic=0.20, paper=0.30, other=0.00)
        for p in PATHWAYS:
            self.assertEqual(
                check_extended(p, fs),
                check_pathway(p, fs),
                msg=f"Delegation mismatch for pathway {p!r}",
            )

    def test_feasibility_result_json_serialisable(self):
        f = check_extended("htc", _make_feedstock(moisture=0.65))
        json.dumps({
            "pathway": f.pathway,
            "feasible": f.feasible,
            "reasons": f.reasons,
            "basis": f.basis,
        })


if __name__ == "__main__":
    unittest.main()
