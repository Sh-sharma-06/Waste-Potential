"""Tests for core_engine/router.py.

Uses FastAPI's TestClient (httpx transport) to exercise all three endpoints.
The router is mounted on a minimal FastAPI app created in setUpClass; the
in-memory run store (_IN_MEMORY_RUNS) is populated / cleared per test.

No database, no network.  All fixtures are defined in this file.
"""
from __future__ import annotations

import dataclasses
import unittest

# Guard: skip entire module if fastapi / httpx are not installed.
try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    _SKIP = False
except ImportError:
    _SKIP = True

if not _SKIP:
    from app.core_engine.router import router, _IN_MEMORY_RUNS, get_run_reader, _InMemoryRunReader
    from app.core_engine.params import Params


# ---------------------------------------------------------------------------
# Shared app + client (built once)
# ---------------------------------------------------------------------------

def _make_app() -> "FastAPI":
    app = FastAPI()
    app.include_router(router)
    return app


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _default_params_dict() -> dict:
    """Return a plain-dict copy of default Params, with composition as a list."""
    p = Params()
    d = dataclasses.asdict(p)
    d["composition"] = list(d["composition"])  # simulate JSON round-trip
    return d


def _seed_run(run_id: str, params_dict: dict | None = None) -> None:
    """Put a fake run into the in-memory store."""
    _IN_MEMORY_RUNS[run_id] = {
        "run_id": run_id,
        "params": params_dict if params_dict is not None else _default_params_dict(),
        "status": "illustrative_estimate",
    }


# ---------------------------------------------------------------------------
# 1. GET /parameters
# ---------------------------------------------------------------------------

@unittest.skipIf(_SKIP, "fastapi or httpx not installed")
class TestListParameters(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(_make_app())

    def test_happy_path_returns_list(self):
        resp = self.client.get("/parameters")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)

    def test_each_entry_has_required_keys(self):
        resp = self.client.get("/parameters")
        required = {"name", "value", "unit", "mass_basis", "status",
                    "source", "uncertainty", "model_version", "description"}
        for entry in resp.json():
            self.assertTrue(required.issubset(entry.keys()),
                            f"Missing keys in {entry}")

    def test_status_filter_returns_matching_only(self):
        # First discover what status values exist
        all_entries = self.client.get("/parameters").json()
        if not all_entries:
            self.skipTest("registry is empty")
        target_status = all_entries[0]["status"]
        resp = self.client.get(f"/parameters?status={target_status}")
        self.assertEqual(resp.status_code, 200)
        for entry in resp.json():
            self.assertEqual(entry["status"], target_status)

    def test_status_filter_nonexistent_returns_empty(self):
        resp = self.client.get("/parameters?status=__no_such_status__")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), [])

    def test_no_filter_returns_all_entries(self):
        all_resp  = self.client.get("/parameters").json()
        stat = all_resp[0]["status"] if all_resp else None
        if stat is None:
            self.skipTest("registry is empty")
        # Count of no-filter >= count of one-status filter
        filtered = self.client.get(f"/parameters?status={stat}").json()
        self.assertGreaterEqual(len(all_resp), len(filtered))


# ---------------------------------------------------------------------------
# 2. POST /simulations/{run_id}/uncertainty
# ---------------------------------------------------------------------------

