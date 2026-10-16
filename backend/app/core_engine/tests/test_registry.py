"""
Tests for backend/app/core_engine/registry.py

Contract requirements verified:
  1. Every Params field has exactly one registry row.
  2. Every registry row name maps back to a Params field.
  3. Registry value equals the Params default for scalar fields.
  4. Unknown name raises KeyError with a descriptive message.
  5. defaults_used(Params()) lists all fields (all are 'illustrative', not 'validated').
  6. units column is never empty for any row.
"""

import dataclasses
import math
import pytest
from pathlib import Path

from app.core_engine.params import Params
from app.core_engine.registry import load_registry, ParameterEntry

# ---------------------------------------------------------------------------
# Fixture: load registry once per test session from the real CSV
# ---------------------------------------------------------------------------

CSV_PATH = str(
    Path(__file__).resolve().parents[4] / "docs" / "parameter_registry.csv"
)


@pytest.fixture(scope="session")
def reg():
    """Load the real registry CSV (cache cleared per session)."""
    load_registry.cache_clear()
    return load_registry(path=CSV_PATH)


@pytest.fixture(scope="session")
def default_params():
    return Params()


# ---------------------------------------------------------------------------
# Helper: enumerate all Params field names
# ---------------------------------------------------------------------------

def _param_field_names() -> list[str]:
    return [f.name for f in dataclasses.fields(Params)]


def _registry_names(reg) -> set[str]:
    return {e.name for e in reg.all_entries()}


# ---------------------------------------------------------------------------
# 1. Every Params field has exactly one registry row
# ---------------------------------------------------------------------------

def test_every_params_field_covered(reg):
    """Each Params field must have a direct row in the registry."""
    registry_names = _registry_names(reg)
    for field_name in _param_field_names():
        assert field_name in registry_names, (
            f"Params field '{field_name}' has no registry row."
        )


# ---------------------------------------------------------------------------
# 2. Every registry row maps back to a Params field (no orphans)
# ---------------------------------------------------------------------------

def test_every_registry_row_maps_to_params_field(reg):
    """No orphan rows in the CSV."""
    param_names = set(_param_field_names())
    for entry in reg.all_entries():
        assert entry.name in param_names, (
            f"Registry row '{entry.name}' does not correspond to any Params field. "
            f"Params fields: {sorted(param_names)}"
        )


# ---------------------------------------------------------------------------
# 3. Registry value matches Params default for scalar (float) fields
# ---------------------------------------------------------------------------

def test_registry_scalar_values_match_defaults(reg, default_params):
    """For every float field, the CSV value must equal the Params default."""
    for entry in reg.all_entries():
        default_val = getattr(default_params, entry.name)
        if isinstance(default_val, float):
            try:
                csv_val = float(entry.value)
            except ValueError:
                pytest.fail(
                    f"Registry value for float field '{entry.name}' is not numeric: '{entry.value}'"
                )
            assert math.isclose(csv_val, default_val, rel_tol=1e-9), (
                f"Registry value {csv_val} != Params default {default_val} for '{entry.name}'"
            )


# ---------------------------------------------------------------------------
# 4. Unknown name raises KeyError with a meaningful message
# ---------------------------------------------------------------------------

def test_unknown_name_raises_key_error(reg):
    with pytest.raises(KeyError, match="Unknown parameter name 'totally_unknown'"):
        reg.get("totally_unknown")


# ---------------------------------------------------------------------------
# 5. defaults_used on default Params lists all fields (none are 'validated')
# ---------------------------------------------------------------------------

def test_defaults_used_lists_all_fields(reg, default_params):
    unvalidated = reg.defaults_used(default_params)
    all_fields = sorted(_param_field_names())
    assert unvalidated == all_fields, (
        f"defaults_used should return all {len(all_fields)} field names.\n"
        f"Missing: {set(all_fields) - set(unvalidated)}\n"
        f"Extra:   {set(unvalidated) - set(all_fields)}"
    )


# ---------------------------------------------------------------------------
# 6. units column is never empty
# ---------------------------------------------------------------------------

def test_units_column_never_empty(reg):
    for entry in reg.all_entries():
        assert entry.unit.strip() != "", (
            f"Registry row '{entry.name}' has an empty 'unit' column."
        )


# ---------------------------------------------------------------------------
# 7. All rows have status == 'illustrative'
# ---------------------------------------------------------------------------

def test_all_rows_are_illustrative(reg):
    for entry in reg.all_entries():
        assert entry.status == "illustrative", (
            f"Row '{entry.name}' has status '{entry.status}', expected 'illustrative'."
        )


# ---------------------------------------------------------------------------
# 8. Exactly 22 rows — one per Params field
# ---------------------------------------------------------------------------

def test_registry_has_exactly_22_rows(reg):
    entries = reg.all_entries()
    assert len(entries) == 22, (
        f"Expected 22 registry rows, got {len(entries)}: {[e.name for e in entries]}"
    )


# ---------------------------------------------------------------------------
# 9. Params validation — fraction out of range raises
# ---------------------------------------------------------------------------

def test_params_fraction_validation():
    with pytest.raises(ValueError, match="must be in \\[0, 1\\]"):
        Params(organic_fraction=1.5)


def test_params_fraction_zero_allowed():
    """availability=0.0 is numerically valid — must NOT raise."""
    p = Params(availability=0.0)
    assert p.availability == 0.0


def test_params_negative_mass_raises():
    with pytest.raises(ValueError, match="must be >= 0"):
        Params(hrt_days=-1.0)


def test_params_composition_bad_sum_raises():
    """Tuple composition that doesn't sum to 1 must raise."""
    with pytest.raises(ValueError, match="must sum to 1"):
        Params(composition=(0.5, 0.3, 0.1))  # sums to 0.9


def test_params_composition_good_sum_ok():
    p = Params(composition=(0.5, 0.3, 0.2))
    assert p.composition[2] == 0.2


def test_params_eta_boiler_must_exceed_eta_th():
    with pytest.raises(ValueError, match="eta_boiler"):
        Params(eta_boiler=0.40, eta_th=0.45)


def test_params_implausible_values_allowed():
    """availability=0.0 and y_biogas=1.5 must construct without error."""
    p = Params(availability=0.0, y_biogas_nm3_per_kg_vs=1.5)
    assert p.availability == 0.0
    assert p.y_biogas_nm3_per_kg_vs == 1.5


def test_params_negative_temperatures_allowed():
    """digester_temp_c and ambient_temp_c may be negative."""
    p = Params(digester_temp_c=-5.0, ambient_temp_c=-20.0)
    assert p.digester_temp_c == -5.0
    assert p.ambient_temp_c == -20.0


# ---------------------------------------------------------------------------
# 10. Re-export: `from app.core_engine.engine import Params` still works
# ---------------------------------------------------------------------------

def test_params_reexport_from_engine():
    from app.core_engine.engine import Params as ParamsFromEngine
    assert ParamsFromEngine is Params
