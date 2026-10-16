"""Tests for the core_engine public API surface (test_public_api.py)."""
import dataclasses
import importlib
import pkgutil
import sys
import types
import unittest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_params():
    from app.core_engine import Params
    return dataclasses.replace(
        Params(),
        total_mass_kg_d=1000,
        organic_fraction=0.45,
        suitable_fraction=0.7,
        y_biogas_nm3_per_kg_vs=0.6,
    )


# ---------------------------------------------------------------------------
# 1. Orchestrator compatibility
# ---------------------------------------------------------------------------

class TestOrchestratorCompat(unittest.TestCase):
    def test_simulate_returns_warnings_list_of_str(self):
        from app.core_engine import simulate
        p = _make_params()
        r = simulate(p)
        self.assertIn("warnings", r)
        warnings = r["warnings"]
        self.assertIsInstance(warnings, list)
        for w in warnings:
            self.assertIsInstance(w, str,
                msg=f"warning entry is not str: {w!r}")

    def test_simulate_returns_e_net_kwh_d_float(self):
        from app.core_engine import simulate
        p = _make_params()
        r = simulate(p)
        self.assertIn("e_net_kwh_d", r)
        self.assertIsInstance(r["e_net_kwh_d"], float)

    def test_simulate_result_is_dict(self):
        from app.core_engine import simulate
        p = _make_params()
        r = simulate(p)
        self.assertIsInstance(r, dict)


# ---------------------------------------------------------------------------
# 2. Frozen contract — four required field names exist on Params
# ---------------------------------------------------------------------------

class TestFrozenContract(unittest.TestCase):
    def test_total_mass_kg_d_field_exists(self):
        from app.core_engine import Params
        fields = {f.name for f in dataclasses.fields(Params)}
        self.assertIn("total_mass_kg_d", fields)

    def test_organic_fraction_field_exists(self):
        from app.core_engine import Params
        fields = {f.name for f in dataclasses.fields(Params)}
        self.assertIn("organic_fraction", fields)

    def test_suitable_fraction_field_exists(self):
        from app.core_engine import Params
        fields = {f.name for f in dataclasses.fields(Params)}
        self.assertIn("suitable_fraction", fields)

    def test_y_biogas_nm3_per_kg_vs_field_exists(self):
        from app.core_engine import Params
        fields = {f.name for f in dataclasses.fields(Params)}
        self.assertIn("y_biogas_nm3_per_kg_vs", fields)

    def test_params_is_frozen(self):
        from app.core_engine import Params
        p = Params()
        with self.assertRaises((dataclasses.FrozenInstanceError, TypeError, AttributeError)):
            p.total_mass_kg_d = 999.0  # type: ignore[misc]

    def test_params_fields_accept_replace(self):
        from app.core_engine import Params
        p = _make_params()
        self.assertEqual(p.total_mass_kg_d, 1000.0)
        self.assertEqual(p.organic_fraction, 0.45)
        self.assertEqual(p.suitable_fraction, 0.7)
        self.assertEqual(p.y_biogas_nm3_per_kg_vs, 0.6)


# ---------------------------------------------------------------------------
# 3. Determinism — simulate(p) twice gives equal dicts
# ---------------------------------------------------------------------------

class TestDeterminism(unittest.TestCase):
    def test_simulate_same_result_twice(self):
        from app.core_engine import simulate
        p = _make_params()
        r1 = simulate(p)
        r2 = simulate(p)
        self.assertEqual(r1, r2)

    def test_simulate_default_params_deterministic(self):
        from app.core_engine import Params, simulate
        p = Params()
        self.assertEqual(simulate(p), simulate(p))

    def test_simulate_different_params_differ(self):
        from app.core_engine import Params, simulate
        r_low = simulate(dataclasses.replace(Params(), total_mass_kg_d=500.0))
        r_high = simulate(dataclasses.replace(Params(), total_mass_kg_d=2000.0))
        self.assertNotEqual(r_low["e_net_kwh_d"], r_high["e_net_kwh_d"])


# ---------------------------------------------------------------------------
# 4. No forbidden imports at module level inside core_engine
# ---------------------------------------------------------------------------

_FORBIDDEN = {"app.ml", "app.data", "app.decision", "app.platform"}

# The one allowed lazy reference: router.get_run_reader may import app.platform
# at call time, but not at import time.

def _core_engine_module_names():
    """Return all module names inside app.core_engine (excluding tests)."""
    import app.core_engine  # noqa: F401
    pkg = sys.modules.get("app.core_engine")
    if pkg is None or not hasattr(pkg, "__path__"):
        return []
    names = []
    for _, modname, _ in pkgutil.walk_packages(pkg.__path__, prefix="app.core_engine."):
        if ".tests" not in modname:
            names.append(modname)
    return names


class TestNoForbiddenImports(unittest.TestCase):

    def _get_module_imports(self, module_name: str):
        """Return the set of top-level module names imported by module_name."""
        mod = sys.modules.get(module_name)
        if mod is None:
            try:
                mod = importlib.import_module(module_name)
            except Exception:
                return set()
        return set(sys.modules.keys())

    def test_no_forbidden_at_import_time(self):
        """After importing all core_engine modules, none of the forbidden
        packages should appear in sys.modules (they weren't imported at module
        level by any core_engine module)."""
        # Snapshot before
        before = set(sys.modules.keys())

        # Import every non-test core_engine sub-module
        for name in _core_engine_module_names():
            try:
                importlib.import_module(name)
            except Exception:
                pass  # some modules may have optional deps; skip import errors

        after = set(sys.modules.keys())
        newly_loaded = after - before

        for forbidden in _FORBIDDEN:
            # A match means the exact package or any sub-module was loaded
            loaded_forbidden = [m for m in newly_loaded
                                 if m == forbidden or m.startswith(forbidden + ".")]
            # The only allowed exception: app.platform.runs imported lazily
            # inside router.get_run_reader — it should NOT appear unless called.
            self.assertEqual(
                loaded_forbidden, [],
                msg=(
                    f"Importing core_engine modules caused {loaded_forbidden!r} "
                    f"to be loaded. These packages must not be imported at module "
                    f"level inside app.core_engine (except lazily in router)."
                ),
            )

    def test_all_exported_names_present(self):
        """Every name in __all__ must be importable from app.core_engine."""
        import app.core_engine as ce
        for name in ce.__all__:
            self.assertTrue(
                hasattr(ce, name),
                msg=f"app.core_engine.__all__ lists {name!r} but it is not an attribute",
            )

    def test_router_is_a_module(self):
        """The exported 'router' must be the core_engine.router module
        (FastAPI APIRouter lives inside it)."""
        import app.core_engine as ce
        self.assertIsInstance(ce.router, types.ModuleType)

    def test_all_is_a_list_of_strings(self):
        import app.core_engine as ce
        self.assertIsInstance(ce.__all__, list)
        for name in ce.__all__:
            self.assertIsInstance(name, str)


if __name__ == "__main__":
    unittest.main()