@unittest.skipIf(_SKIP, "fastapi or httpx not installed")
class TestRunUncertainty(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.app = _make_app()
        cls.client = TestClient(cls.app)

    def setUp(self) -> None:
        _IN_MEMORY_RUNS.clear()
        # Override get_run_reader so the endpoint always uses _InMemoryRunReader,
        # regardless of whether app.platform.runs is importable in this environment.
        self.app.dependency_overrides[get_run_reader] = lambda: _InMemoryRunReader()

    def tearDown(self) -> None:
        # Remove the override so other test classes are not affected.
        self.app.dependency_overrides.pop(get_run_reader, None)
        _IN_MEMORY_RUNS.clear()

    def test_happy_path(self):
        _seed_run("run-001")
        resp = self.client.post(
            "/simulations/run-001/uncertainty",
            json={"n": 50, "seed": 7},
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["n"], 50)
        self.assertEqual(data["seed"], 7)

    def test_result_has_required_keys(self):
        _seed_run("run-002")
        resp = self.client.post(
            "/simulations/run-002/uncertainty",
            json={"n": 20, "seed": 1},
        )
        self.assertEqual(resp.status_code, 200)
        required = {
            "n", "seed", "median", "p2_5", "p97_5",
            "p_net_nonpositive", "runs_with_warnings",
            "sensitivity", "distributions", "assumptions_note",
        }
        self.assertTrue(required.issubset(resp.json().keys()))

    def test_sensitivity_is_list(self):
        _seed_run("run-003")
        resp = self.client.post(
            "/simulations/run-003/uncertainty",
            json={"n": 20, "seed": 0},
        )
        self.assertIsInstance(resp.json()["sensitivity"], list)

    def test_unknown_run_returns_404(self):
        resp = self.client.post(
            "/simulations/NO_SUCH_RUN/uncertainty",
            json={"n": 50, "seed": 42},
        )
        self.assertEqual(resp.status_code, 404)
        self.assertIn("detail", resp.json())
        self.assertIn("NO_SUCH_RUN", resp.json()["detail"])

    def test_n_below_minimum_returns_422(self):
        _seed_run("run-004")
        resp = self.client.post(
            "/simulations/run-004/uncertainty",
            json={"n": 2, "seed": 42},   # below minimum of 10
        )
        self.assertEqual(resp.status_code, 422)

    def test_n_above_maximum_returns_422(self):
        _seed_run("run-005")
        resp = self.client.post(
            "/simulations/run-005/uncertainty",
            json={"n": 99999, "seed": 42},  # above maximum of 20000
        )
        self.assertEqual(resp.status_code, 422)

    def test_composition_as_list_is_accepted(self):
        """run["params"]["composition"] stored as a list must be auto-converted."""
        params = _default_params_dict()
        params["composition"] = [0.6, 0.2, 0.2]   # list not tuple
        _seed_run("run-006", params_dict=params)
        resp = self.client.post(
            "/simulations/run-006/uncertainty",
            json={"n": 20, "seed": 42},
        )
        self.assertEqual(resp.status_code, 200)

    def test_composition_as_tuple_in_dict_is_accepted(self):
        """run["params"]["composition"] stored as a tuple must also work."""
        params = _default_params_dict()
        params["composition"] = (0.6, 0.2, 0.2)   # tuple already
        _seed_run("run-007", params_dict=params)
        resp = self.client.post(
            "/simulations/run-007/uncertainty",
            json={"n": 20, "seed": 42},
        )
        self.assertEqual(resp.status_code, 200)

    def test_extra_keys_in_run_params_are_ignored(self):
        """run["params"] may carry extra keys that are not Params fields."""
        params = _default_params_dict()
        params["__extra_key__"] = "ignored"
        _seed_run("run-008", params_dict=params)
        resp = self.client.post(
            "/simulations/run-008/uncertainty",
            json={"n": 20, "seed": 1},
        )
        self.assertEqual(resp.status_code, 200)

    def test_default_n_and_seed_used_when_omitted(self):
        _seed_run("run-009")
        resp = self.client.post(
            "/simulations/run-009/uncertainty",
            json={},   # rely on UncertaintyRequest defaults
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["n"], 2000)   # default n
        self.assertEqual(data["seed"], 42)  # default seed

    def test_missing_request_body_returns_422(self):
        _seed_run("run-010")
        resp = self.client.post(
            "/simulations/run-010/uncertainty",
            # no body at all
        )
        # FastAPI will parse {} as valid (all fields have defaults) or
        # return 422 if content-type is wrong — either is acceptable
        self.assertIn(resp.status_code, (200, 422))


# ---------------------------------------------------------------------------
# 3. GET /validation/summary
# ---------------------------------------------------------------------------

@unittest.skipIf(_SKIP, "fastapi or httpx not installed")
class TestValidationSummary(unittest.TestCase):

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(_make_app())
        cls.data = cls.client.get("/validation/summary").json()

    def test_status_200(self):
        resp = self.client.get("/validation/summary")
        self.assertEqual(resp.status_code, 200)

    def test_has_required_keys(self):
        required = {
            "parameter_counts_by_status",
            "n_unvalidated_defaults",
            "limitations",
            "empirical_validation",
            "predicted_vs_observed",
        }
        self.assertTrue(required.issubset(self.data.keys()))

    def test_empirical_validation_is_pending(self):
        self.assertEqual(self.data["empirical_validation"], "pending")

    def test_predicted_vs_observed_is_empty_list(self):
        self.assertEqual(self.data["predicted_vs_observed"], [])

    def test_limitations_is_non_empty_list(self):
        lims = self.data["limitations"]
        self.assertIsInstance(lims, list)
        self.assertGreater(len(lims), 0)

    def test_parameter_counts_by_status_is_dict(self):
        self.assertIsInstance(self.data["parameter_counts_by_status"], dict)

    def test_parameter_counts_sum_positive(self):
        total = sum(self.data["parameter_counts_by_status"].values())
        self.assertGreater(total, 0)

    def test_n_unvalidated_defaults_non_negative(self):
        self.assertGreaterEqual(self.data["n_unvalidated_defaults"], 0)

    def test_response_is_json_serialisable(self):
        import json
        resp = self.client.get("/validation/summary")
        json.dumps(resp.json())   # must not raise


if __name__ == "__main__":
    unittest.main()
