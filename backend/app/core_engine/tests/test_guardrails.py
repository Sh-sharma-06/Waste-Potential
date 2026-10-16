"""
Tests for backend/app/core_engine/guardrails.py

Coverage:
  - parse_formula: correct atom counts, unknown element raises, empty raises
  - atom_balance residuals < 1e-9 for carbohydrate, protein, lipid (string input)
  - theoretical_ch4_nm3_per_kg_vs matches canonical coefficients within 1% (string input)
  - buswell_bound with tuple and dict composition; bad sum raises
  - check_vs_destruction threshold edge cases
  - check_input_ranges with Params dataclass instance and dict
  - check_methane_yield below/at/above bound
"""

import math
import pytest
from dataclasses import replace

from app.core_engine.guardrails import (
    FORMULA_CARB,
    FORMULA_LIPID,
    FORMULA_PROT,
    SUPPORTED_RANGES,
    atom_balance,
    buswell_bound,
    check_input_ranges,
    check_methane_yield,
    check_vs_destruction,
    parse_formula,
    theoretical_ch4_nm3_per_kg_vs,
)
from app.core_engine.params import Params


# ---------------------------------------------------------------------------
# parse_formula
# ---------------------------------------------------------------------------

def test_parse_formula_carbohydrate():
    f = parse_formula("C6H10O5")
    assert f.c == 6 and f.h == 10 and f.o == 5 and f.n == 0 and f.s == 0


def test_parse_formula_protein():
    f = parse_formula("C5H7NO2")
    assert f.c == 5 and f.h == 7 and f.o == 2 and f.n == 1 and f.s == 0


def test_parse_formula_lipid():
    f = parse_formula("C57H104O6")
    assert f.c == 57 and f.h == 104 and f.o == 6


def test_parse_formula_with_sulfur():
    f = parse_formula("C2H6S")
    assert f.c == 2 and f.h == 6 and f.s == 1


def test_parse_formula_unknown_element_raises():
    with pytest.raises(ValueError, match="unknown element"):
        parse_formula("C6H10O5Fe")


def test_parse_formula_empty_raises():
    with pytest.raises(ValueError):
        parse_formula("")


def test_parse_formula_whitespace_raises():
    with pytest.raises(ValueError):
        parse_formula("   ")


# ---------------------------------------------------------------------------
# atom_balance — string input, residuals < 1e-9
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("formula_str,label", [
    ("C6H10O5",  "carbohydrate"),
    ("C5H7NO2",  "protein"),
    ("C57H104O6", "lipid"),
])
def test_atom_balance_string_residuals_near_zero(formula_str, label):
    residuals = atom_balance(formula_str)
    for element, residual in residuals.items():
        assert abs(residual) < 1e-9, (
            f"atom_balance({label!r}): element {element} residual {residual} >= 1e-9"
        )


def test_atom_balance_object_still_works():
    """MolecularFormula objects must still be accepted (backward compat)."""
    residuals = atom_balance(FORMULA_CARB)
    for v in residuals.values():
        assert abs(v) < 1e-9


# ---------------------------------------------------------------------------
# theoretical_ch4_nm3_per_kg_vs — string input, matches canonical within 1%
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("formula_str,canonical,label", [
    ("C6H10O5",  0.415, "carbohydrate"),
    ("C5H7NO2",  0.496, "protein"),
    ("C57H104O6", 1.014, "lipid"),
])
def test_theoretical_yield_string_within_1pct(formula_str, canonical, label):
    derived = theoretical_ch4_nm3_per_kg_vs(formula_str)
    rel_err = abs(derived - canonical) / canonical
    assert rel_err < 0.01, (
        f"theoretical_ch4_nm3_per_kg_vs({formula_str!r}): "
        f"derived={derived:.5f}, canonical={canonical}, rel_err={rel_err:.4%}"
    )


def test_theoretical_yield_object_still_works():
    derived = theoretical_ch4_nm3_per_kg_vs(FORMULA_LIPID)
    assert abs(derived - 1.014) / 1.014 < 0.01


# ---------------------------------------------------------------------------
# buswell_bound — tuple and dict; bad sum raises
# ---------------------------------------------------------------------------

