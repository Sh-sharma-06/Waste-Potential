"""
FastAPI router for the Waste-Potential decision module.

Exposes four endpoints:

  POST /optimize          — Runs the LP allocator + Pareto filter.
  POST /costs             — Runs the cost engine (CRF + annualised CAPEX/OPEX).
  POST /carbon/package    — Runs the carbon calculator (GHG delta + breakdown).
  POST /marketplace/match — Runs the marketplace matching algorithm.

Error handling (strict):
  All endpoint logic is wrapped in try/except blocks.
  Physical or mathematical rejections → HTTP 422 Unprocessable Entity with a
  detailed message. Unexpected server-side errors → HTTP 500.

  Specific 422 triggers:
    /optimize:   Optimizer returns is_feasible=False (infeasible LP).
    /carbon:     BoundaryMismatchError from BoundaryValidator.
    All endpoints: ValueError from data-contract validation.
"""

from __future__ import annotations

import traceback
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

from .carbon import (
    BaselineScenario,
    BoundaryMismatchError,
    CarbonCalculator,
    ProposedScenario,
    ProposedTechnology,
    WasteStream,
)
from .cost import CostEngine, TechnologyParams
from .market import MarketMatcher
from .objectives import AllocationScenarioMetrics, MultiObjectiveScorer, ObjectiveWeights
from .optimizer import Optimizer, ScipyBackend, WasteScenario
from .pareto import ParetoFilter
from .specs import BuyerProfile, FacilityOutput, ProductSpec

router = APIRouter(prefix="/decision", tags=["Decision Engine"])


# ===========================================================================
# Pydantic request / response models
# ===========================================================================

# ---------------------------------------------------------------------------
# /optimize
# ---------------------------------------------------------------------------

class OptimizeRequest(BaseModel):
    """Request body for POST /optimize.

    supply and capacity are flat dicts keyed by string IDs.
    Composite keys use the pipe '|' delimiter: 'stream_id|tech_id'.
    """
    supply: dict[str, float] = Field(
        ..., description="stream_id (str) → available supply tonnes/year"
    )
    capacity: dict[str, float] = Field(
        ..., description="tech_id (str) → treatment capacity tonnes/year"
    )
    compatibility_matrix: dict[str, int] = Field(
        ...,
        description=(
            "JSON-safe flat dict: key = 'stream_id|tech_id' (e.g. 'stream_1|tech_A'), "
            "value = 1 (compatible) or 0 (incompatible)."
        ),
    )
    objective_coefficients: dict[str, float] = Field(
        ...,
        description=(
            "Flat dict: key = 'stream_id|tech_id', "
            "value = pre-computed per-tonne LP objective coefficient."
        ),
    )
    w_cost: float = Field(1.0, ge=0.0, le=1.0)
    w_carbon: float = Field(0.0, ge=0.0, le=1.0)
    w_transport: float = Field(0.0, ge=0.0, le=1.0)

    # Pareto sweep: list of (w_cost, w_carbon, w_transport) weight triplets.
    # If supplied, the optimizer is run once per triplet and the Pareto filter
    # is applied to the full population.  When absent, a single run is performed.
    pareto_weight_sweep: list[dict[str, float]] | None = Field(
        None,
        description=(
            "Optional list of weight dicts for a Pareto sweep. "
            "Each dict must contain w_cost, w_carbon, w_transport summing to 1.0."
        ),
    )

    @model_validator(mode="after")
    def _weights_sum_to_one(self) -> "OptimizeRequest":
        total = self.w_cost + self.w_carbon + self.w_transport
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"w_cost + w_carbon + w_transport must equal 1.0, got {total:.8f}."
            )
        return self


class ParetoCandidateOut(BaseModel):
    scenario_id: str
    norm_cost: float
    norm_carbon: float
    norm_transport: float
    composite_score: float
    raw_cost: float
    raw_carbon: float
    raw_transport: float


class OptimizeResponse(BaseModel):
    is_feasible: bool
    solver_status: str
    objective_value: float | None
    allocation: dict[str, float]         # key = "stream_id|tech_id"
    pareto_front: list[ParetoCandidateOut] | None = None
    n_pareto: int | None = None


