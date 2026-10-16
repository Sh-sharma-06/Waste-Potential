"""Independent audit of B1 (params, registry, guardrails, engine). Written from the spec."""
import csv, dataclasses, os, unittest
from dataclasses import replace

from app.core_engine.engine import simulate, buswell_bound as eng_bound
from app.core_engine.params import Params
from app.core_engine import guardrails as g
from app.core_engine import registry as reg

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), *[".."] * 4))
CSV = os.path.join(REPO, "docs", "parameter_registry.csv")

FIELDS = ["total_mass_kg_d", "organic_fraction", "suitable_fraction", "ts_fraction",
          "vs_of_ts", "target_ts", "y_biogas_nm3_per_kg_vs", "ch4_fraction", "ch4_slip",
          "availability", "eta_el", "eta_th", "eta_boiler", "digester_temp_c",
          "ambient_temp_c", "hrt_days", "cp_kj_kg_k", "u_wall_w_m2k", "aux_mix_kwh_m3_d",
          "aux_sort_kwh_t", "aux_gas_kwh_nm3", "composition"]


class TestParamsContract(unittest.TestCase):
    def test_exact_fields_in_order(self):
        self.assertEqual([f.name for f in dataclasses.fields(Params)], FIELDS)

    def test_frozen(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            Params().hrt_days = 5

    def test_key_defaults(self):
        p = Params()
        self.assertEqual((p.total_mass_kg_d, p.organic_fraction, p.suitable_fraction), (1000.0, 0.45, 0.80))
        self.assertEqual((p.hrt_days, p.eta_el, p.ch4_slip), (30.0, 0.35, 0.015))

    def test_implausible_but_valid_values_construct(self):
        replace(Params(), availability=0.0)
        replace(Params(), y_biogas_nm3_per_kg_vs=1.5)
        replace(Params(), ambient_temp_c=-15.0)

    def test_invalid_values_rejected(self):
        for kw in ({"organic_fraction": 1.2}, {"ch4_fraction": -0.1}, {"hrt_days": -1},
                   {"composition": (0.5, 0.2, 0.2)}, {"eta_boiler": 0.40, "eta_th": 0.45}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                replace(Params(), **kw)


class TestEngineGolden(unittest.TestCase):
    def test_default_run(self):
        r = simulate(Params())
        for k, v in {"suitable_kg_d": 360, "water_added_kg_d": 612, "feed_kg_d": 972,
                     "biogas_nm3_d": 47.045, "e_gross_kwh_d": 87.055,
                     "aux_kwh_d": 10.315, "e_net_kwh_d": 76.741}.items():
            self.assertAlmostEqual(r[k], v, delta=1e-2, msg=k)


class TestGuardrails(unittest.TestCase):
    def test_buswell_matches_engine(self):
        self.assertAlmostEqual(g.buswell_bound((0.6, 0.2, 0.2)), 0.551, places=3)
        self.assertAlmostEqual(g.buswell_bound((0.6, 0.2, 0.2)), eng_bound((0.6, 0.2, 0.2)), places=9)

    def test_buswell_pure_components(self):
        self.assertAlmostEqual(g.buswell_bound((1, 0, 0)), 0.415, places=3)
        self.assertAlmostEqual(g.buswell_bound((0, 0, 1)), 1.014, places=3)

    def test_buswell_bad_sum(self):
        with self.assertRaises(ValueError):
            g.buswell_bound((0.5, 0.2, 0.2))

    def test_methane_yield_check(self):
        self.assertIsNone(g.check_methane_yield(0.33, 0.551))
        self.assertIsNone(g.check_methane_yield(0.551, 0.551))      # equal is allowed
        self.assertIsInstance(g.check_methane_yield(0.60, 0.551), str)

    def test_vs_destruction_edges(self):
        self.assertIsNone(g.check_vs_destruction(85.0, 100.0))       # exactly 0.85
        self.assertIsInstance(g.check_vs_destruction(85.1, 100.0), str)
        self.assertIsNone(g.check_vs_destruction(50.0, 0.0))         # no divide by zero
        self.assertIsNone(g.check_vs_destruction(95.0, 100.0, limit=0.96))  # custom limit

    def test_input_ranges(self):
        self.assertEqual(list(g.check_input_ranges(Params())), [])
        bad = g.check_input_ranges(replace(Params(), hrt_days=5.0))
        self.assertTrue(any(item[0] == "hrt_days" for item in bad))
        bad = g.check_input_ranges(replace(Params(), ts_fraction=0.6))
        self.assertTrue(any(item[0] == "ts_fraction" for item in bad))

    def test_ranges_use_real_field_names(self):
        for key in g.SUPPORTED_RANGES:
            self.assertIn(key, FIELDS, key)

    def test_elemental_balance_independent_proof(self):
        for formula, ref in (("C6H10O5", 0.415), ("C5H7NO2", 0.496), ("C57H104O6", 1.014)):
            with self.subTest(formula=formula):
                bal = g.atom_balance(formula)
                vals = bal.values() if isinstance(bal, dict) else bal
                for resid in vals:
                    self.assertLess(abs(resid), 1e-9)
                y = g.theoretical_ch4_nm3_per_kg_vs(formula)
                self.assertLess(abs(y - ref) / ref, 0.01)


class TestRegistry(unittest.TestCase):
    def setUp(self):
        with open(CSV, newline="", encoding="utf-8") as f:
            self.rows = list(csv.DictReader(f))

    def test_columns(self):
        want = {"name", "value", "unit", "mass_basis", "status", "source",
                "uncertainty", "model_version", "description"}
        self.assertTrue(want <= set(self.rows[0].keys()))

    def test_one_row_per_field(self):
        names = [r["name"] for r in self.rows]
        self.assertEqual(sorted(names), sorted(FIELDS))
        self.assertEqual(len(names), len(set(names)))

    def test_values_equal_defaults(self):
        p = Params()
        for r in self.rows:
            if r["name"] == "composition":
                continue
            self.assertAlmostEqual(float(r["value"]), getattr(p, r["name"]), places=9, msg=r["name"])

    def test_all_illustrative_and_units_present(self):
        for r in self.rows:
            self.assertEqual(r["status"], "illustrative", r["name"])
            self.assertTrue(r["unit"].strip() != "" or r["name"] in
                            ("organic_fraction", "suitable_fraction", "ts_fraction", "vs_of_ts",
                             "target_ts", "ch4_fraction", "ch4_slip", "availability",
                             "eta_el", "eta_th", "eta_boiler", "composition"), r["name"])

    def test_assumed_distributions_recorded(self):
        text = {r["name"]: r["uncertainty"] for r in self.rows}
        for n in ("y_biogas_nm3_per_kg_vs", "ts_fraction", "suitable_fraction", "eta_el"):
            self.assertIn("ASSUMED", text[n], n)

    def test_defaults_used_lists_all_22(self):
        self.assertEqual(sorted(reg.defaults_used(Params())), sorted(FIELDS))

    def test_unknown_name_raises(self):
        with self.assertRaises(Exception):
            reg.get("not_a_parameter")

    def test_constants_not_in_params_registry(self):
        names = {r["name"] for r in self.rows}
        self.assertFalse({"LHV_CH4", "BUSWELL_CARB", "BUSWELL_PROT", "BUSWELL_LIP"} & names)


if __name__ == "__main__":
    unittest.main()