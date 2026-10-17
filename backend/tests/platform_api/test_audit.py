"""Tests for the audit hash / run id helpers (app/platform/audit.py)."""

from __future__ import annotations

import copy
import hashlib

import pytest

from app.platform.audit import (
    RUN_ID_LENGTH,
    canonical_json,
    compute_audit_hash,
    run_id_from_hash,
)

INPUTS = {"waste_mass_kg_day": 1000.0, "overrides": {}, "location_id": None}
PARAMS = {"total_mass_kg_d": 1000.0, "composition": (0.6, 0.2, 0.2)}
RESULTS = {"e_net_kwh_d": 76.74057020848, "warnings": [], "status": "illustrative_estimate"}
VERSION = "engine-0.2"


def _hash(**changes):
    parts = {"inputs": INPUTS, "params": PARAMS, "model_version": VERSION, "results": RESULTS}
    parts.update(changes)
    return compute_audit_hash(parts["inputs"], parts["params"], parts["model_version"], parts["results"])


def test_hash_matches_documented_recipe():
    payload = {"inputs": INPUTS, "params": PARAMS, "model_version": VERSION, "results": RESULTS}
    expected = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
    assert _hash() == expected
    assert canonical_json({"b": 1, "a": [1, 2]}) == '{"a":[1,2],"b":1}'


def test_identical_payloads_hash_identically():
    assert _hash() == _hash(
        inputs=copy.deepcopy(INPUTS),
        params=copy.deepcopy(PARAMS),
        results=copy.deepcopy(RESULTS),
    )


def test_key_order_does_not_matter():
    reordered = dict(reversed(list(RESULTS.items())))
    assert _hash(results=reordered) == _hash()


def test_tuple_and_list_params_hash_the_same():
    as_list = {**PARAMS, "composition": [0.6, 0.2, 0.2]}
    assert _hash(params=as_list) == _hash()


@pytest.mark.parametrize(
    "changes",
    [
        {"results": {**RESULTS, "e_net_kwh_d": 76.74057020849}},
        {"results": {**RESULTS, "warnings": ["x"]}},
        {"params": {**PARAMS, "total_mass_kg_d": 1000.1}},
        {"inputs": {**INPUTS, "waste_mass_kg_day": 999.0}},
        {"model_version": "engine-0.3"},
    ],
    ids=["result-value", "result-warnings", "params", "inputs", "model-version"],
)
def test_any_change_changes_hash(changes):
    assert _hash(**changes) != _hash()


def test_hash_is_sha256_hex():
    h = _hash()
    assert len(h) == 64
    int(h, 16)


def test_run_id_is_hash_prefix():
    h = _hash()
    assert RUN_ID_LENGTH == 12
    assert run_id_from_hash(h) == h[:12]
