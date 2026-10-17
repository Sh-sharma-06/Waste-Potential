"""Tests for import-order safety after the PEP 562 lazy-router fix.

Each module that previously triggered the circular import is imported in a
fresh subprocess so that sys.modules state from the test runner cannot mask
failures.  The golden-run and router-structure assertions run in-process.
"""
from __future__ import annotations

import os
import subprocess
import sys
import unittest

# Derive the backend directory from this file's location:
# .../backend/app/core_engine/tests/test_import_order.py
#   -> dirname = tests/  ->  ../../../  = backend/
_BACKEND_DIR = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..")
)


def _import_ok(module: str) -> tuple[int, str]:
    """Run ``python -c "import <module>"`` in a fresh subprocess under *_BACKEND_DIR*.

    Returns (returncode, combined_stderr) so callers can embed stderr in the
    failure message.
    """
    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        cwd=_BACKEND_DIR,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stderr.strip()


class TestFreshSubprocessImports(unittest.TestCase):
    """Each module must be importable in isolation (fresh Python process)."""

    def _assert_importable(self, module: str) -> None:
        rc, err = _import_ok(module)
        self.assertEqual(
            rc,
            0,
            f"Fresh import of '{module}' failed (returncode={rc}):\n{err}",
        )

    def test_import_app_platform_runs(self) -> None:
        self._assert_importable("app.platform.runs")

    def test_import_app_schemas_simulation(self) -> None:
        self._assert_importable("app.schemas.simulation")

    def test_import_app_core_engine(self) -> None:
        self._assert_importable("app.core_engine")

    def test_import_app_core_engine_router(self) -> None:
        self._assert_importable("app.core_engine.router")

    def test_import_app_core_engine_params(self) -> None:
        self._assert_importable("app.core_engine.params")

    def test_import_app_main(self) -> None:
        self._assert_importable("app.main")


class TestLazyRouterAttribute(unittest.TestCase):
    """``from app.core_engine import router`` must return the router MODULE and
    that module must expose an APIRouter with the three expected route paths."""

    @classmethod
    def setUpClass(cls) -> None:
        from app.core_engine import router as _router_mod  # noqa: PLC0415
        cls.router_mod = _router_mod

    def test_router_is_module(self) -> None:
        import types
        self.assertIsInstance(self.router_mod, types.ModuleType)

    def test_router_has_router_attribute(self) -> None:
        self.assertTrue(
            hasattr(self.router_mod, "router"),
            "router module must expose an 'router' attribute (the APIRouter)",
        )

    def test_route_parameters_present(self) -> None:
        paths = [r.path for r in self.router_mod.router.routes]
        self.assertIn("/parameters", paths)

    def test_route_uncertainty_present(self) -> None:
        paths = [r.path for r in self.router_mod.router.routes]
        self.assertIn("/simulations/{run_id}/uncertainty", paths)

    def test_route_validation_summary_present(self) -> None:
        paths = [r.path for r in self.router_mod.router.routes]
        self.assertIn("/validation/summary", paths)


class TestGoldenRun(unittest.TestCase):
    """Default Params() golden values must be stable within 1e-3."""

    @classmethod
    def setUpClass(cls) -> None:
        from app.core_engine.engine import simulate
        from app.core_engine.params import Params
        cls.result = simulate(Params())

    def test_e_net_kwh_d_golden(self) -> None:
        self.assertAlmostEqual(
            self.result["e_net_kwh_d"], 76.7406, delta=1e-3,
            msg="e_net_kwh_d deviates from golden value 76.7406",
        )

    def test_biogas_nm3_d_golden(self) -> None:
        self.assertAlmostEqual(
            self.result["biogas_nm3_d"], 47.0448, delta=1e-3,
            msg="biogas_nm3_d deviates from golden value 47.0448",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
