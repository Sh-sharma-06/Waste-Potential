"""resources.py — Resource ledger for waste-to-energy pathway simulation results.

Pure functions: no file, network, or DB access.
Currency / units are noted on each field.

ResourceLedger maps the physical resource inputs consumed by a pathway per day
to a single, uniform data structure so that the orchestrator and any cost/impact
model can work with a common interface regardless of which pathway was chosen.

Mapping rules
-------------
anaerobic_digestion
    electricity_kwh_d  = result["aux_kwh_d"]
    heat_kwh_d         = result["q_demand_kwh_d"]
    water_kg_d         = result["water_added_kg_d"]

composting
    electricity_kwh_d  = result["aux_kwh_d"]

incineration
    electricity_kwh_d  = result["aux_kwh_d"]

gasification
    electricity_kwh_d  = result["aux_kwh_d"] + result["drying_kwh_d"]

pyrolysis
    fuel_kwh_d         = result["process_heat_kwh_d"]

All unmapped fields default to 0.0.  Missing result keys are treated as 0.0.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict

# ---------------------------------------------------------------------------
# Supported pathway names (mirrors feasibility.PATHWAYS)
# ---------------------------------------------------------------------------
_SUPPORTED_PATHWAYS = frozenset(
    {
        "anaerobic_digestion",
        "composting",
        "incineration",
        "gasification",
        "pyrolysis",
    }
)


# ---------------------------------------------------------------------------
# ResourceLedger
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResourceLedger:
    """Daily resource consumption for one pathway run.

    Parameters
    ----------
    electricity_kwh_d:
        Electrical energy consumed [kWh/day].  Includes auxiliary loads and
        (for gasification) pre-drying electricity.  Must be >= 0.
    heat_kwh_d:
        Thermal energy demand [kWh/day].  For AD this is the digester heat
        demand (q_demand_kwh_d).  Must be >= 0.
    water_kg_d:
        Process water consumed or added [kg/day].  For AD this is
        water_added_kg_d (positive = water added, negative = water removed).
        Stored as-is; callers should interpret sign.
    fuel_kwh_d:
        External fuel energy demand [kWh/day].  For pyrolysis this is the
        process heat (process_heat_kwh_d).  Must be >= 0.
    labour_note:
        Free-text note for labour considerations (not quantified in this
        model).  Non-empty string; defaults to "not quantified".
    """

    electricity_kwh_d: float
    heat_kwh_d: float
    water_kg_d: float
    fuel_kwh_d: float
    labour_note: str

    def __post_init__(self) -> None:
        if self.electricity_kwh_d < 0:
            raise ValueError(
                f"ResourceLedger.electricity_kwh_d must be >= 0; "
                f"got {self.electricity_kwh_d}"
            )
        if self.heat_kwh_d < 0:
            raise ValueError(
                f"ResourceLedger.heat_kwh_d must be >= 0; "
                f"got {self.heat_kwh_d}"
            )
        if self.fuel_kwh_d < 0:
            raise ValueError(
                f"ResourceLedger.fuel_kwh_d must be >= 0; "
                f"got {self.fuel_kwh_d}"
            )
        if not self.labour_note:
            raise ValueError("ResourceLedger.labour_note must not be empty.")


# ---------------------------------------------------------------------------
# ledger_from_result
# ---------------------------------------------------------------------------

def ledger_from_result(
    pathway: str,
    result: Dict[str, Any],
) -> ResourceLedger:
    """Build a :class:`ResourceLedger` from a pathway simulator result dict.

    Parameters
    ----------
    pathway:
        Name of the pathway — must be one of the five supported values:
        ``"anaerobic_digestion"``, ``"composting"``, ``"incineration"``,
        ``"gasification"``, ``"pyrolysis"``.
    result:
        The dict returned by the corresponding simulator function.
        Missing keys are treated as 0.0.

    Returns
    -------
    ResourceLedger
        Frozen ledger with resource values mapped per the rules in the module
        docstring.

    Raises
    ------
    ValueError
        If *pathway* is not one of the five supported pathway names.
    """
    if pathway not in _SUPPORTED_PATHWAYS:
        raise ValueError(
            f"Unknown pathway '{pathway}'. "
            f"Must be one of {sorted(_SUPPORTED_PATHWAYS)}."
        )

    def _get(key: str) -> float:
        """Return result[key] as float, or 0.0 if key is absent or None."""
        v = result.get(key)
        if v is None:
            return 0.0
        return float(v)

    electricity_kwh_d: float = 0.0
    heat_kwh_d: float = 0.0
    water_kg_d: float = 0.0
    fuel_kwh_d: float = 0.0

    if pathway == "anaerobic_digestion":
        electricity_kwh_d = _get("aux_kwh_d")
        heat_kwh_d        = _get("q_demand_kwh_d")
        water_kg_d        = _get("water_added_kg_d")

    elif pathway == "composting":
        electricity_kwh_d = _get("aux_kwh_d")

    elif pathway == "incineration":
        electricity_kwh_d = _get("aux_kwh_d")

    elif pathway == "gasification":
        electricity_kwh_d = _get("aux_kwh_d") + _get("drying_kwh_d")

    elif pathway == "pyrolysis":
        fuel_kwh_d = _get("process_heat_kwh_d")

    return ResourceLedger(
        electricity_kwh_d=electricity_kwh_d,
        heat_kwh_d=heat_kwh_d,
        water_kg_d=water_kg_d,
        fuel_kwh_d=fuel_kwh_d,
        labour_note="not quantified",
    )
