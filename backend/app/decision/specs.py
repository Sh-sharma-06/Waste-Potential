"""
Shared dataclasses for the Waste-Potential marketplace matching layer.

These types are imported by both market.py and router.py.
They define the data contracts for:
  - Facility output (what is being sold / offered)
  - Product specifications (quality parameters)
  - Buyer profiles (demand, minimum spec thresholds, bid price, location)
  - Match results (scored allocations)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Product specification
# ---------------------------------------------------------------------------

@dataclass
class ProductSpec:
    """Quality specification of a facility's output product.

    A facility may produce multiple product streams (e.g. biogas AND digestate).
    This dataclass represents one product stream.

    Attributes
    ----------
    product_type:
        Human-readable product identifier, e.g. "biogas", "digestate",
        "compost", "syngas", "RDF".
    parameters:
        Dict of quality parameters and their measured values.
        Keys are parameter names; values are floats.
        Examples:
          {"methane_pct": 62.5}           — biogas purity
          {"N_pct": 3.2, "P_pct": 1.1, "K_pct": 2.8}  — fertilizer NPK
          {"calorific_value_mj_kg": 18.5} — RDF calorific value
    """
    product_type: str
    parameters: dict[str, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Facility output (seller side)
# ---------------------------------------------------------------------------

@dataclass
class FacilityOutput:
    """Available output from a treatment facility.

    Attributes
    ----------
    facility_id:
        Unique identifier for the facility.
    product:
        Product specification (type + quality parameters).
    available_volume:
        Quantity available for sale (tonnes/year or kWh/year — must match
        buyer demand units). Must be > 0.
    latitude:
        WGS-84 latitude of the facility (decimal degrees).
    longitude:
        WGS-84 longitude of the facility (decimal degrees).
    """
    facility_id: str
    product: ProductSpec
    available_volume: float
    latitude: float
    longitude: float

    def __post_init__(self) -> None:
        if self.available_volume <= 0:
            raise ValueError(
                f"FacilityOutput.available_volume must be > 0, "
                f"got {self.available_volume} for facility '{self.facility_id}'."
            )


# ---------------------------------------------------------------------------
# Buyer profile (demand side)
# ---------------------------------------------------------------------------

@dataclass
class BuyerProfile:
    """A potential buyer of the facility's product.

    Attributes
    ----------
    buyer_id:
        Unique identifier for the buyer.
    product_type:
        The product type this buyer purchases. Must match FacilityOutput.product.product_type
        for the buyer to be considered compatible.
    demand_volume:
        Maximum volume the buyer can accept (same units as FacilityOutput.available_volume).
        Must be > 0 for the buyer to be eligible.
    min_spec_thresholds:
        Dict of minimum acceptable quality parameter values.
        Keys must be a subset of the facility's ProductSpec.parameters keys.
        A buyer is dropped if any facility parameter falls below its threshold.
        Example: {"methane_pct": 55.0} means the buyer requires ≥ 55 % methane.
    bid_price:
        Price the buyer is willing to pay per unit volume (£/tonne or £/kWh).
        Must be ≥ 0.
    latitude:
        WGS-84 latitude of the buyer's intake point (decimal degrees).
    longitude:
        WGS-84 longitude of the buyer's intake point (decimal degrees).
    max_road_distance_km:
        Maximum allowable road distance from the facility to this buyer (km).
        Buyers whose computed road distance exceeds this are hard-filtered out.
        Default: no limit (float infinity).
    """
    buyer_id: str
    product_type: str
    demand_volume: float
    min_spec_thresholds: dict[str, float]
    bid_price: float
    latitude: float
    longitude: float
    max_road_distance_km: float = float("inf")

    def __post_init__(self) -> None:
        if self.bid_price < 0:
            raise ValueError(
                f"BuyerProfile.bid_price must be ≥ 0, "
                f"got {self.bid_price} for buyer '{self.buyer_id}'."
            )


# ---------------------------------------------------------------------------
# Match result
# ---------------------------------------------------------------------------

@dataclass
class BuyerMatch:
    """A single buyer allocation in a market match result.

    Attributes
    ----------
    buyer_id:
        The matched buyer's ID.
    allocated_volume:
        Volume allocated to this buyer (same units as FacilityOutput).
    road_distance_km:
        Computed road distance (km) from facility to buyer.
    match_score:
        Composite match score in [0.0, 1.0]. Higher is better.
        score = 0.6 * norm_bid_price + 0.4 * norm_inverse_distance
    bid_price:
        The buyer's bid price (carried through for transparency).
    """
    buyer_id: str
    allocated_volume: float
    road_distance_km: float
    match_score: float
    bid_price: float


@dataclass
class MarketMatchResult:
    """Full result of a marketplace matching run.

    Attributes
    ----------
    facility_id:
        The facility whose output was matched.
    total_available:
        Original available volume before allocation.
    total_allocated:
        Total volume allocated across all matched buyers.
    remaining_volume:
        Unallocated volume (total_available - total_allocated).
    matches:
        List of BuyerMatch objects, sorted descending by match_score.
    n_eligible_buyers:
        Number of buyers that passed all hard filters.
    n_filtered_buyers:
        Number of buyers that were dropped by hard filters.
    filter_reasons:
        Dict mapping buyer_id → rejection reason string for all filtered buyers.
    """
    facility_id: str
    total_available: float
    total_allocated: float
    remaining_volume: float
    matches: list[BuyerMatch]
    n_eligible_buyers: int
    n_filtered_buyers: int
    filter_reasons: dict[str, str] = field(default_factory=dict)