# ---------------------------------------------------------------------------
# /costs
# ---------------------------------------------------------------------------

class TechParamsIn(BaseModel):
    tech_id: str
    capex: float = Field(..., ge=0.0)
    opex_annual: float = Field(..., ge=0.0)
    throughput_tonnes_yr: float = Field(..., gt=0.0)
    net_electricity_kwh_yr: float = 0.0
    gate_fee_per_tonne: float = 0.0
    discount_rate: float | None = Field(None, ge=0.0, le=1.0)
    asset_life_years: int | None = Field(None, ge=1)
    grid_import_price: float | None = Field(None, ge=0.0)


class LPCostCoeffOut(BaseModel):
    tech_id: str
    cost_per_tonne: float
    gate_fee_per_tonne: float
    electricity_revenue_per_tonne: float
    grid_import_cost_per_tonne: float
    net_cost_per_tonne: float
    cost_per_kwh: float | None


class CostsResponse(BaseModel):
    coefficients: list[LPCostCoeffOut]


# ---------------------------------------------------------------------------
# /carbon/package
# ---------------------------------------------------------------------------

class WasteStreamIn(BaseModel):
    stream_id: str
    supply_tonnes_yr: float = Field(..., ge=0.0)
    baseline_type: str
    distance_to_baseline_km: float = Field(0.0, ge=0.0)


class ProposedTechIn(BaseModel):
    tech_id: str
    direct_emission_factor: float = Field(..., ge=0.0)
    net_electricity_kwh_per_tonne: float = 0.0
    aux_energy_kwh_per_tonne: float = Field(0.0, ge=0.0)
    distances_to_facility_km: dict[str, float] = Field(default_factory=dict)


class CarbonRequest(BaseModel):
    waste_streams: list[WasteStreamIn]
    proposed_technologies: list[ProposedTechIn]
    allocation: dict[str, float] = Field(
        ..., description="Flat dict: key = 'stream_id|tech_id', value = tonnes/year."
    )
    include_transport: bool = True
    gwp_period: str = "GWP100"
    region: str | None = None
    operator_overrides: dict[str, float] = Field(default_factory=dict)


class CarbonResponse(BaseModel):
    total_delta: float
    baseline_total: float
    proposed_total: float
    breakdown: dict[str, float]


# ---------------------------------------------------------------------------
# /marketplace/match
# ---------------------------------------------------------------------------

class ProductSpecIn(BaseModel):
    product_type: str
    parameters: dict[str, float] = Field(default_factory=dict)


class FacilityOutputIn(BaseModel):
    facility_id: str
    product: ProductSpecIn
    available_volume: float = Field(..., gt=0.0)
    latitude: float
    longitude: float


class BuyerProfileIn(BaseModel):
    buyer_id: str
    product_type: str
    demand_volume: float
    min_spec_thresholds: dict[str, float] = Field(default_factory=dict)
    bid_price: float = Field(..., ge=0.0)
    latitude: float
    longitude: float
    max_road_distance_km: float = float("inf")


class BuyerMatchOut(BaseModel):
    buyer_id: str
    allocated_volume: float
    road_distance_km: float
    match_score: float
    bid_price: float


class MarketMatchResponse(BaseModel):
    facility_id: str
    total_available: float
    total_allocated: float
    remaining_volume: float
    matches: list[BuyerMatchOut]
    n_eligible_buyers: int
    n_filtered_buyers: int
    filter_reasons: dict[str, str]


# ===========================================================================
# Helper: parse flat "i,j" string keys → (int, int)
# ===========================================================================

def _parse_pair_key(key: str, field_name: str) -> tuple[str, str]:
    """Parse a 'stream_id|tech_id' string key into a (str, str) tuple.

    Accepts the pipe '|' delimiter only.  Raises HTTPException 422 if the
    key is malformed (missing delimiter or more than one '|').
    """
    parts = key.split("|")
    if len(parts) != 2 or not parts[0] or not parts[1]:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Invalid key format in '{field_name}': '{key}'. "
                "Expected 'stream_id|tech_id' (e.g. 'stream_1|tech_A')."
            ),
        )
    return parts[0], parts[1]


