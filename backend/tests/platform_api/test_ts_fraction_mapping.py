"""ts_fraction = 1 − organic_moisture_fraction, derived from the P3 location stream.

Precedence: Params() defaults < location stream < request fields < overrides.
P3's stream is patched with distinctive values so a passing test cannot be
explained by the Params() default (ts_fraction = 0.27).
"""

from __future__ import annotations

import copy
import math
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core_engine import Params
from app.data.service import get_stream
from app.errors import register_error_handlers
from app.platform import orchestrator
from app.platform.orchestrator import SimulationInputError, resolve_params, run_simulation
from app.platform.router import router
from app.platform.runs import RunStore, get_run_store
from app.schemas.simulation import SimRequest

BASE_STREAM = get_stream("any")
DEFAULT_TS = Params().ts_fraction


def _stream(**values) -> dict:
    """A copy of P3's default stream with some field values replaced.

    A value of None removes the field.
    """
    stream = copy.deepcopy(BASE_STREAM)
    for field, value in values.items():
        if value is None:
            stream.pop(field, None)
        else:
            stream[field]["value"] = value
    return stream


def _resolve(stream: dict, **fields):
    with patch.object(orchestrator, "get_stream", return_value=stream):
        return resolve_params(SimRequest(location_id="farm_1", **fields))


@pytest.fixture
def store() -> RunStore:
    return RunStore()


@pytest.fixture
def client(store) -> TestClient:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(router)
    app.dependency_overrides[get_run_store] = lambda: store
    return TestClient(app)


def _post(client: TestClient, stream: dict, body: dict):
    with patch.object(orchestrator, "get_stream", return_value=stream):
        return client.post("/simulations", json={"location_id": "farm_1", **body})


# ---------------------------------------------------------------------------
# Mapping and source metadata
# ---------------------------------------------------------------------------

def test_stream_organic_moisture_maps_to_ts_fraction():
    params, sources, notes = _resolve(_stream(organic_moisture_fraction=0.80))
    assert params.ts_fraction == pytest.approx(0.20)
    assert params.ts_fraction != DEFAULT_TS
    assert sources["ts_fraction"] == "location_stream"
    assert "ts_fraction" in notes["stream_fields_applied"]


def test_default_p3_stream_is_recorded_as_the_source():
    # P3's default (0.73) gives exactly the Params() default; the source must
    # still say the value came from the stream.
    params, sources, _ = _resolve(_stream())
    assert params.ts_fraction == 1.0 - BASE_STREAM["organic_moisture_fraction"]["value"]
    assert sources["ts_fraction"] == "location_stream"


def test_mapping_reaches_the_stored_run(client, store):
    resp = _post(client, _stream(organic_moisture_fraction=0.80), {})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["params"]["ts_fraction"] == pytest.approx(0.20)
    assert body["notes"]["param_sources"]["ts_fraction"] == "location_stream"
    assert store.get(body["id"]).params["ts_fraction"] == pytest.approx(0.20)


def test_mapped_value_changes_the_result():
    common = dict(waste_mass_kg_day=1000.0)
    with patch.object(orchestrator, "get_stream", return_value=_stream(organic_moisture_fraction=0.80)):
        low = run_simulation(SimRequest(location_id="farm_1", **common), store=RunStore())
    with patch.object(orchestrator, "get_stream", return_value=_stream(organic_moisture_fraction=0.65)):
        high = run_simulation(SimRequest(location_id="farm_1", **common), store=RunStore())
    assert low.results.vs_kg_d < high.results.vs_kg_d
    assert low.audit_hash != high.audit_hash


# ---------------------------------------------------------------------------
# Precedence
# ---------------------------------------------------------------------------

def test_override_beats_stream_derived_ts_fraction():
    params, sources, _ = _resolve(
        _stream(organic_moisture_fraction=0.80), overrides={"ts_fraction": 0.33}
    )
    assert params.ts_fraction == 0.33
    assert sources["ts_fraction"] == "override"


def test_request_fields_still_beat_stream_with_ts_mapping_present():
    params, sources, _ = _resolve(
        _stream(organic_moisture_fraction=0.80, organic_fraction=0.55),
        waste_mass_kg_day=250.0,
        organic_fraction=0.30,
    )
    assert params.total_mass_kg_d == 250.0
    assert params.organic_fraction == 0.30
    assert params.ts_fraction == pytest.approx(0.20)
    assert sources == {
        "total_mass_kg_d": "request",
        "organic_fraction": "request",
        "ts_fraction": "location_stream",
    }


