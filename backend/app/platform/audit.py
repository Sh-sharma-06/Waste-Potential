"""Audit hash and run-id helpers for simulation runs.

Contract (confirmed by P1): the audit hash is SHA-256 over canonical JSON of
exactly four parts — inputs, final Params, model_version and results. No
timestamps or random values are included, so identical runs hash identically.
The run id is the first 12 hex characters of the hash.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

RUN_ID_LENGTH = 12


def canonical_json(payload: Any) -> str:
    """Deterministic JSON encoding used for hashing."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def compute_audit_hash(
    inputs: Mapping[str, Any],
    params: Mapping[str, Any],
    model_version: str,
    results: Mapping[str, Any],
) -> str:
    """Return the hex SHA-256 of the canonical audit payload."""
    payload = {
        "inputs": inputs,
        "params": params,
        "model_version": model_version,
        "results": results,
    }
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def run_id_from_hash(audit_hash: str) -> str:
    """Derive the public run id from an audit hash."""
    return audit_hash[:RUN_ID_LENGTH]