# ===========================================================================
# Endpoints
# ===========================================================================

# ---------------------------------------------------------------------------
# POST /optimize
# ---------------------------------------------------------------------------

@router.post("/optimize", response_model=OptimizeResponse)
def optimize(request: OptimizeRequest) -> OptimizeResponse:
    """Run the LP allocation optimizer, then apply the Pareto filter.

    Raises HTTP 422 if:
    - The LP is infeasible (no valid allocation exists).
    - Weight triplets in pareto_weight_sweep do not each sum to 1.0.
    - Any key in compatibility_matrix or objective_coefficients is malformed.
    """
    try:
        # Supply and capacity dicts retain their string keys directly
        supply: dict[str, float] = dict(request.supply)
        capacity: dict[str, float] = dict(request.capacity)

        compat: dict[tuple[str, str], int] = {}
        for k, v in request.compatibility_matrix.items():
            compat[_parse_pair_key(k, "compatibility_matrix")] = v

        obj_raw: dict[tuple[str, str], float] = {}
        for k, v in request.objective_coefficients.items():
            obj_raw[_parse_pair_key(k, "objective_coefficients")] = v

        # Single-run or Pareto sweep
        if request.pareto_weight_sweep:
            # Validate all sweep weight triplets
            sweep_weights: list[dict[str, float]] = []
            for idx, wt in enumerate(request.pareto_weight_sweep):
                total = wt.get("w_cost", 0) + wt.get("w_carbon", 0) + wt.get("w_transport", 0)
                if abs(total - 1.0) > 1e-6:
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            f"pareto_weight_sweep[{idx}] weights sum to {total:.8f}, "
                            "not 1.0."
                        ),
                    )
                sweep_weights.append(wt)

            opt = Optimizer(ScipyBackend())
            scenarios: list[AllocationScenarioMetrics] = []

            for idx, wt in enumerate(sweep_weights):
                weights_dict = {
                    "w_cost": wt.get("w_cost", 0.0),
                    "w_carbon": wt.get("w_carbon", 0.0),
                    "w_transport": wt.get("w_transport", 0.0),
                }
                scenario = WasteScenario(
                    supply=supply,
                    capacity=capacity,
                    compatibility_matrix=compat,
                    objective_coefficients=obj_raw,
                    weights=weights_dict,
                )
                res = opt.solve(scenario)
                if not res.success:
                    raise HTTPException(
                        status_code=422,
                        detail=(
                            f"LP allocation is infeasible for Pareto sweep point {idx} "
                            f"(w_cost={wt.get('w_cost')}, w_carbon={wt.get('w_carbon')}, "
                            f"w_transport={wt.get('w_transport')}). "
                            f"Solver status: '{res.solver_status}'. "
                            "Check that supply/capacity constraints are mutually satisfiable."
                        ),
                    )
                # Compute aggregate metrics from allocation for scoring
                total_cost = sum(
                    obj_raw.get(pair, 0.0) * v
                    for pair, v in res.allocation.items()
                )
                scenarios.append(AllocationScenarioMetrics(
                    scenario_id=f"sweep_{idx}",
                    total_cost=total_cost,
                    total_carbon=total_cost,        # placeholder — caller should inject real values
                    total_transport_distance=0.0,   # placeholder
                    allocation=res.allocation,
                ))

            scorer = MultiObjectiveScorer()
            obj_weights = ObjectiveWeights(
                w_cost=request.w_cost,
                w_carbon=request.w_carbon,
                w_transport=request.w_transport,
            )
            scored = scorer.score(scenarios, obj_weights)
            pareto_result = ParetoFilter().filter(scored)

            pareto_out = [
                ParetoCandidateOut(
                    scenario_id=s.scenario_id,
                    norm_cost=s.norm_cost,
                    norm_carbon=s.norm_carbon,
                    norm_transport=s.norm_transport,
                    composite_score=s.composite_score,
                    raw_cost=s.raw.total_cost,
                    raw_carbon=s.raw.total_carbon,
                    raw_transport=s.raw.total_transport_distance,
                )
                for s in pareto_result.pareto_front
            ]

            # Return the best-scoring Pareto candidate as the primary allocation
            best = pareto_result.pareto_front[0] if pareto_result.pareto_front else scored[0]
            best_alloc = best.raw.allocation or {}
            return OptimizeResponse(
                is_feasible=True,
                solver_status="optimal",
                objective_value=best.composite_score,
                allocation={f"{i}|{j}": v for (i, j), v in best_alloc.items()},
                pareto_front=pareto_out,
                n_pareto=pareto_result.n_pareto,
            )

        else:
            # Single-run (no Pareto sweep)
            scenario = WasteScenario(
                supply=supply,
                capacity=capacity,
                compatibility_matrix=compat,
                objective_coefficients=obj_raw,
                weights={
                    "w_cost": request.w_cost,
                    "w_carbon": request.w_carbon,
                    "w_transport": request.w_transport,
                },
            )
            opt = Optimizer(ScipyBackend())
            res = opt.solve(scenario)

            if not res.success:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"LP allocation is infeasible. "
                        f"Solver status: '{res.solver_status}'. "
                        "Check that supply/capacity constraints allow a valid allocation. "
                        "Verify that at least one compatible (stream_id, tech_id) pair exists "
                        "and that supply ≤ total compatible capacity."
                    ),
                )

            return OptimizeResponse(
                is_feasible=True,
                solver_status=res.solver_status,
                objective_value=res.objective_value,
                allocation={f"{i}|{j}": v for (i, j), v in res.allocation.items()},
            )

    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected optimizer error: {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# POST /costs
# ---------------------------------------------------------------------------

@router.post("/costs", response_model=CostsResponse)
def compute_costs(technologies: list[TechParamsIn]) -> CostsResponse:
    """Compute CRF-based annualised cost coefficients for a list of technologies.

    Raises HTTP 422 if any technology parameter violates physical constraints
    (e.g. capex < 0, throughput ≤ 0).
    """
    try:
        engine = CostEngine()
        tech_params: list[TechnologyParams] = []
        for t in technologies:
            cost_params: dict[str, Any] = {}
            if t.discount_rate is not None:
                cost_params["discount_rate"] = t.discount_rate
            if t.asset_life_years is not None:
                cost_params["asset_life_years"] = t.asset_life_years
            if t.grid_import_price is not None:
                cost_params["grid_import_price"] = t.grid_import_price

            tech_params.append(TechnologyParams(
                tech_id=t.tech_id,
                capex=t.capex,
                opex_annual=t.opex_annual,
                throughput_tonnes_yr=t.throughput_tonnes_yr,
                net_electricity_kwh_yr=t.net_electricity_kwh_yr,
                gate_fee_per_tonne=t.gate_fee_per_tonne,
                cost_params=cost_params,
            ))

        coeffs = engine.lp_coefficients(tech_params)
        return CostsResponse(coefficients=[
            LPCostCoeffOut(
                tech_id=c.tech_id,
                cost_per_tonne=c.cost_per_tonne,
                gate_fee_per_tonne=c.gate_fee_per_tonne,
                electricity_revenue_per_tonne=c.electricity_revenue_per_tonne,
                grid_import_cost_per_tonne=c.grid_import_cost_per_tonne,
                net_cost_per_tonne=c.net_cost_per_tonne,
                cost_per_kwh=c.cost_per_kwh,
            )
            for c in coeffs.values()
        ])

    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected cost engine error: {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# POST /carbon/package
# ---------------------------------------------------------------------------

@router.post("/carbon/package", response_model=CarbonResponse)
def carbon_package(request: CarbonRequest) -> CarbonResponse:
    """Compute itemized GHG delta for a proposed vs. baseline waste scenario.

    Raises HTTP 422 if:
    - IPCC boundary-matching rules are violated (BoundaryMismatchError).
    - An unknown baseline_type or emission factor key is supplied.
    - Any physical constraint on input values is violated.
    """
    try:
        # Build domain objects
        waste_streams = [
            WasteStream(
                stream_id=ws.stream_id,
                supply_tonnes_yr=ws.supply_tonnes_yr,
                baseline_type=ws.baseline_type,
                distance_to_baseline_km=ws.distance_to_baseline_km,
            )
            for ws in request.waste_streams
        ]

        proposed_techs = [
            ProposedTechnology(
                tech_id=pt.tech_id,
                direct_emission_factor=pt.direct_emission_factor,
                net_electricity_kwh_per_tonne=pt.net_electricity_kwh_per_tonne,
                aux_energy_kwh_per_tonne=pt.aux_energy_kwh_per_tonne,
                distances_to_facility_km=dict(pt.distances_to_facility_km),
            )
            for pt in request.proposed_technologies
        ]

        allocation: dict[tuple[str, str], float] = {
            _parse_pair_key(k, "allocation"): v
            for k, v in request.allocation.items()
        }

        baseline = BaselineScenario(
            waste_streams=waste_streams,
            include_transport=request.include_transport,
            gwp_period=request.gwp_period,
        )
        proposed = ProposedScenario(
            technologies=proposed_techs,
            include_transport=request.include_transport,
            gwp_period=request.gwp_period,
        )

        calc = CarbonCalculator(
            region=request.region,
            operator_overrides=request.operator_overrides or {},
        )
        result = calc.ghg_delta(baseline, proposed, allocation)

        return CarbonResponse(
            total_delta=result.total_delta,
            baseline_total=result.baseline_total,
            proposed_total=result.proposed_total,
            breakdown=result.breakdown,
        )

    except BoundaryMismatchError as exc:
        raise HTTPException(
            status_code=422,
            detail=(
                f"IPCC system boundary violation: {exc}. "
                "Ensure baseline and proposed scenarios use the same transport "
                "inclusion flag, GWP period, and waste stream set."
            ),
        ) from exc
    except HTTPException:
        raise
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected carbon calculator error: {exc}",
        ) from exc


# ---------------------------------------------------------------------------
# POST /marketplace/match
# ---------------------------------------------------------------------------

@router.post("/marketplace/match", response_model=MarketMatchResponse)
def marketplace_match(
    facility: FacilityOutputIn,
    buyers: list[BuyerProfileIn],
) -> MarketMatchResponse:
    """Match a facility's product output to eligible buyers.

    Raises HTTP 422 if:
    - facility.available_volume ≤ 0.
    - Any buyer bid_price < 0.
    """
    try:
        fac = FacilityOutput(
            facility_id=facility.facility_id,
            product=ProductSpec(
                product_type=facility.product.product_type,
                parameters=facility.product.parameters,
            ),
            available_volume=facility.available_volume,
            latitude=facility.latitude,
            longitude=facility.longitude,
        )

        buyer_objs = [
            BuyerProfile(
                buyer_id=b.buyer_id,
                product_type=b.product_type,
                demand_volume=b.demand_volume,
                min_spec_thresholds=b.min_spec_thresholds,
                bid_price=b.bid_price,
                latitude=b.latitude,
                longitude=b.longitude,
                max_road_distance_km=b.max_road_distance_km,
            )
            for b in buyers
        ]

        matcher = MarketMatcher()
        result = matcher.match(fac, buyer_objs)

        return MarketMatchResponse(
            facility_id=result.facility_id,
            total_available=result.total_available,
            total_allocated=result.total_allocated,
            remaining_volume=result.remaining_volume,
            matches=[
                BuyerMatchOut(
                    buyer_id=m.buyer_id,
                    allocated_volume=m.allocated_volume,
                    road_distance_km=m.road_distance_km,
                    match_score=m.match_score,
                    bid_price=m.bid_price,
                )
                for m in result.matches
            ],
            n_eligible_buyers=result.n_eligible_buyers,
            n_filtered_buyers=result.n_filtered_buyers,
            filter_reasons=result.filter_reasons,
        )

    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unexpected marketplace matching error: {exc}",
        ) from exc
