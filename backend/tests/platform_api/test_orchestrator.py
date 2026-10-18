"""Tests for simulation orchestration (app/platform/orchestrator.py) and
POST /simulations, plus the P1 run-reader interface."""

from __future__ import annotations

import dataclasses
import threading
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core_engine import Params, simulate
from app.data.service import get_stream
from app.main import create_app
from app.platform import orchestrator
from app.platform.audit import compute_audit_hash, run_id_from_hash
from app.platform.orchestrator import (
    ENGINE_MODEL_VERSION,
    SimulationInputError,
    resolve_params,
    run_simulation,
)
from app.platform.runs import RunReader, RunStore, get_run_store
from app.schemas.simulation import SimRequest

GOLDEN = {"waste_mass_kg_day": 1000, "organic_fraction": 0.45, "suitable_fraction": 0.80}
STREAM = get_stream("any")
STREAM_MASS = STREAM["total_mass_kg_d"]["value"]
STREAM_ORGANIC = STREAM["organic_fraction"]["value"]


@pytest.fixture
def store() -> RunStore:
    return RunStore()


@pytest.fixture
def client(store):
    app = create_app()
    app.dependency_overrides[get_run_store] = lambda: store
    return TestClient(app)


def _req(**fields) -> SimRequest:
    return SimRequest(**fields)


# ---------------------------------------------------------------------------
# 1. P1 golden run
# ---------------------------------------------------------------------------

def test_golden_run(client, store):
    resp = client.post("/simulations", json=GOLDEN)
    assert resp.status_code == 200
    body = resp.json()

    assert body["results"]["e_net_kwh_d"] == pytest.approx(76.7406, abs=1e-4)
    assert body["results"]["biogas_nm3_d"] == pytest.approx(47.0448, abs=1e-4)
    assert body["status"] == "illustrative_estimate"
    assert body["results"]["status"] == "illustrative_estimate"
    assert body["model_version"] == ENGINE_MODEL_VERSION == "engine-0.2"
    assert body["id"] == body["audit_hash"][:12]
    assert body["notes"]["location"] is None
    assert body["notes"]["orchestrator"]["ml_yield"] == "not_used"
    assert len(store) == 1


def test_golden_run_matches_direct_engine_call():
    resp = run_simulation(_req(**GOLDEN), store=RunStore())
    expected = simulate(dataclasses.replace(
        Params(), total_mass_kg_d=1000.0, organic_fraction=0.45, suitable_fraction=0.80
    ))
    assert resp.results.model_dump() == expected


def test_response_carries_all_final_params_and_engine_metadata():
    resp = run_simulation(_req(**GOLDEN), store=RunStore())
    assert set(resp.params) == {f.name for f in dataclasses.fields(Params)}
    assert resp.defaults_used_unvalidated  # from core_engine.defaults_used
    assert resp.warnings_detail == []      # golden run triggers no rule warnings
    assert resp.missing_inputs == []


def test_rule_warnings_populate_warnings_detail():
    # eta_el=0 → negative net electricity → NEG_NET rule
    resp = run_simulation(_req(waste_mass_kg_day=1000, overrides={"eta_el": 0.0}), store=RunStore())
    assert resp.results.e_net_kwh_d < 0
    assert "NEG_NET" in {w.code for w in resp.warnings_detail}


@pytest.mark.parametrize(
    "field, value",
    [("hrt_days", 0.0), ("digester_temp_c", -50.0)],
)
def test_engine_extrapolation_reports_out_of_range_not_ml(field, value):
    resp = run_simulation(_req(waste_mass_kg_day=1000, overrides={field: value}), store=RunStore())
    assert resp.status == resp.results.status == "extrapolation"
    assert resp.results.out_of_range_inputs == [field]

    codes = [w.code for w in resp.warnings_detail]
    assert codes.count("OUT_OF_RANGE") == 1
    oor = next(w for w in resp.warnings_detail if w.code == "OUT_OF_RANGE")
    assert field in oor.message
    # extrapolation_flag is ML-specific; no ML estimate was used.
    assert "ML_EXTRAPOLATION" not in codes
    assert resp.notes["orchestrator"]["ml_yield"] == "not_used"