def test_no_location_keeps_default_ts_fraction_and_no_source():
    params, sources, _ = resolve_params(SimRequest(waste_mass_kg_day=1000.0))
    assert params.ts_fraction == DEFAULT_TS
    assert "ts_fraction" not in sources


# ---------------------------------------------------------------------------
# Absent field and whole-stream moisture
# ---------------------------------------------------------------------------

def test_absent_organic_moisture_keeps_default_and_no_source():
    params, sources, notes = _resolve(_stream(organic_moisture_fraction=None))
    assert params.ts_fraction == DEFAULT_TS
    assert "ts_fraction" not in sources
    assert "ts_fraction" not in notes["stream_fields_applied"]


def test_whole_stream_moisture_fraction_is_not_mapped():
    # Only whole-stream moisture present: ts_fraction stays at the default.
    params, sources, _ = _resolve(
        _stream(organic_moisture_fraction=None, moisture_fraction=0.40)
    )
    assert params.ts_fraction == DEFAULT_TS
    assert "ts_fraction" not in sources


def test_organic_moisture_is_used_even_when_whole_stream_moisture_differs():
    params, _, _ = _resolve(_stream(organic_moisture_fraction=0.80, moisture_fraction=0.40))
    assert params.ts_fraction == pytest.approx(0.20)  # not 1 - 0.40


# ---------------------------------------------------------------------------
# Validation → 422, nothing stored
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "value, fragment",
    [
        (-0.1, "must be in [0, 1]"),
        (1.5, "must be in [0, 1]"),
        (math.nan, "must be a finite number"),
        (math.inf, "must be a finite number"),
        ("0.7", "must be a number"),
        (True, "must be a number"),
    ],
    ids=["negative", "above-one", "nan", "inf", "string", "bool"],
)
def test_invalid_organic_moisture_returns_422_and_saves_nothing(client, store, value, fragment):
    resp = _post(client, _stream(organic_moisture_fraction=value), {})
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert isinstance(detail, str)
    assert "location stream organic_moisture_fraction" in detail and fragment in detail
    assert len(store) == 0


def test_invalid_organic_moisture_raises_simulation_input_error():
    with pytest.raises(SimulationInputError, match="organic_moisture_fraction"):
        _resolve(_stream(organic_moisture_fraction=2.0))


def test_full_moisture_gives_zero_ts_which_the_engine_rejects(client, store):
    # 1.0 is a valid fraction, but ts_fraction = 0 has no solids to digest.
    resp = _post(client, _stream(organic_moisture_fraction=1.0), {})
    assert resp.status_code == 422
    assert "simulation rejected the inputs" in resp.json()["detail"]
    assert len(store) == 0


def test_zero_moisture_gives_ts_one_and_runs_as_extrapolation(client):
    resp = _post(client, _stream(organic_moisture_fraction=0.0), {})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["params"]["ts_fraction"] == 1.0
    assert body["status"] == "extrapolation"


# ---------------------------------------------------------------------------
# Provenance: P3 marks organic_moisture_fraction as a placeholder
# (kind="estimated", source_id="placeholder_general"). The derived
# ts_fraction must carry that provenance and never read as site data.
# ---------------------------------------------------------------------------

PLACEHOLDER_META = {"kind": "estimated", "resolution": "n/a", "source_id": "placeholder_general"}
MEASURED_META = {"kind": "measured", "resolution": "daily", "source_id": "sensor_v1"}
TS_CAVEAT_PREFIX = "ts_fraction is derived from the P3 location stream's organic_moisture_fraction"


def _with_moisture_meta(meta: dict, value: float = 0.80) -> dict:
    stream = _stream(organic_moisture_fraction=value)
    stream["organic_moisture_fraction"]["meta"] = dict(meta)
    return stream


def _ts_caveats(caveats: list[str]) -> list[str]:
    return [c for c in caveats if c.startswith(TS_CAVEAT_PREFIX)]


def test_real_p3_stream_tags_organic_moisture_as_placeholder():
    # Guards the P3 contract this behaviour depends on.
    assert BASE_STREAM["organic_moisture_fraction"]["meta"] == PLACEHOLDER_META


