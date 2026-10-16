"""
Emission factor registry for the Waste-Potential carbon calculator.

Two-layer lookup:
  1. IPCC AR6 GWP100 values hardcoded as the authoritative baseline.
  2. Database-backed operator override dict injected at call time — keeps this
     module free of any database import so it is always unit-testable in isolation.

All values are in kgCO2e per the stated functional unit.
AR6 GWP100 characterisation factors (methane = 29.8, N2O = 273) are from:
  IPCC Sixth Assessment Report (2021), WG1, Table 7.SM.7.
"""

from __future__ import annotations

from typing import Optional

# ---------------------------------------------------------------------------
# GWP characterisation period supported in Phase 1
# ---------------------------------------------------------------------------
GWP_PERIOD = "GWP100"

# ---------------------------------------------------------------------------
# IPCC AR6 GWP100 hardcoded baseline factors
#
# Key               Unit                    Source / notes
# ---------------------------------------------------------------------------
AR6_FACTORS: dict[str, float] = {
    # Grid electricity — UK average (DESNZ 2023, consistent with AR6 grid
    # displacement methodology); operators must override for other regions.
    "grid_electricity": 0.233,          # kgCO2e / kWh

    # Diesel combustion (tank-to-wheel, IPCC AR6 Annex II)
    "diesel": 2.68,                     # kgCO2e / litre

    # Natural gas combustion (lower heating value basis, IPCC AR6)
    "natural_gas": 0.202,               # kgCO2e / kWh

    # Landfill CH4 — degradable organic carbon method, GWP100 CH4=29.8
    # Representative value for mixed municipal solid waste.
    # Ref: IPCC 2006 Guidelines Vol.5 Ch.3, updated with AR6 GWP.
    "landfill_ch4": 467.0,              # kgCO2e / tonne waste

    # Road freight transport (HGV, average load factor)
    # Ref: IPCC AR6 WG3 Annex II; GLEC Framework 2.0
    "transport_road": 0.096,            # kgCO2e / tonne-km

    # Direct CO2 from waste incineration (mixed MSW, biogenic excluded)
    # Ref: IPCC 2006 Guidelines Vol.5 Ch.5, non-biogenic fraction only
    "incineration_co2": 330.0,          # kgCO2e / tonne waste

    # Open burning of waste (uncontrolled; CO2e includes CH4, N2O, CO)
    # Ref: IPCC 2006 Guidelines Vol.5 Ch.5 Table 5.3
    "open_burning_co2e": 1550.0,        # kgCO2e / tonne waste

    # Incineration without energy recovery (same stack emissions as
    # incineration_co2 — alias used by the dynamic baseline dispatcher)
    "incineration_no_recovery": 330.0,  # kgCO2e / tonne waste
}

# ---------------------------------------------------------------------------
# Regional AR6 variants
#
# Keyed as (region_code: str, factor_key: str) -> float.
# Region codes follow ISO 3166-1 alpha-2 for countries or UN M.49 for
# supranational zones (e.g. "EU", "US", "IN").
#
# Only `grid_electricity` meaningfully varies by region in Phase 1.
# Additional regional factors can be added here without changing carbon.py.
# ---------------------------------------------------------------------------
REGIONAL_AR6: dict[tuple[str, str], float] = {
    ("EU", "grid_electricity"): 0.276,   # kgCO2e / kWh — EU-27 average 2022
    ("US", "grid_electricity"): 0.386,   # kgCO2e / kWh — EPA eGRID 2022
    ("IN", "grid_electricity"): 0.708,   # kgCO2e / kWh — India CEA 2022
    ("CN", "grid_electricity"): 0.581,   # kgCO2e / kWh — China NBS 2022
    ("AU", "grid_electricity"): 0.510,   # kgCO2e / kWh — DCCEEW 2022
}

# ---------------------------------------------------------------------------
# Baseline type → factor key mapping
#
# Used by carbon.py to dispatch to the right factor for a given baseline_type
# string without hardcoding any baseline logic in the calculator itself.
# Extend this dict to add new baseline types — no changes to carbon.py needed.
# ---------------------------------------------------------------------------
BASELINE_TYPE_FACTOR_MAP: dict[str, str] = {
    "landfill": "landfill_ch4",
    "open_burning": "open_burning_co2e",
    "incineration_no_recovery": "incineration_no_recovery",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class UnknownFactorKeyError(KeyError):
    """Raised when a requested emission factor key has no registered value."""


class UnknownBaselineTypeError(KeyError):
    """Raised when a baseline_type string has no registered factor mapping."""


def get_factor(
    key: str,
    *,
    region: Optional[str] = None,
    operator_overrides: Optional[dict[str, float]] = None,
) -> float:
    """Return the emission factor for *key* using three-layer resolution.

    Resolution order (highest priority first):
      1. operator_overrides  — DB-backed values injected by the service layer.
      2. REGIONAL_AR6        — AR6 regional variant for (region, key).
      3. AR6_FACTORS         — Global IPCC AR6 GWP100 default.

    Parameters
    ----------
    key:
        Emission factor key (see AR6_FACTORS for valid keys).
    region:
        Optional ISO 3166-1 alpha-2 or UN M.49 region code.
    operator_overrides:
        Optional dict of operator-supplied overrides loaded from the DB at
        request time. Must not contain database objects — plain floats only.

    Raises
    ------
    UnknownFactorKeyError
        If *key* is not present in any layer of the registry.
    """
    if operator_overrides and key in operator_overrides:
        return float(operator_overrides[key])

    if region is not None:
        regional_value = REGIONAL_AR6.get((region, key))
        if regional_value is not None:
            return regional_value

    if key in AR6_FACTORS:
        return AR6_FACTORS[key]

    raise UnknownFactorKeyError(
        f"Emission factor key '{key}' is not registered in AR6_FACTORS, "
        f"REGIONAL_AR6, or the supplied operator_overrides. "
        f"Valid AR6 keys: {sorted(AR6_FACTORS)}"
    )


def get_baseline_factor_key(baseline_type: str) -> str:
    """Return the AR6_FACTORS key that corresponds to *baseline_type*.

    Raises
    ------
    UnknownBaselineTypeError
        If *baseline_type* is not registered in BASELINE_TYPE_FACTOR_MAP.
    """
    key = BASELINE_TYPE_FACTOR_MAP.get(baseline_type)
    if key is None:
        raise UnknownBaselineTypeError(
            f"Baseline type '{baseline_type}' is not registered. "
            f"Valid types: {sorted(BASELINE_TYPE_FACTOR_MAP)}"
        )
    return key
