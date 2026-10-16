import unittest
from dataclasses import replace
from app.core_engine.engine import *


class T(unittest.TestCase):
    def test_water_sign_dilution(self):
        self.assertAlmostEqual(condition_water(100, .73, .90), 170.0, places=6)

    def test_water_sign_dewater(self):
        self.assertAlmostEqual(condition_water(100, .95, .90), -50.0, places=6)

    def test_old_blueprint_formula_was_wrong(self):
        old = 100 * (.73 - .90) / (1 - .90)
        self.assertNotAlmostEqual(old, condition_water(100, .73, .90))

    def test_solids_conserved_after_conditioning(self):
        m, xi, xt = 360, .73, .90
        new = m + condition_water(m, xi, xt)
        self.assertAlmostEqual(m * (1 - xi), new * (1 - xt), places=9)

    def test_mass_closure(self):
        r = simulate(Params())
        self.assertAlmostEqual(r["mass_residual_kg"], 0.0, places=9)
        self.assertGreater(r["digestate_kg_d"], 0)

    def test_rejects_accounted(self):
        r = simulate(Params())
        self.assertAlmostEqual(r["organic_kg_d"], r["suitable_kg_d"] + r["rejected_kg_d"])

    def test_blueprint_chain_arithmetic(self):
        vb = 360 * 0.10; vm = vb * .6; ech = vm * 9.94
        self.assertAlmostEqual(vm, 21.6); self.assertAlmostEqual(ech, 214.704, 3)
        self.assertAlmostEqual(ech * .35 - 10, 65.1464, 3)

    def test_no_negative_outputs(self):
        for f in (0, .1, .5, 1):
            r = simulate(replace(Params(), organic_fraction=f))
            for k, v in r.items():
                if isinstance(v, float) and k not in ("e_net_kwh_d", "heat_surplus_kwh_d", "water_added_kg_d"):
                    self.assertGreaterEqual(v, -1e-9, k)

    def test_net_le_gross(self):
        r = simulate(Params()); self.assertLess(r["e_net_kwh_d"], r["e_gross_kwh_d"])

    def test_energy_monotonic_in_yield(self):
        a = simulate(replace(Params(), y_biogas_nm3_per_kg_vs=.4))["e_gross_kwh_d"]
        b = simulate(replace(Params(), y_biogas_nm3_per_kg_vs=.6))["e_gross_kwh_d"]
        self.assertLess(a, b)

    def test_zero_availability_gives_negative_net_and_warning(self):
        r = simulate(replace(Params(), availability=0.0))
        self.assertLess(r["e_net_kwh_d"], 0)
        self.assertTrue(any("net electricity" in x for x in r["warnings"]))

    def test_buswell_guardrail_fires(self):
        r = simulate(replace(Params(), y_biogas_nm3_per_kg_vs=1.5))
        self.assertTrue(any("Buswell" in x for x in r["warnings"]))

    def test_default_inside_buswell(self):
        r = simulate(Params()); self.assertLess(r["ch4_nm3_per_kg_vs"], r["buswell_bound"])

    def test_cold_climate_boiler_kicks_in(self):
        r = simulate(replace(Params(), ambient_temp_c=-15, u_wall_w_m2k=3.0))
        self.assertGreater(r["boiler_chem_kwh_d"], 0)
        self.assertLess(r["e_gross_kwh_d"], simulate(Params())["e_gross_kwh_d"])

    def test_no_double_count_slip(self):
        a = simulate(replace(Params(), ch4_slip=0, availability=1))
        self.assertAlmostEqual(a["e_chem_kwh_d"], a["ch4_nm3_d"] * LHV_CH4_KWH_NM3, 6)

    def test_energy_balance_chem_to_outputs(self):
        r = simulate(Params())
        chp_chem = r["e_chem_kwh_d"] - r["flared_kwh_d"] - r["boiler_chem_kwh_d"]
        self.assertAlmostEqual(r["e_gross_kwh_d"], chp_chem * .35, 6)

    def test_cost_undefined_when_net_nonpositive(self):
        self.assertIsNone(cost_per_kwh(1000, -3)); self.assertIsNone(cost_per_kwh(1000, 0))
        self.assertAlmostEqual(cost_per_kwh(36500, 10), 10.0)

    def test_bad_inputs_raise(self):
        with self.assertRaises(ValueError): simulate(replace(Params(), total_mass_kg_d=-1))
        with self.assertRaises(ValueError): condition_water(100, 1.2, .9)


if __name__ == "__main__":
    unittest.main(verbosity=2)