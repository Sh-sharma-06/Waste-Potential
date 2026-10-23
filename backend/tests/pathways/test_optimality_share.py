"""
Tests for the optimality_share feature in app/pathways/mc_compare.py.

Covers:
  - Shares sum to 1 within 1e-9 over feasible pathways.
  - A single feasible pathway gets optimality_share = 1.0.
  - A deterministically rejected pathway gets optimality_share = 0.0.
  - Same seed → identical output; different seed → different output.
  - AD + composting both feasible → each gets a share.
  - Result is JSON serialisable.
  - No-feasible-pathway edge case returns no shares.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from app.pathways.mc_compare import PathwayMCResult, merge_mc_into_results, run_mc_compare
from app.pathways.schemas import PathwayCompareRequest, PathwayResult

AD = "anaerobic_digestion"
COMP = "composting"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _request(**overrides: Any) -> PathwayCompareRequest:
    """Minimal valid request with two pathways that have non-zero cost/yield."""
    base: dict[str, Any] = {
        "farm_id": "farm_test",
        "waste_tpd": 10.0,
        "pathways": [AD, COMP],
        "capex_inr": {AD: 5_000_000.0, COMP: 2_000_000.0},
        "opex_inr_yr": {AD: 300_000.0, COMP: 100_000.0},
        "net_kwh_per_tonne": {AD: 120.0, COMP: 0.0},
        "capacity_tpd": {AD: 20.0, COMP: 15.0},
        "distance_km": 10.0,
        "mc_runs": 200,
        "mc_seed": 42,
    }
    base.update(overrides)
    return PathwayCompareRequest(**base)


def _feasible_result(pathway: str) -> PathwayResult:
    return PathwayResult(pathway=pathway, feasible=True, status="feasible")


def _rejected_result(pathway: str) -> PathwayResult:
    return PathwayResult(pathway=pathway, feasible=False, status="rejected")


# ---------------------------------------------------------------------------
# 1. Shares sum to 1
# ---------------------------------------------------------------------------

def test_optimality_shares_sum_to_one():
    req = _request()
    feasible = {AD, COMP}
    mc = run_mc_compare(req, feasible_pathways=feasible)
    total = sum(r.optimality_share for r in mc)
    assert abs(total - 1.0) < 1e-9, f"shares sum to {total!r}, expected 1.0"


# ---------------------------------------------------------------------------
# 2. Single feasible pathway gets share 1.0
# ---------------------------------------------------------------------------

def test_single_feasible_pathway_gets_share_one():
    req = _request()
    feasible = {AD}   # only AD is eligible
    mc = run_mc_compare(req, feasible_pathways=feasible)
    by_pw = {r.pathway: r for r in mc}
    assert by_pw[AD].optimality_share == pytest.approx(1.0, abs=1e-9)
    assert by_pw[AD].win_count == req.mc_runs
    # COMP is not in eligible set → share stays 0
    assert by_pw[COMP].optimality_share == pytest.approx(0.0)
    assert by_pw[COMP].win_count == 0


# ---------------------------------------------------------------------------
# 3. Rejected pathway never wins
# ---------------------------------------------------------------------------

def test_rejected_pathway_gets_share_zero_after_merge():
    req = _request()
    feasible = {AD}
    mc = run_mc_compare(req, feasible_pathways=feasible)
    results = [_feasible_result(AD), _rejected_result(COMP)]
    merged = merge_mc_into_results(results, mc)
    by_pw = {r.pathway: r for r in merged}
    assert by_pw[COMP].optimality_share == pytest.approx(0.0)
    assert by_pw[COMP].win_count == 0
    # AD must still have share 1.0
    assert by_pw[AD].optimality_share == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# 4. Determinism: same seed → identical; different seed → different
# ---------------------------------------------------------------------------

def test_same_seed_gives_identical_output():
    req_a = _request(mc_seed=42)
    req_b = _request(mc_seed=42)
    mc_a = run_mc_compare(req_a, feasible_pathways={AD, COMP})
    mc_b = run_mc_compare(req_b, feasible_pathways={AD, COMP})
    by_a = {r.pathway: r for r in mc_a}
    by_b = {r.pathway: r for r in mc_b}
    for pw in (AD, COMP):
        assert by_a[pw].win_count == by_b[pw].win_count
        assert by_a[pw].optimality_share == by_b[pw].optimality_share
        assert by_a[pw].prob_positive_npv == by_b[pw].prob_positive_npv


def test_different_seed_gives_different_output():
    req_42 = _request(mc_seed=42)
    req_99 = _request(mc_seed=99)
    mc_42 = run_mc_compare(req_42, feasible_pathways={AD, COMP})
    mc_99 = run_mc_compare(req_99, feasible_pathways={AD, COMP})
    by_42 = {r.pathway: r for r in mc_42}
    by_99 = {r.pathway: r for r in mc_99}
    # The shared e_price samples differ between seeds, so each pathway's mean
    # net value must differ (net_value_samples reflects the shared draw).
    differed = any(
        by_42[pw].annual_net_value_mc.mean != by_99[pw].annual_net_value_mc.mean
        for pw in (AD, COMP)
    )
    assert differed, "Different seeds produced identical mean net values — seeding is broken"


# ---------------------------------------------------------------------------
# 5. Two feasible pathways (AD + composting) both get a positive share
# ---------------------------------------------------------------------------

def test_two_feasible_pathways_both_get_positive_share():
    """With AD having non-zero yield and composting having zero yield but lower
    cost, both should win at least some runs when costs vary enough."""
    # Give composting a very small cost so it sometimes beats AD
    req = _request(
        opex_inr_yr={AD: 500_000.0, COMP: 50_000.0},
        net_kwh_per_tonne={AD: 50.0, COMP: 0.0},
        gate_fee_inr_t={AD: 0.0, COMP: 200.0},   # composting gate revenue
        mc_runs=500,
        mc_seed=7,
    )
    feasible = {AD, COMP}
    mc = run_mc_compare(req, feasible_pathways=feasible)
    by_pw = {r.pathway: r for r in mc}

    # Both shares must be strictly positive
    assert by_pw[AD].optimality_share > 0.0, "AD share is zero"
    assert by_pw[COMP].optimality_share > 0.0, "composting share is zero"

    # Shares still sum to 1
    total = sum(r.optimality_share for r in mc)
    assert abs(total - 1.0) < 1e-9


# ---------------------------------------------------------------------------
# 6. JSON serialisability of merged PathwayResult
# ---------------------------------------------------------------------------

def test_pathway_result_with_optimality_share_is_json_serialisable():
    req = _request(mc_runs=50)
    feasible = {AD, COMP}
    mc = run_mc_compare(req, feasible_pathways=feasible)
    results = [_feasible_result(AD), _feasible_result(COMP)]
    merged = merge_mc_into_results(results, mc)
    for r in merged:
        # model_dump(mode="json") is what FastAPI serialises to
        d = r.model_dump(mode="json")
        json_str = json.dumps(d)  # must not raise
        reloaded = json.loads(json_str)
        assert reloaded["pathway"] == r.pathway
        assert isinstance(reloaded.get("optimality_share"), (float, type(None)))
        assert isinstance(reloaded.get("win_count"), (int, type(None)))


# ---------------------------------------------------------------------------
# 7. No-feasible-pathway edge case: shares are all 0, note is absent
# ---------------------------------------------------------------------------

def test_no_feasible_pathway_produces_no_shares():
    req = _request()
    # Empty eligible set → no pathway can win
    mc = run_mc_compare(req, feasible_pathways=set())
    for r in mc:
        assert r.win_count == 0
        assert r.optimality_share == pytest.approx(0.0)

    # merge_mc_into_results with all-rejected results also sets no shares
    results = [_rejected_result(AD), _rejected_result(COMP)]
    merged = merge_mc_into_results(results, mc)
    for r in merged:
        assert r.optimality_note is None
        assert r.optimality_share is None


# ---------------------------------------------------------------------------
# 8. optimality_note text on all feasible merged results
# ---------------------------------------------------------------------------

def test_optimality_note_present_on_all_merged_results():
    req = _request(mc_runs=50)
    mc = run_mc_compare(req, feasible_pathways={AD, COMP})
    results = [_feasible_result(AD), _feasible_result(COMP)]
    merged = merge_mc_into_results(results, mc)
    expected_fragment = "highest modelled annual net value"
    for r in merged:
        assert r.optimality_note is not None
        assert expected_fragment in r.optimality_note
