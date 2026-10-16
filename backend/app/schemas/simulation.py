"""
simulation.py — Pydantic v2 request/response schemas for the simulation API.

Imports the shared _Base from app.schemas.common (extra="forbid").
"""

from __future__ import annotations

import dataclasses
from typing import Any, Dict, List, Optional

from pydantic import Field, field_validator

from app.schemas.common import _Base


# ---------------------------------------------------------------------------
# Params field names — used by SimRequest validator
# ---------------------------------------------------------------------------

from app.core_engine.params import Params as _Params

_PARAMS_FIELD_NAMES: frozenset = frozenset(
    f.name for f in dataclasses.fields(_Params)
)


# ===========================================================================
# SimRequest
# ===========================================================================

class SimRequest(_Base):
    """Incoming simulation request."""

    process: str = "anaerobic_digestion"
    location_id: Optional[str] = None
    waste_mass_kg_day: Optional[float] = Field(default=None, gt=0, le=1e6)
    organic_fraction: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    suitable_fraction: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    use_ml_yield: bool = False
    operating: Optional[Dict[str, float]] = None
    overrides: Dict[str, float] = Field(default_factory=dict)

    @field_validator("overrides")
    @classmethod
    def _validate_override_keys(cls, v: Dict[str, float]) -> Dict[str, float]:
        unknown = set(v.keys()) - _PARAMS_FIELD_NAMES
        if unknown:
            raise ValueError(
                f"overrides contains unknown Params field names: {sorted(unknown)}. "
                f"Valid names: {sorted(_PARAMS_FIELD_NAMES)}."
            )
        return v


# ===========================================================================
# RuleWarningModel
# ===========================================================================

class RuleWarningModel(_Base):
    """Mirrors risk_rules.RuleWarning."""

    code: str
    severity: str
    stage: str
    message: str
    basis: str


# ===========================================================================
# SimResults
# ===========================================================================

class SimResults(_Base):
    """All keys returned by engine.simulate()."""

    # Mass flows [kg/day]
    organic_kg_d: float
    suitable_kg_d: float
    rejected_kg_d: float
    water_added_kg_d: float
    feed_kg_d: float
    vs_kg_d: float
    biogas_kg_d: float
    digestate_kg_d: float

    # Volumes / geometry
    digester_m3: float
    biogas_nm3_d: float
    ch4_nm3_d: float

    # Per-VS metrics
    ch4_nm3_per_kg_vs: float
    buswell_bound: float
    vs_destruction: float

    # Mass balance
    mass_residual_kg: float

    # Energy [kWh/day]
    e_chem_kwh_d: float
    flared_kwh_d: float
    q_demand_kwh_d: float
    q_feed_kwh_d: float
    q_loss_kwh_d: float
    boiler_chem_kwh_d: float
    chp_chem_kwh_d: float
    e_gross_kwh_d: float
    aux_kwh_d: float
    e_net_kwh_d: float
    heat_surplus_kwh_d: float

    # Flags / metadata
    heat_deficit: bool
    out_of_range_inputs: List[str]
    warnings: List[str]
    status: str


# ===========================================================================
# SimResponse
# ===========================================================================

class SimResponse(_Base):
    """Full simulation response envelope."""

    id: str
    inputs: Dict[str, Any]
    params: Dict[str, Any]
    results: SimResults
    notes: Dict[str, Any] = Field(default_factory=dict)
    model_version: str
    audit_hash: str
    status: str
    defaults_used_unvalidated: List[str]
    warnings_detail: List[RuleWarningModel] = Field(default_factory=list)
    missing_inputs: List[str] = Field(default_factory=list)


# ===========================================================================
# ParameterEntryModel
# ===========================================================================

class ParameterEntryModel(_Base):
    """One row of docs/parameter_registry.csv."""

    name: str
    value: str
    unit: str
    mass_basis: str
    status: str
    source: str
    uncertainty: str
    model_version: str
    description: str


# ===========================================================================
# UncertaintyRequest
# ===========================================================================

class UncertaintyRequest(_Base):
    """Parameters for a Monte Carlo uncertainty run.

    Attributes
    ----------
    n:
        Number of Monte Carlo iterations [dimensionless]. Must be 10–20 000.
    seed:
        Random seed for reproducibility.
    distribution_overrides:
        Optional dict mapping Params field names to distribution-spec dicts.
        Each spec must have at least ``"kind"`` and ``"args"`` keys (matching
        the ``Dist`` dataclass in montecarlo.py). When None the engine uses
        ``montecarlo.default_dists()``.
    """

    n: int = Field(default=2000, ge=10, le=20000)
    seed: int = 42
    distribution_overrides: Optional[Dict[str, Any]] = None


# ===========================================================================
# UncertaintyResult
# ===========================================================================

class _SensitivityItem(_Base):
    input: str
    abs_spearman: float


class UncertaintyResult(_Base):
    """Mirrors the dict returned by montecarlo.run_mc()."""

    n: int
    seed: int
    median: float
    p2_5: float
    p97_5: float
    p_net_nonpositive: float
    runs_with_warnings: int
    sensitivity: List[_SensitivityItem]
    distributions: Dict[str, Any]
    assumptions_note: str