def test_placeholder_provenance_reaches_the_response(client, store):
    resp = _post(client, _stream(), {})  # P3's real default stream
    assert resp.status_code == 200, resp.text
    body = resp.json()
    location = body["notes"]["location"]

    assert body["status"] == "illustrative_estimate"
    assert body["notes"]["param_sources"]["ts_fraction"] == "location_stream"
    assert "ts_fraction" in location["placeholder_fields"]
    assert location["derived_fields"]["ts_fraction"] == {
        "source_field": "organic_moisture_fraction",
        "formula": "1 - organic_moisture_fraction",
        "meta": PLACEHOLDER_META,
    }
    assert len(_ts_caveats(body["notes"]["caveats"])) == 1
    assert "not measured site data" in _ts_caveats(body["notes"]["caveats"])[0]
    # The stored run carries the same provenance.
    assert store.get(body["id"]).notes["location"]["derived_fields"] == location["derived_fields"]


def test_provenance_follows_p3_meta_rather_than_a_hard_coded_field_list(client):
    # If P3 ever supplies a measured value, it is not labelled a placeholder.
    resp = _post(client, _with_moisture_meta(MEASURED_META), {"waste_mass_kg_day": 500.0})
    body = resp.json()
    location = body["notes"]["location"]
    assert "ts_fraction" not in location["placeholder_fields"]
    assert location["derived_fields"]["ts_fraction"]["meta"] == MEASURED_META
    assert _ts_caveats(body["notes"]["caveats"]) == []


def test_override_removes_the_placeholder_caveat_but_keeps_stream_provenance(client):
    resp = _post(client, _stream(), {"overrides": {"ts_fraction": 0.30}})
    body = resp.json()
    assert body["params"]["ts_fraction"] == 0.30
    assert body["notes"]["param_sources"]["ts_fraction"] == "override"
    assert _ts_caveats(body["notes"]["caveats"]) == []
    # The stream value was still a placeholder; that fact is not hidden.
    assert "ts_fraction" in body["notes"]["location"]["placeholder_fields"]


def test_absent_organic_moisture_has_no_derived_provenance():
    _, _, notes = _resolve(_stream(organic_moisture_fraction=None))
    assert notes["derived_fields"] == {}
    assert "ts_fraction" not in notes["placeholder_fields"]


def test_extrapolation_status_is_kept_when_placeholder_is_used(client):
    # moisture 0 → ts 1.0, outside the model range: the stronger warning wins.
    resp = _post(client, _stream(organic_moisture_fraction=0.0), {})
    body = resp.json()
    assert body["status"] == "extrapolation"
    assert len(_ts_caveats(body["notes"]["caveats"])) == 1


def _engine_reporting(status: str):
    real = orchestrator.simulate
    return patch.object(orchestrator, "simulate", side_effect=lambda p: {**real(p), "status": status})


def test_placeholder_run_is_never_reported_with_a_stronger_status(store):
    # The engine only returns illustrative_estimate/extrapolation today; this
    # pins the guard if a stronger status (e.g. "validated") is ever added.
    with _engine_reporting("validated"), patch.object(
        orchestrator, "get_stream", return_value=_stream()
    ):
        resp = run_simulation(SimRequest(location_id="farm_1"), store=store)
    assert resp.status == "illustrative_estimate"
    assert resp.results.status == "validated"  # engine output itself is not rewritten


def test_status_guard_does_not_apply_without_placeholders_in_use(store):
    with _engine_reporting("validated"):
        no_location = run_simulation(SimRequest(waste_mass_kg_day=1000.0), store=store)
    with _engine_reporting("validated"), patch.object(
        orchestrator, "get_stream", return_value=_stream()
    ):
        all_replaced = run_simulation(
            SimRequest(location_id="farm_1", waste_mass_kg_day=500.0, overrides={"ts_fraction": 0.30}),
            store=store,
        )
    assert no_location.status == "validated"
    assert all_replaced.status == "validated"


def test_provenance_does_not_change_the_audit_hash(store):
    # notes are outside the audit hash (inputs, params, model_version, results).
    with patch.object(orchestrator, "get_stream", return_value=_with_moisture_meta(PLACEHOLDER_META)):
        placeholder = run_simulation(SimRequest(location_id="farm_1"), store=RunStore())
    with patch.object(orchestrator, "get_stream", return_value=_with_moisture_meta(MEASURED_META)):
        measured = run_simulation(SimRequest(location_id="farm_1"), store=RunStore())
    assert placeholder.audit_hash == measured.audit_hash
