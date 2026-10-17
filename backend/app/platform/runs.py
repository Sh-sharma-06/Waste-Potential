"""Minimal in-memory run store.

A run is a stored ``SimResponse`` (app/schemas/simulation.py) keyed by its
``id``. The store is process-local and bounded: once ``max_runs`` is reached
the oldest run is evicted. Nothing is persisted across restarts.

Runs are deep-copied on save and on read, so callers cannot mutate stored
state through the objects they pass in or get back.

``get_run_store()`` returns the process-wide store. core_engine (P1) reads
runs through ``get_run(run_id) -> dict | None`` (equivalently
``get_run_reader().get(run_id)``), importing this module lazily (see
core_engine/tests/test_public_api.py).
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Optional

from app.config import get_settings
from app.schemas.simulation import SimResponse


class RunIdCollisionError(RuntimeError):
    """Two different audit payloads produced the same run id."""


class RunStore:
    """Thread-safe, insertion-ordered, size-bounded store of runs."""

    def __init__(self, max_runs: int = 1000) -> None:
        if max_runs < 1:
            raise ValueError(f"max_runs must be >= 1, got {max_runs}")
        self.max_runs = max_runs
        self._runs: OrderedDict[str, SimResponse] = OrderedDict()
        self._lock = threading.Lock()

    def save(self, run: SimResponse) -> SimResponse:
        """Store a copy of *run* under ``run.id``, replacing any run with the
        same id. Returns a separate copy of what was stored."""
        stored = run.model_copy(deep=True)
        with self._lock:
            self._runs.pop(stored.id, None)
            self._runs[stored.id] = stored
            while len(self._runs) > self.max_runs:
                self._runs.popitem(last=False)
        return stored.model_copy(deep=True)

    def save_if_absent(self, run: SimResponse) -> tuple[SimResponse, bool]:
        """Atomically store a copy of *run* unless its id is already present.

        Returns ``(copy_of_stored_run, created)``. If a run with the same id
        and the same ``audit_hash`` exists, it is returned unchanged (not
        moved to newest) with ``created=False``. If the id exists with a
        different ``audit_hash``, raises RunIdCollisionError and leaves the
        existing run untouched.
        """
        candidate = run.model_copy(deep=True)
        with self._lock:
            existing = self._runs.get(candidate.id)
            if existing is None:
                self._runs[candidate.id] = candidate
                while len(self._runs) > self.max_runs:
                    self._runs.popitem(last=False)
                stored, created = candidate, True
            elif existing.audit_hash != candidate.audit_hash:
                raise RunIdCollisionError(
                    f"run id {candidate.id!r} already used by a different run"
                )
            else:
                stored, created = existing, False
        return stored.model_copy(deep=True), created

    def get(self, run_id: str) -> Optional[SimResponse]:
        """Return a copy of the run, or None if unknown."""
        with self._lock:
            run = self._runs.get(run_id)
        return None if run is None else run.model_copy(deep=True)

    def list(self, limit: Optional[int] = None) -> list[SimResponse]:
        """Return copies of runs newest first, at most *limit* of them."""
        with self._lock:
            runs = list(reversed(self._runs.values()))
        if limit is not None:
            runs = runs[:limit]
        return [r.model_copy(deep=True) for r in runs]

    def delete(self, run_id: str) -> bool:
        with self._lock:
            return self._runs.pop(run_id, None) is not None

    def clear(self) -> None:
        with self._lock:
            self._runs.clear()

    def __len__(self) -> int:
        with self._lock:
            return len(self._runs)


_store: Optional[RunStore] = None
_store_lock = threading.Lock()


def get_run_store() -> RunStore:
    """Return the process-wide RunStore, creating it on first use."""
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = RunStore(max_runs=get_settings().run_store_max_runs)
    return _store


def get_run(run_id: str) -> Optional[dict]:
    """P1 run-reader contract: a fresh plain dict for the run in the
    process-wide store, or None if *run_id* is unknown (see RunReader.get)."""
    return RunReader().get(run_id)


class RunReader:
    """Read-only, dict-based view of stored runs for core_engine (P1).

    ``get`` returns a fresh plain dict (``SimResponse.model_dump()``) with
    id, inputs, params (all final Params fields), results, notes,
    model_version, audit_hash and the remaining SimResponse fields, or None
    for an unknown id. Mutating the dict never affects the store.
    """

    def __init__(self, store: Optional[RunStore] = None) -> None:
        self._store = store

    def get(self, run_id: str) -> Optional[dict]:
        store = self._store if self._store is not None else get_run_store()
        run = store.get(run_id)
        return None if run is None else run.model_dump()


def get_run_reader() -> RunReader:
    """Return a reader over the process-wide store."""
    return RunReader()
