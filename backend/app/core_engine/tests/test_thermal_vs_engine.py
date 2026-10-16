import unittest
from dataclasses import replace
from app.core_engine.engine import simulate
from app.core_engine.params import Params
from app.core_engine.thermal import heat_demand_kwh, split_chp_boiler


def _demand(p, r):
    return heat_demand_kwh(r["feed_kg_d"], p.digester_temp_c - p.ambient_temp_c,
                           r["digester_m3"], p.cp_kj_kg_k, p.u_wall_w_m2k)


class TestThermalMatchesEngine(unittest.TestCase):
    def test_default_demand(self):
        p = Params(); r = simulate(p)
        self.assertAlmostEqual(_demand(p, r).total_kwh_d, r["q_demand_kwh_d"], places=6)

    def test_reference_split(self):
        d = _demand(Params(), simulate(Params()))
        self.assertAlmostEqual(d.feed_heating_kwh_d, 12.96, delta=0.05)
        self.assertAlmostEqual(d.wall_loss_kwh_d, 7.55, delta=0.05)

    def test_cold_case_boiler(self):
        p = replace(Params(), ambient_temp_c=-15, u_wall_w_m2k=3.0)
        r = simulate(p)
        d = _demand(p, r)
        self.assertAlmostEqual(d.total_kwh_d, r["q_demand_kwh_d"], places=6)
        c_chem = r["e_chem_kwh_d"] * p.availability
        s = split_chp_boiler(c_chem, d.total_kwh_d, p.eta_th, p.eta_boiler)
        self.assertAlmostEqual(s.boiler_fuel_kwh_d, r["boiler_chem_kwh_d"], places=6)
        self.assertGreater(s.boiler_fuel_kwh_d, 0)


if __name__ == "__main__":
    unittest.main()