def test_buswell_bound_tuple():
    result = buswell_bound((0.6, 0.2, 0.2))
    expected = 0.6 * 0.415 + 0.2 * 0.496 + 0.2 * 1.014
    assert math.isclose(result, expected, rel_tol=1e-9)
    assert math.isclose(result, 0.551, rel_tol=1e-4)


def test_buswell_bound_dict():
    result = buswell_bound({"carbs": 1.0, "protein": 0.0, "lipid": 0.0})
    assert math.isclose(result, 0.415)


def test_buswell_bound_pure_lipid_tuple():
    assert math.isclose(buswell_bound((0.0, 0.0, 1.0)), 1.014)


def test_buswell_bound_bad_sum_tuple_raises():
    with pytest.raises(ValueError, match="must sum to 1"):
        buswell_bound((0.5, 0.2, 0.2))  # sums to 0.9


def test_buswell_bound_bad_sum_dict_raises():
    with pytest.raises(ValueError, match="must sum to 1"):
        buswell_bound({"carbs": 0.5, "protein": 0.3, "lipid": 0.1})


# ---------------------------------------------------------------------------
# check_vs_destruction — threshold edge cases
# ---------------------------------------------------------------------------

def test_vs_destruction_exactly_at_limit_no_warning():
    assert check_vs_destruction(85.0, 100.0) is None


def test_vs_destruction_just_above_limit_warns():
    result = check_vs_destruction(85.1, 100.0)
    assert result is not None and "WARNING" in result


def test_vs_destruction_zero_vs_no_warning():
    assert check_vs_destruction(50.0, 0.0) is None


def test_vs_destruction_well_below_limit():
    assert check_vs_destruction(50.0, 100.0) is None


def test_vs_destruction_custom_limit():
    result = check_vs_destruction(75.0, 100.0, limit=0.70)
    assert result is not None and "WARNING" in result


# ---------------------------------------------------------------------------
# check_input_ranges — Params dataclass instance
# ---------------------------------------------------------------------------

def test_check_input_ranges_params_default_all_in_range():
    """Default Params() must produce no out-of-range flags."""
    assert check_input_ranges(Params()) == []


def test_check_input_ranges_params_hrt_too_low():
    flags = check_input_ranges(replace(Params(), hrt_days=5.0))
    assert len(flags) == 1
    field, value, low, high = flags[0]
    assert field == "hrt_days" and value == 5.0


def test_check_input_ranges_params_ts_too_high():
    flags = check_input_ranges(replace(Params(), ts_fraction=0.6))
    assert any(item[0] == "ts_fraction" for item in flags)


def test_check_input_ranges_dict_still_works():
    """Dict input must still be accepted (backward compat)."""
    assert check_input_ranges({"hrt_days": 20.0}) == []
    flags = check_input_ranges({"hrt_days": 5.0})
    assert flags[0][0] == "hrt_days"


def test_check_input_ranges_never_raises():
    params = {k: -999.0 for k in SUPPORTED_RANGES}
    result = check_input_ranges(params)
    assert isinstance(result, list)


def test_check_input_ranges_unknown_key_ignored():
    assert check_input_ranges({"totally_unknown": 999.0}) == []


def test_check_input_ranges_nonnumeric_skipped():
    """Non-numeric values (e.g. a tuple) must be silently skipped."""
    result = check_input_ranges({"ts_fraction": (0.1, 0.2)})
    assert result == []


# ---------------------------------------------------------------------------
# SUPPORTED_RANGES keys must all be real Params field names
# ---------------------------------------------------------------------------

def test_supported_ranges_keys_are_params_fields():
    import dataclasses
    param_names = {f.name for f in dataclasses.fields(Params)}
    for key in SUPPORTED_RANGES:
        assert key in param_names, (
            f"SUPPORTED_RANGES key '{key}' is not a Params field name."
        )


# ---------------------------------------------------------------------------
# check_methane_yield
# ---------------------------------------------------------------------------

def test_check_methane_yield_below_bound_returns_none():
    assert check_methane_yield(0.40, 0.55) is None


def test_check_methane_yield_at_bound_returns_none():
    assert check_methane_yield(0.55, 0.55) is None


def test_check_methane_yield_above_bound_returns_warning():
    result = check_methane_yield(0.60, 0.55)
    assert result is not None and "WARNING" in result and "Buswell" in result