def test_in_range_run_has_no_extrapolation_warnings():
    resp = run_simulation(_req(**GOLDEN), store=RunStore())
    codes = {w.code for w in resp.warnings_detail}
    assert resp.status == "illustrative_estimate"
    assert not codes & {"OUT_OF_RANGE", "ML_EXTRAPOLATION"}


def test_rule_warnings_called_with_ml_flag_false_for_extrapolated_run():
    with patch.object(orchestrator, "rule_warnings", wraps=orchestrator.rule_warnings) as rw:
        run_simulation(_req(waste_mass_kg_day=1000, overrides={"hrt_days": 0.0}), store=RunStore())
    (result,), kwargs = rw.call_args
    assert result["status"] == "extrapolation"
    assert kwargs == {"extrapolation_flag": False}


# ---------------------------------------------------------------------------
# 2. Missing mass
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "body",
    [{}, {"organic_fraction": 0.5}, {"overrides": {"hrt_days": 25.0}}],
    ids=["empty", "fraction-only", "unrelated-override"],
)
def test_missing_mass_returns_422_and_saves_nothing(client, store, body):
    resp = client.post("/simulations", json=body)
    assert resp.status_code == 422
    assert "waste mass is required" in resp.json()["detail"]
    assert len(store) == 0


def test_mass_from_overrides_is_accepted():
    params, sources, _ = resolve_params(_req(overrides={"total_mass_kg_d": 500.0}))
    assert params.total_mass_kg_d == 500.0
    assert sources["total_mass_kg_d"] == "override"


