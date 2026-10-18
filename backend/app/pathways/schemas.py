"""
Pydantic schemas for the POST /pathways/compare endpoint.

Frontend contract (strict — field names must not change):
  Request:
    PathwayCompareRequest
      - farm_id         : str
      - waste_tpd       : float          tonnes/day of available waste
      - pathways        : list[str]      pathway identifiers to evaluate.
                          Accepted values (all 7 supported by the physics engine):
                            "anaerobic_digestion", "composting", "incineration",
                            "gasification", "pyrolysis", "htc", "torrefaction"
      - capex_inr       : dict[str,float] pathway → total CAPEX in INR
      - opex_inr_yr     : dict[str,float] pathway → annual OPEX in INR
      - asset_life_yr   : dict[str,int]  pathway → asset life (years)
      - discount_rate   : float          shared discount rate (default 0.07)
      - electricity_price_inr_kwh : float INR per kWh export/import
      - gate_fee_inr_t  : dict[str,float] pathway → revenue per tonne accepted
      - net_kwh_per_tonne: dict[str,float] pathway → net kWh exported per tonne
      - direct_ghg_kg_per_tonne: dict[str,float] pathway → kgCO2e per tonne
      - capacity_tpd    : dict[str,float] pathway → facility max tonnes/day
      - distance_km     : float          distance from farm to facility (km)
      - max_distance_km : float          hard upper-limit distance filter (default 200 km)
      - mc_runs         : int            Monte Carlo iterations (default 500)
      - mc_cost_cv      : float          coefficient of variation for cost (default 0.15)
      - mc_yield_cv     : float          coefficient of variation for yield (default 0.10)
      - region          : str | None     ISO region code for grid emissions
      - operator_overrides: dict[str,float] emission factor overrides
      - location_id     : str            site identifier for P3 data lookup (default "default")
      - crop_type       : str | None     crop for ML yield prediction (optional)
      - area_ha         : float | None   cultivated area in hectares (optional)
      - soil_index      : float | None   soil quality index 0–1 (optional, default 0.75)

  Response:
    list[PathwayResult]
      - pathway         : str
      - feasible        : bool
      - reasons         : list[str]       populated when feasible=False
      - outputs         : dict[str,float] key outputs (e.g. biogas_m3_d, compost_t_d …)
      - revenue_inr_y   : float
      - cost_inr_y      : float
      - annual_net_value_inr : float      revenue_inr_y − cost_inr_y
      - e_net_kwh_d     : float           net kWh/day exported (negative = net consumer)
      - status          : str             "feasible" | "rejected" | "uncertain"
      - warnings        : list[str]       non-fatal caveats
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field, model_validator


# ===========================================================================
# Request
# ===========================================================================

class PathwayCompareRequest(BaseModel):
    """Request body for POST /pathways/compare.

    All monetary values are in INR (Indian Rupees) to align with the India
    pilot farm context. Energy in kWh. Mass in tonnes.
    """

    farm_id: str = Field(..., description="Unique identifier of the source farm / waste stream.")

    waste_tpd: float = Field(
        ..., gt=0.0, description="Available waste feedstock in tonnes per day."
    )

    pathways: list[str] = Field(
        ..., min_length=1, description="Ordered list of pathway IDs to evaluate."
    )

    # --- Financial parameters (per pathway) ---
    capex_inr: dict[str, float] = Field(
        default_factory=dict,
        description="Total capital expenditure in INR per pathway.",
    )
    opex_inr_yr: dict[str, float] = Field(
        default_factory=dict,
        description="Annual operating expenditure in INR per pathway.",
    )
    asset_life_yr: dict[str, int] = Field(
        default_factory=dict,
        description="Asset life in years per pathway (default: 20).",
    )
    discount_rate: float = Field(
        0.07, gt=0.0, le=1.0,
        description="Shared discount rate for CAPEX annualisation (default 7 %).",
    )

    # --- Revenue parameters ---
    electricity_price_inr_kwh: float = Field(
        0.0, ge=0.0,
        description="INR per kWh for electricity export (revenue) or import (cost).",
    )
    gate_fee_inr_t: dict[str, float] = Field(
        default_factory=dict,
        description="Tipping / gate fee received per tonne of waste (INR/tonne).",
    )

    # --- Technical parameters (per pathway) ---
    net_kwh_per_tonne: dict[str, float] = Field(
        default_factory=dict,
        description="Net kWh exported per tonne of waste processed (per pathway).",
    )
    direct_ghg_kg_per_tonne: dict[str, float] = Field(
        default_factory=dict,
        description="Direct GHG emissions in kgCO2e per tonne processed.",
    )
    capacity_tpd: dict[str, float] = Field(
        default_factory=dict,
        description="Maximum treatment capacity in tonnes/day per pathway.",
    )

    # --- Spatial / logistical ---
    distance_km: float = Field(
        0.0, ge=0.0,
        description="One-way road distance from the waste source to the facility (km).",
    )
    max_distance_km: float = Field(
        200.0, ge=0.0,
        description="Hard upper-limit: pathways whose nearest facility exceeds this "
                    "distance are rejected as infeasible (default 200 km).",
    )

    # --- Monte Carlo parameters ---
    mc_runs: int = Field(
        500, ge=10, le=10_000,
        description="Number of Monte Carlo iterations for uncertainty quantification.",
    )
    mc_cost_cv: float = Field(
        0.15, ge=0.0, le=1.0,
        description="Coefficient of variation applied to annualised cost in MC runs.",
    )
    mc_yield_cv: float = Field(
        0.10, ge=0.0, le=1.0,
        description="Coefficient of variation applied to electricity yield in MC runs.",
    )
    mc_seed: int = Field(
        42,
        description="Random seed for reproducible Monte Carlo draws (default 42).",
    )

    # --- Emission factors ---
    region: Optional[str] = Field(
        None, description="ISO 3166-1 alpha-2 region code for regional grid emission factors."
    )
    operator_overrides: dict[str, float] = Field(
        default_factory=dict,
        description="Operator-supplied emission factor overrides (factor_key → kgCO2e/unit).",
    )

    # --- P3 data integration fields ---
    location_id: str = Field(
        "default",
        description="Site identifier used to look up feedstock and location context "
                    "from the P3 data service layer.",
    )
    crop_type: Optional[str] = Field(
        None,
        description="Crop type for ML-based yield prediction via YieldPredictor. "
                    "When provided together with area_ha, overrides waste_tpd with the "
                    "predicted daily biomass.",
    )
    area_ha: Optional[float] = Field(
        None,
        ge=0.0,
        description="Cultivated area in hectares. Required when crop_type is set.",
    )
    soil_index: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Soil quality index in [0, 1]. Used by YieldPredictor when crop_type "
                    "and area_ha are provided (default 0.75 if omitted).",
    )

    @model_validator(mode="after")
    def _check_pathway_coverage(self) -> "PathwayCompareRequest":
        """Warn-level: all per-pathway dicts should cover every pathway listed."""
        # We don't hard-reject missing entries — compare.py uses safe .get() with defaults.
        return self


# ===========================================================================
# Response
# ===========================================================================

class PathwayResult(BaseModel):
    """Screening result for a single evaluated pathway.

    Frontend contract — field names and types are fixed.
    """

    pathway: str = Field(..., description="Pathway identifier (mirrors request).")
    feasible: bool = Field(..., description="True iff the pathway passed all coarse checks.")
    reasons: list[str] = Field(
        default_factory=list,
        description="Rejection reasons (populated when feasible=False).",
    )
    outputs: dict[str, float] = Field(
        default_factory=dict,
        description="Key technical outputs, e.g. {'biogas_m3_d': 420.0, 'compost_t_d': 2.1}.",
    )
    revenue_inr_y: float = Field(
        0.0, description="Estimated annual revenue in INR."
    )
    cost_inr_y: float = Field(
        0.0, description="Estimated annual cost in INR (annualised CAPEX + OPEX)."
    )
    annual_net_value_inr: float = Field(
        0.0, description="Net annual value: revenue_inr_y − cost_inr_y."
    )
    e_net_kwh_d: float = Field(
        0.0, description="Net kWh/day exported (negative = net electricity consumer)."
    )
    model_status: Optional[str] = Field(
        None,
        description="Optional status tag from the ML model or simulation engine, "
                    "e.g. 'converged', 'fallback', 'extrapolated'.",
    )
    status: str = Field(
        ...,
        description="One of: 'feasible', 'rejected', 'uncertain'.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal caveats, e.g. parameter assumptions or data gaps.",
    )
    optimality_share: Optional[float] = Field(
        None,
        description="Fraction of MC runs in which this pathway had the highest "
                    "annual net value among deterministically feasible pathways.",
    )
    win_count: Optional[int] = Field(
        None,
        description="Number of MC runs in which this pathway was the winner.",
    )
    optimality_note: Optional[str] = Field(
        None,
        description="Explanatory note about the optimality share.",
    )
