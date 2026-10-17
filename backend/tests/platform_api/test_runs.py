"""Unit tests for the in-memory run store (app/platform/runs.py)."""

from __future__ import annotations

import threading

import pytest

from app import config
from app.platform import runs
from app.platform.runs import RunIdCollisionError, RunStore, get_run_store


def test_save_and_get(make_run):
    store = RunStore()
    run = make_run("a")
    assert store.save(run) == run
    assert store.get("a") == run
    assert len(store) == 1


def test_mutating_original_after_save_does_not_change_store(make_run):
    store = RunStore()
    run = make_run("a")
    store.save(run)
    run.status = "mutated"
    run.inputs["total_mass_kg_d"] = -1.0
    run.defaults_used_unvalidated.append("x")

    stored = store.get("a")
    assert stored.status == "illustrative_estimate"
    assert stored.inputs == {"total_mass_kg_d": 1000.0}
    assert stored.defaults_used_unvalidated == ["hrt_days"]


def test_mutating_save_return_value_does_not_change_store(make_run):
    store = RunStore()
    returned = store.save(make_run("a"))
    returned.status = "mutated"
    assert store.get("a").status == "illustrative_estimate"


def test_mutating_get_result_does_not_change_store(make_run):
    store = RunStore()
    store.save(make_run("a"))
    got = store.get("a")
    got.status = "mutated"
    got.params["hrt_days"] = 0.0
    got.results.warnings.append("injected")

    fresh = store.get("a")
    assert fresh is not got
    assert fresh.status == "illustrative_estimate"
    assert fresh.params == {"hrt_days": 30.0}
    assert "injected" not in fresh.results.warnings


def test_mutating_list_results_does_not_change_store(make_run):
    store = RunStore()
    store.save(make_run("a"))
    listed = store.list()
    listed[0].status = "mutated"
    listed[0].inputs.clear()
    listed.clear()

    fresh = store.list()
    assert [r.id for r in fresh] == ["a"]
    assert fresh[0].status == "illustrative_estimate"
    assert fresh[0].inputs == {"total_mass_kg_d": 1000.0}


def test_get_unknown_returns_none():
    assert RunStore().get("missing") is None


def test_list_is_newest_first_and_respects_limit(make_run):
    store = RunStore()
    for rid in ("a", "b", "c"):
        store.save(make_run(rid))
    assert [r.id for r in store.list()] == ["c", "b", "a"]
    assert [r.id for r in store.list(limit=2)] == ["c", "b"]


def test_saving_same_id_replaces_and_moves_to_newest(make_run):
    store = RunStore()
    store.save(make_run("a"))
    store.save(make_run("b"))
    replacement = make_run("a", status="validated")
    store.save(replacement)
    assert len(store) == 2
    assert store.get("a") == replacement
    assert [r.id for r in store.list()] == ["a", "b"]


def test_oldest_run_is_evicted_at_capacity(make_run):
    store = RunStore(max_runs=2)
    for rid in ("a", "b", "c"):
        store.save(make_run(rid))
    assert store.get("a") is None
    assert [r.id for r in store.list()] == ["c", "b"]


def test_delete_and_clear(make_run):
    store = RunStore()
    store.save(make_run("a"))
    store.save(make_run("b"))
    assert store.delete("a") is True
    assert store.delete("a") is False
    store.clear()
    assert len(store) == 0


@pytest.mark.parametrize("bad", [0, -1])
def test_invalid_max_runs_rejected(bad):
    with pytest.raises(ValueError):
        RunStore(max_runs=bad)


def test_concurrent_saves_respect_capacity(make_run):
    store = RunStore(max_runs=50)
    template = make_run()

    def worker(offset: int) -> None:
        for i in range(100):
            store.save(template.model_copy(update={"id": f"{offset}-{i}"}))

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(store) == 50


# ---------------------------------------------------------------------------
# save_if_absent — atomic deduplication
# ---------------------------------------------------------------------------

def _with_hash(run, audit_hash):
    return run.model_copy(update={"audit_hash": audit_hash})


def test_save_if_absent_stores_new_run(make_run):
    store = RunStore()
    run = make_run("a")
    stored, created = store.save_if_absent(run)
    assert created is True
    assert stored == run and stored is not run
    assert store.get("a") == run


def test_save_if_absent_returns_existing_identical_run(make_run):
    store = RunStore()
    first = make_run("a")
    store.save_if_absent(first)
    store.save(make_run("b"))

    repeat = make_run("a", status="different-but-same-hash")
    stored, created = store.save_if_absent(repeat)
    assert created is False
    assert stored == first  # existing run returned, not the new object
    assert store.get("a") == first
    assert [r.id for r in store.list()] == ["b", "a"]  # not moved to newest
    assert len(store) == 2


def test_save_if_absent_collision_raises_and_keeps_existing(make_run):
    store = RunStore()
    original = _with_hash(make_run("a"), "hash-1")
    store.save_if_absent(original)

    with pytest.raises(RunIdCollisionError, match="'a'"):
        store.save_if_absent(_with_hash(make_run("a", status="other"), "hash-2"))
    assert store.get("a") == original
    assert len(store) == 1


def test_save_if_absent_isolates_input_and_output(make_run):
    store = RunStore()
    run = make_run("a")
    stored, _ = store.save_if_absent(run)
    run.status = "mutated-input"
    stored.status = "mutated-output"
    assert store.get("a").status == "illustrative_estimate"


def test_save_if_absent_respects_capacity(make_run):
    store = RunStore(max_runs=2)
    for rid in ("a", "b", "c"):
        store.save_if_absent(make_run(rid))
    assert [r.id for r in store.list()] == ["c", "b"]


def _race(n, target):
    barrier = threading.Barrier(n)
    outcomes = [None] * n

    def worker(i):
        barrier.wait()
        try:
            outcomes[i] = ("ok", target(i))
        except Exception as exc:  # noqa: BLE001 - recorded for assertions
            outcomes[i] = ("error", exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return outcomes


def test_concurrent_identical_save_if_absent_creates_exactly_once(make_run):
    store = RunStore()
    run = make_run("a")
    outcomes = _race(16, lambda i: store.save_if_absent(run))

    assert all(kind == "ok" for kind, _ in outcomes)
    created = [value[1] for _, value in outcomes]
    assert created.count(True) == 1
    assert all(value[0] == run for _, value in outcomes)
    assert len(store) == 1


def test_concurrent_colliding_save_if_absent_never_overwrites(make_run):
    store = RunStore()
    candidates = [_with_hash(make_run("a"), f"hash-{i}") for i in range(16)]
    outcomes = _race(16, lambda i: store.save_if_absent(candidates[i]))

    winners = [value[0] for kind, value in outcomes if kind == "ok"]
    errors = [value for kind, value in outcomes if kind == "error"]
    assert len(winners) == 1
    assert len(errors) == 15
    assert all(isinstance(e, RunIdCollisionError) for e in errors)
    assert store.get("a") == winners[0]
    assert len(store) == 1


def test_process_store_is_singleton_and_uses_settings(monkeypatch, make_run):
    monkeypatch.setattr(runs, "_store", None)
    monkeypatch.setenv("WP_RUN_STORE_MAX_RUNS", "3")
    config.get_settings.cache_clear()
    try:
        store = get_run_store()
        assert store is get_run_store()
        assert store.max_runs == 3

        store.save(make_run("x"))
        found = runs.get_run("x")
        assert isinstance(found, dict) and found["id"] == "x"
        assert runs.get_run("missing") is None
    finally:
        config.get_settings.cache_clear()