@pytest.mark.parametrize(
    "literal, fragment",
    [
        ("0", "total_mass_kg_d must be > 0"),
        ("0.0", "total_mass_kg_d must be > 0"),
        ("-1", "total_mass_kg_d must be > 0"),
        ("-1e-9", "total_mass_kg_d must be > 0"),
        ("NaN", "must be a finite number"),
        ("Infinity", "must be a finite number"),
        ("-Infinity", "must be a finite number"),
    ],
)
@pytest.mark.parametrize("with_request_mass", [False, True], ids=["override-only", "override-beats-request"])
def test_invalid_override_mass_returns_422_and_saves_nothing(
    client, store, literal, fragment, with_request_mass
):
    request_mass = '"waste_mass_kg_day": 1000, ' if with_request_mass else ""
    raw = f'{{{request_mass}"overrides": {{"total_mass_kg_d": {literal}}}}}'
    resp = client.post(
        "/simulations", content=raw.encode(), headers={"content-type": "application/json"}
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert isinstance(detail, str)
    assert "total_mass_kg_d" in detail and fragment in detail
    assert len(store) == 0


@pytest.mark.parametrize("value", [0.0, -5.0])
def test_invalid_override_mass_raises_simulation_input_error(value):
    with pytest.raises(SimulationInputError, match=r"total_mass_kg_d must be > 0.*from override"):
        resolve_params(_req(waste_mass_kg_day=1000.0, overrides={"total_mass_kg_d": value}))


def test_max_mass_matches_request_schema_bound():
    from annotated_types import Le

    bounds = [m.le for m in SimRequest.model_fields["waste_mass_kg_day"].metadata if isinstance(m, Le)]
    assert bounds == [orchestrator.MAX_MASS_KG_D] == [1_000_000.0]


@pytest.mark.parametrize("value", [1_000_000.0000001, 1_000_001.0, 1e9])
@pytest.mark.parametrize("with_request_mass", [False, True], ids=["override-only", "override-beats-request"])
def test_override_mass_above_max_returns_422_and_saves_nothing(client, store, value, with_request_mass):
    body = {"overrides": {"total_mass_kg_d": value}}
    if with_request_mass:
        body["waste_mass_kg_day"] = 1000
    resp = client.post("/simulations", json=body)
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert isinstance(detail, str)
    assert "total_mass_kg_d must be <= 1e+06" in detail and "from override" in detail
    assert len(store) == 0


def test_override_mass_exactly_max_is_accepted(client, store):
    resp = client.post(
        "/simulations",
        json={"waste_mass_kg_day": 1000, "overrides": {"total_mass_kg_d": 1_000_000}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["params"]["total_mass_kg_d"] == 1_000_000.0
    assert body["notes"]["param_sources"]["total_mass_kg_d"] == "override"
    assert len(store) == 1


@pytest.mark.parametrize("value", [1e-6, 1.0, 2500.0])
def test_valid_positive_override_mass_still_runs(client, store, value):
    resp = client.post(
        "/simulations",
        json={"waste_mass_kg_day": 1000, "overrides": {"total_mass_kg_d": value}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["params"]["total_mass_kg_d"] == value
    assert body["notes"]["param_sources"]["total_mass_kg_d"] == "override"
    assert len(store) == 1


# ---------------------------------------------------------------------------
# 3. Location stream data and precedence
# ---------------------------------------------------------------------------

def test_location_stream_supplies_mass_and_is_labelled_placeholder(client, store):
    resp = client.post("/simulations", json={"location_id": "farm_1"})
    assert resp.status_code == 200
    body = resp.json()

    assert body["params"]["total_mass_kg_d"] == STREAM_MASS
    assert body["params"]["organic_fraction"] == STREAM_ORGANIC
    notes = body["notes"]
    assert notes["param_sources"]["total_mass_kg_d"] == "location_stream"
    assert notes["location"]["location_id"] == "farm_1"
    # Mass by fixed list; ts_fraction because P3 tags organic_moisture_fraction
    # source_id="placeholder_general" (see test_ts_fraction_mapping.py).
    assert notes["location"]["placeholder_fields"] == ["total_mass_kg_d", "ts_fraction"]
    assert any("placeholder" in c for c in notes["caveats"])
    # P3 provenance is preserved verbatim
    meta = notes["location"]["stream"]["total_mass_kg_d"]["meta"]
    assert meta["kind"] == "estimated" and meta["source_id"] == "default_v1"
    assert "sinks" in notes["location"]["context"]


def test_stream_ts_fraction_comes_from_organic_moisture_not_whole_stream_moisture():
    # Mapping details are covered in test_ts_fraction_mapping.py.
    params, sources, _ = resolve_params(_req(location_id="farm_1"))
    organic_moisture = STREAM["organic_moisture_fraction"]["value"]
    assert params.ts_fraction == 1.0 - organic_moisture
    assert params.ts_fraction != 1.0 - STREAM["moisture_fraction"]["value"]
    assert sources["ts_fraction"] == "location_stream"


def test_explicit_request_fields_override_stream(store):
    resp = run_simulation(
        _req(location_id="farm_1", waste_mass_kg_day=250.0, organic_fraction=0.3),
        store=store,
    )
    assert resp.params["total_mass_kg_d"] == 250.0
    assert resp.params["organic_fraction"] == 0.3
    assert resp.notes["param_sources"]["total_mass_kg_d"] == "request"
    assert resp.notes["param_sources"]["organic_fraction"] == "request"
    # Mass is no longer the placeholder; the stream-derived ts_fraction still is.
    assert not any(c.startswith("total_mass_kg_d") for c in resp.notes["caveats"])
    assert [c.split()[0] for c in resp.notes["caveats"]] == ["ts_fraction"]


def test_overrides_beat_top_level_fields_and_stream():
    params, sources, _ = resolve_params(_req(
        location_id="farm_1",
        waste_mass_kg_day=1000.0,
        organic_fraction=0.45,
        overrides={"total_mass_kg_d": 2000.0, "organic_fraction": 0.6},
    ))
    assert params.total_mass_kg_d == 2000.0
    assert params.organic_fraction == 0.6
    assert sources["total_mass_kg_d"] == sources["organic_fraction"] == "override"


def test_no_location_means_no_data_calls():
    with patch.object(orchestrator, "get_stream") as gs, patch.object(
        orchestrator, "get_location_context"
    ) as glc:
        run_simulation(_req(**GOLDEN), store=RunStore())
    gs.assert_not_called()
    glc.assert_not_called()


def test_params_defaults_are_not_changed():
    run_simulation(_req(waste_mass_kg_day=10.0, overrides={"hrt_days": 12.0}), store=RunStore())
    assert Params().total_mass_kg_d == 1000.0
    assert Params().hrt_days == 30.0


# ---------------------------------------------------------------------------
# 4–5. Invalid inputs and unsupported features → 422, nothing saved
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "body, fragment",
    [
        ({"waste_mass_kg_day": 1000, "overrides": {"organic_fraction": 1.5}}, "invalid simulation parameters"),
        ({"waste_mass_kg_day": 1000, "overrides": {"composition": 0.5}}, "invalid simulation parameters"),
        ({"waste_mass_kg_day": 1000, "overrides": {"total_mass_kg_d": -1.0}}, "total_mass_kg_d must be > 0"),
        ({"waste_mass_kg_day": 1000, "overrides": {"target_ts": 0.0}}, "simulation rejected the inputs"),
        ({"waste_mass_kg_day": 1000, "process": "pyrolysis"}, "not supported"),
        ({"waste_mass_kg_day": 1000, "use_ml_yield": True}, "use_ml_yield=true is not supported"),
    ],
    ids=["fraction>1", "composition-scalar", "negative-mass", "engine-ValueError", "process", "ml-yield"],
)
def test_unsimulatable_inputs_return_422_and_save_nothing(client, store, body, fragment):
    resp = client.post("/simulations", json=body)
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert isinstance(detail, str) and fragment in detail
    assert len(store) == 0


def test_non_finite_override_returns_422(client, store):
    resp = client.post(
        "/simulations",
        content=b'{"waste_mass_kg_day": 1000, "overrides": {"hrt_days": NaN}}',
        headers={"content-type": "application/json"},
    )
    assert resp.status_code == 422
    assert "finite" in resp.json()["detail"]
    assert len(store) == 0


@pytest.mark.parametrize(
    "body",
    [
        {"waste_mass_kg_day": 0},
        {"waste_mass_kg_day": 1000, "organic_fraction": 2.0},
        {"waste_mass_kg_day": 1000, "overrides": {"not_a_param": 1.0}},
        {"waste_mass_kg_day": 1000, "unknown_field": 1},
    ],
    ids=["mass-zero", "fraction-schema", "unknown-override", "unknown-field"],
)
def test_schema_validation_errors_return_422_and_save_nothing(client, store, body):
    resp = client.post("/simulations", json=body)
    assert resp.status_code == 422
    assert isinstance(resp.json()["detail"], list)
    assert len(store) == 0


def test_ml_rejection_never_reaches_the_ml_layer(store):
    with patch("app.ml.yield_model.predict.estimate_illustrative_l1") as l1, patch(
        "app.ml.yield_model.predict.estimate"
    ) as est:
        with pytest.raises(SimulationInputError):
            run_simulation(_req(waste_mass_kg_day=1000, use_ml_yield=True), store=store)
    l1.assert_not_called()
    est.assert_not_called()


# ---------------------------------------------------------------------------
# 6–7. Retrieval, run reader, 404
# ---------------------------------------------------------------------------

def test_run_is_retrievable_by_generated_id(client):
    body = client.post("/simulations", json=GOLDEN).json()
    got = client.get(f"/runs/{body['id']}")
    assert got.status_code == 200
    assert got.json() == body
    assert [r["id"] for r in client.get("/runs").json()] == [body["id"]]


def test_run_reader_returns_p1_dict(store):
    resp = run_simulation(_req(**GOLDEN), store=store)
    run = RunReader(store).get(resp.id)
    assert isinstance(run, dict)
    for key in ("id", "inputs", "params", "results", "notes", "model_version", "audit_hash"):
        assert key in run
    assert run["id"] == resp.id
    assert set(run["params"]) == {f.name for f in dataclasses.fields(Params)}
    assert run["results"]["e_net_kwh_d"] == pytest.approx(76.7406, abs=1e-4)


def test_unknown_run_reader_none_and_http_404(client, store):
    assert RunReader(store).get("does-not-exist") is None
    assert RunReader(RunStore()).get("") is None
    resp = client.get("/runs/does-not-exist")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "Run 'does-not-exist' not found"}


P1_RUN_KEYS = {"id", "inputs", "params", "results", "notes", "model_version", "audit_hash"}


@pytest.fixture
def process_store(monkeypatch) -> RunStore:
    from app.platform import runs

    shared = RunStore()
    monkeypatch.setattr(runs, "_store", shared)
    return shared


def test_get_run_unknown_id_returns_none(process_store):
    from app.platform.runs import get_run

    assert get_run("does-not-exist") is None
    run_simulation(_req(**GOLDEN))
    assert get_run("does-not-exist") is None


def test_get_run_returns_p1_dict_for_existing_run(process_store):
    from app.platform.runs import get_run

    resp = run_simulation(_req(**GOLDEN))
    run = get_run(resp.id)

    assert type(run) is dict
    assert P1_RUN_KEYS <= set(run)
    assert run == resp.model_dump()
    assert run["id"] == resp.id
    assert run["audit_hash"] == resp.audit_hash
    assert run["model_version"] == ENGINE_MODEL_VERSION
    assert set(run["params"]) == {f.name for f in dataclasses.fields(Params)}
    assert run["results"]["e_net_kwh_d"] == pytest.approx(76.7406, abs=1e-4)
    for key in ("inputs", "params", "results", "notes"):
        assert type(run[key]) is dict


def test_get_run_dict_is_isolated_from_store(process_store):
    from app.platform.runs import get_run

    resp = run_simulation(_req(**GOLDEN))
    run = get_run(resp.id)
    run["params"]["total_mass_kg_d"] = -1.0
    run["results"]["warnings"].append("tampered")
    run["notes"]["caveats"].append("tampered")
    run["id"] = "tampered"

    fresh = get_run(resp.id)
    assert fresh is not run
    assert fresh == resp.model_dump()
    assert process_store.get(resp.id) == resp


def test_default_run_reader_uses_process_store(monkeypatch):
    from app.platform import runs

    shared = RunStore()
    monkeypatch.setattr(runs, "_store", shared)
    resp = run_simulation(_req(**GOLDEN))  # no store → process store
    assert runs.get_run_reader().get(resp.id)["id"] == resp.id


# ---------------------------------------------------------------------------
# 8–9. Audit hash and deduplication
# ---------------------------------------------------------------------------

def test_audit_hash_is_recomputable_from_stored_run(store):
    resp = run_simulation(_req(**GOLDEN), store=store)
    recomputed = compute_audit_hash(
        resp.inputs, resp.params, resp.model_version, resp.results.model_dump(mode="json")
    )
    assert recomputed == resp.audit_hash
    assert run_id_from_hash(recomputed) == resp.id


def test_identical_requests_reuse_the_same_run(client, store):
    a = client.post("/simulations", json=GOLDEN).json()
    b = client.post("/simulations", json=dict(reversed(list(GOLDEN.items())))).json()
    assert a["id"] == b["id"] and a["audit_hash"] == b["audit_hash"]
    assert len(store) == 1


def test_different_inputs_give_different_runs(store):
    a = run_simulation(_req(**GOLDEN), store=store)
    b = run_simulation(_req(**{**GOLDEN, "waste_mass_kg_day": 1001}), store=store)
    assert a.id != b.id and a.audit_hash != b.audit_hash
    assert len(store) == 2


def test_changed_results_change_audit_hash(store):
    real = simulate
    def shifted(p):
        out = real(p)
        out["e_net_kwh_d"] += 1.0
        return out

    a = run_simulation(_req(**GOLDEN), store=store)
    with patch.object(orchestrator, "simulate", side_effect=shifted):
        b = run_simulation(_req(**GOLDEN), store=store)
    assert a.inputs == b.inputs and a.params == b.params
    assert a.audit_hash != b.audit_hash and a.id != b.id


def test_run_id_collision_is_not_silently_overwritten(store):
    first = run_simulation(_req(**GOLDEN), store=store)
    with patch.object(orchestrator, "run_id_from_hash", return_value=first.id):
        with pytest.raises(orchestrator.RunIdCollisionError):
            run_simulation(_req(**{**GOLDEN, "waste_mass_kg_day": 2000}), store=store)
    assert store.get(first.id).audit_hash == first.audit_hash


def _record_save_if_absent(store: RunStore) -> list[bool]:
    """Wrap store.save_if_absent on the instance and record each 'created' flag."""
    created: list[bool] = []
    lock = threading.Lock()
    original = store.save_if_absent

    def spy(run):
        stored, was_created = original(run)
        with lock:
            created.append(was_created)
        return stored, was_created

    store.save_if_absent = spy  # instance attribute; each test gets a fresh store
    return created


def test_identical_repeat_returns_existing_run(store):
    first = run_simulation(_req(**GOLDEN), store=store)
    again = run_simulation(_req(**GOLDEN), store=store)
    assert again == first
    assert len(store) == 1


def test_identical_repeat_in_race_window_returns_existing_via_atomic_save(store):
    """Simulate the fast-path get() missing (another request saved in between):
    save_if_absent must return the stored run instead of inserting again."""
    first = run_simulation(_req(**GOLDEN), store=store)
    created = _record_save_if_absent(store)
    with patch.object(store, "get", return_value=None):
        again = run_simulation(_req(**GOLDEN), store=store)
    assert created == [False]
    assert again == first
    assert len(store) == 1


def test_collision_in_race_window_raises_and_keeps_original(store):
    """Different audit hash, same run id, fast path bypassed: the atomic save
    must raise RunIdCollisionError and leave the original untouched."""
    first = run_simulation(_req(**GOLDEN), store=store)
    with patch.object(store, "get", return_value=None), patch.object(
        orchestrator, "run_id_from_hash", return_value=first.id
    ):
        with pytest.raises(orchestrator.RunIdCollisionError):
            run_simulation(_req(**{**GOLDEN, "waste_mass_kg_day": 2000}), store=store)
    assert store.get(first.id) == first
    assert len(store) == 1


def test_orchestrator_collision_error_is_the_store_error():
    from app.platform.runs import RunIdCollisionError

    assert orchestrator.RunIdCollisionError is RunIdCollisionError


def _concurrent(n: int, fn):
    barrier = threading.Barrier(n)
    results: list = [None] * n
    errors: list = []

    def worker(i):
        barrier.wait()
        try:
            results[i] = fn()
        except Exception as exc:  # noqa: BLE001 - surfaced by the assertion below
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    return results


def test_concurrent_identical_requests_store_exactly_one_run(store):
    results = _concurrent(16, lambda: run_simulation(_req(**GOLDEN), store=store))
    assert len({r.id for r in results}) == 1
    assert all(r == results[0] for r in results)
    assert len(store) == 1
    assert store.get(results[0].id) == results[0]


def test_concurrent_identical_requests_all_reaching_atomic_save(store):
    """Force every request past the fast path so all of them race on
    save_if_absent: exactly one creates, the rest get the stored run."""
    created = _record_save_if_absent(store)
    with patch.object(store, "get", return_value=None):
        results = _concurrent(16, lambda: run_simulation(_req(**GOLDEN), store=store))
    assert sorted(created) == [False] * 15 + [True]
    assert all(r == results[0] for r in results)
    assert len(store) == 1


# ---------------------------------------------------------------------------
# 10. No mutable references leak from the store
# ---------------------------------------------------------------------------

def test_mutating_returned_response_does_not_change_store(store):
    resp = run_simulation(_req(**GOLDEN), store=store)
    resp.status = "tampered"
    resp.params["total_mass_kg_d"] = -1.0
    resp.notes["caveats"].append("tampered")
    resp.results.warnings.append("tampered")

    again = run_simulation(_req(**GOLDEN), store=store)  # dedup path returns stored run
    for run in (again, store.get(resp.id)):
        assert run.status == "illustrative_estimate"
        assert run.params["total_mass_kg_d"] == 1000.0
        assert run.notes["caveats"] == []
        assert run.results.warnings == []


def test_mutating_run_reader_dict_does_not_change_store(store):
    resp = run_simulation(_req(**GOLDEN), store=store)
    reader = RunReader(store)
    run = reader.get(resp.id)
    run["params"]["total_mass_kg_d"] = -1.0
    run["results"]["warnings"].append("tampered")
    run["notes"]["orchestrator"]["model_version"] = "tampered"

    fresh = reader.get(resp.id)
    assert fresh["params"]["total_mass_kg_d"] == 1000.0
    assert fresh["results"]["warnings"] == []
    assert fresh["notes"]["orchestrator"]["model_version"] == ENGINE_MODEL_VERSION


# ---------------------------------------------------------------------------
# 11. Provenance in audit hash (fix: same numbers, different provenance → new run)
# ---------------------------------------------------------------------------

def _measured_stream() -> dict:
    """A stream identical to get_stream("any") except organic_moisture_fraction
    is tagged kind="measured" (not a placeholder), so ts_fraction provenance
    differs from the default placeholder stream."""
    from app.data.service import get_stream
    stream = {k: (dict(v) if isinstance(v, dict) else v) for k, v in get_stream("any").items()}
    entry = dict(stream["organic_moisture_fraction"])
    entry["meta"] = dict(entry["meta"])
    entry["meta"]["kind"] = "measured"
    entry["meta"]["source_id"] = "survey_2024"
    stream["organic_moisture_fraction"] = entry
    return stream


def test_placeholder_vs_measured_provenance_give_different_hashes(store):
    """Identical numbers from a placeholder stream vs a measured stream must
    produce different audit hashes and be stored as separate runs."""
    # Request with location_id so provenance comes from the stream.
    req = _req(location_id="farm_1", waste_mass_kg_day=1000.0,
               organic_fraction=0.45, suitable_fraction=0.80)

    placeholder_resp = run_simulation(req, store=store)

    with patch.object(orchestrator, "get_stream", return_value=_measured_stream()):
        measured_resp = run_simulation(req, store=store)

    # Identical numbers, different provenance → different hash and run id.
    assert placeholder_resp.audit_hash != measured_resp.audit_hash
    assert placeholder_resp.id != measured_resp.id
    assert len(store) == 2

    # Provenance embedded in inputs blob must differ.
    prov_placeholder = placeholder_resp.inputs["provenance"]["ts_fraction"]
    prov_measured = measured_resp.inputs["provenance"]["ts_fraction"]
    assert prov_placeholder["placeholder"] is True
    assert prov_measured["placeholder"] is False
    assert prov_measured["source_id"] == "survey_2024"


def test_identical_provenance_reuses_stored_run(store):
    """Two requests that are byte-for-byte identical (same numbers, same stream
    provenance) must yield the same hash and reuse the same run."""
    req = _req(location_id="farm_1", waste_mass_kg_day=1000.0,
               organic_fraction=0.45, suitable_fraction=0.80)

    first = run_simulation(req, store=store)
    second = run_simulation(req, store=store)

    assert first.audit_hash == second.audit_hash
    assert first.id == second.id
    assert len(store) == 1


def test_provenance_in_hash_golden_numeric_regression(store):
    """No location_id, waste_mass_kg_day=1000, organic_fraction=0.45,
    suitable_fraction=0.80 → e_net_kwh_d ≈ 76.7406, biogas_nm3_d ≈ 47.0448.
    Provenance for a pure-request run (no stream) carries request kind only."""
    resp = run_simulation(_req(**GOLDEN), store=store)

    assert resp.results.e_net_kwh_d == pytest.approx(76.7406, abs=1e-3)
    assert resp.results.biogas_nm3_d == pytest.approx(47.0448, abs=1e-3)

    # Provenance blob must be present in inputs and included in the hash.
    assert "provenance" in resp.inputs
    prov = resp.inputs["provenance"]
    assert prov["total_mass_kg_d"]["kind"] == "request"
    assert prov["total_mass_kg_d"]["placeholder"] is False

    # Hash must be reproducible from the stored inputs (which include provenance).
    from app.platform.audit import compute_audit_hash, run_id_from_hash
    recomputed = compute_audit_hash(
        resp.inputs, resp.params, resp.model_version, resp.results.model_dump(mode="json")
    )
    assert recomputed == resp.audit_hash
    assert run_id_from_hash(recomputed) == resp.id
