"""
Marketplace matching engine for the Waste-Potential decision module.

Algorithm (exact, per specification):
  1. INPUTS
     - FacilityOutput: available volume + product specs + coordinates.
     - List[BuyerProfile]: each with demand, min-spec thresholds, bid price,
       coordinates, and max allowable road distance.

  2. DISTANCE
     Mock OSRM function: road_distance = haversine_km * 1.3
     (The 1.3x multiplier approximates the road network detour ratio.
     Replace with a live OSRM HTTP call when a routing server is available.)

  3. HARD FILTER — drop a buyer if ANY of:
     a. road_distance_km > buyer.max_road_distance_km
     b. buyer.demand_volume <= 0
     c. Any facility spec parameter is below the buyer's minimum threshold
        (for each threshold key, facility param value < threshold value)
     d. buyer.product_type != facility.product.product_type

  4. SCORING — for eligible buyers:
     match_score = (norm_bid_price * 0.6) + (norm_inverse_distance * 0.4)
     where:
       norm_bid_price       = (bid - min_bid) / (max_bid - min_bid)  [0→1]
       norm_inverse_distance = 1 - (dist - min_dist) / (max_dist - min_dist)  [0→1]
     When all bids or all distances are equal, the normalised value is 0.5.
     Higher score is better.

  5. ALLOCATION
     Sort eligible buyers descending by match_score.
     Iterate: assigned = min(remaining_output, buyer_demand)
              remaining_output -= assigned
     Stop when remaining_output == 0 or list exhausted.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .specs import (
    BuyerMatch,
    BuyerProfile,
    FacilityOutput,
    MarketMatchResult,
)


# ---------------------------------------------------------------------------
# Mock OSRM routing
# ---------------------------------------------------------------------------

_ROAD_DETOUR_MULTIPLIER: float = 1.3


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Straight-line (great-circle) distance in km between two WGS-84 points."""
    R = 6371.0  # Earth radius, km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    return 2 * R * math.asin(math.sqrt(a))


def mock_osrm_road_distance(
    facility_lat: float,
    facility_lon: float,
    buyer_lat: float,
    buyer_lon: float,
) -> float:
    """Return a mock road distance (km) using straight-line × 1.3 detour ratio.

    This function is a stand-in for a live OSRM HTTP request. Replace the body
    with an actual OSRM table/route API call when a routing server is available.
    The function signature must remain identical.

    Returns
    -------
    float
        Estimated road distance in kilometres.
    """
    straight_line = _haversine_km(facility_lat, facility_lon, buyer_lat, buyer_lon)
    return straight_line * _ROAD_DETOUR_MULTIPLIER


# ---------------------------------------------------------------------------
# Market Matcher
# ---------------------------------------------------------------------------

class MarketMatcher:
    """Matches a facility's available output to the best eligible buyers.

    Usage
    -----
    >>> matcher = MarketMatcher()
    >>> result = matcher.match(facility, buyers)
    """

    # --- Hard filter --------------------------------------------------------

    @staticmethod
    def _hard_filter(
        facility: FacilityOutput,
        buyers: list[BuyerProfile],
    ) -> tuple[list[tuple[BuyerProfile, float]], dict[str, str]]:
        """Apply hard eligibility filters.

        Returns
        -------
        eligible: list of (BuyerProfile, road_distance_km) tuples
        filter_reasons: {buyer_id: reason} for all dropped buyers
        """
        eligible: list[tuple[BuyerProfile, float]] = []
        filter_reasons: dict[str, str] = {}

        for buyer in buyers:
            # Rule b — demand must be positive
            if buyer.demand_volume <= 0:
                filter_reasons[buyer.buyer_id] = (
                    f"demand_volume={buyer.demand_volume} is ≤ 0."
                )
                continue

            # Rule d — product type must match
            if buyer.product_type != facility.product.product_type:
                filter_reasons[buyer.buyer_id] = (
                    f"product_type mismatch: buyer requires '{buyer.product_type}', "
                    f"facility offers '{facility.product.product_type}'."
                )
                continue

            # Rule a — road distance
            road_km = mock_osrm_road_distance(
                facility.latitude, facility.longitude,
                buyer.latitude, buyer.longitude,
            )
            if road_km > buyer.max_road_distance_km:
                filter_reasons[buyer.buyer_id] = (
                    f"road_distance={road_km:.2f} km exceeds "
                    f"max_road_distance_km={buyer.max_road_distance_km:.2f} km."
                )
                continue

            # Rule c — spec thresholds
            spec_fail: str | None = None
            for param_key, threshold in buyer.min_spec_thresholds.items():
                facility_value = facility.product.parameters.get(param_key)
                if facility_value is None:
                    spec_fail = (
                        f"spec parameter '{param_key}' is not present in "
                        f"facility product '{facility.product.product_type}'."
                    )
                    break
                if facility_value < threshold:
                    spec_fail = (
                        f"spec '{param_key}': facility value {facility_value} "
                        f"is below buyer minimum threshold {threshold}."
                    )
                    break
            if spec_fail:
                filter_reasons[buyer.buyer_id] = spec_fail
                continue

            eligible.append((buyer, road_km))

        return eligible, filter_reasons

    # --- Scoring ------------------------------------------------------------

    @staticmethod
    def _score_eligible(
        eligible: list[tuple[BuyerProfile, float]],
    ) -> list[tuple[BuyerProfile, float, float]]:
        """Compute match scores for eligible (buyer, road_km) pairs.

        match_score = 0.6 * norm_bid_price + 0.4 * norm_inverse_distance

        norm_bid_price:       (bid - min_bid) / (max_bid - min_bid)
        norm_inverse_distance: 1 - (dist - min_dist) / (max_dist - min_dist)

        When range == 0 (all values identical), normalised value is 0.5.

        Returns
        -------
        List of (BuyerProfile, road_km, match_score) sorted descending by score.
        """
        if not eligible:
            return []

        bids = [b.bid_price for b, _ in eligible]
        dists = [d for _, d in eligible]

        min_bid, max_bid = min(bids), max(bids)
        min_dist, max_dist = min(dists), max(dists)
        bid_span = max_bid - min_bid
        dist_span = max_dist - min_dist

        scored: list[tuple[BuyerProfile, float, float]] = []
        for (buyer, dist) in eligible:
            norm_bid = (
                (buyer.bid_price - min_bid) / bid_span
                if bid_span > 0
                else 0.5
            )
            norm_inv_dist = (
                1.0 - (dist - min_dist) / dist_span
                if dist_span > 0
                else 0.5
            )
            score = 0.6 * norm_bid + 0.4 * norm_inv_dist
            scored.append((buyer, dist, score))

        scored.sort(key=lambda t: t[2], reverse=True)
        return scored

    # --- Allocation ---------------------------------------------------------

    @staticmethod
    def _allocate(
        available_volume: float,
        scored: list[tuple[BuyerProfile, float, float]],
    ) -> list[BuyerMatch]:
        """Greedily allocate product to buyers in descending score order.

        For each buyer:
          assigned = min(remaining_output, buyer.demand_volume)
          remaining_output -= assigned
        Stops when remaining_output == 0 or list exhausted.
        """
        remaining = available_volume
        matches: list[BuyerMatch] = []

        for buyer, road_km, score in scored:
            if remaining <= 0:
                break
            assigned = min(remaining, buyer.demand_volume)
            remaining -= assigned
            matches.append(BuyerMatch(
                buyer_id=buyer.buyer_id,
                allocated_volume=assigned,
                road_distance_km=road_km,
                match_score=score,
                bid_price=buyer.bid_price,
            ))

        return matches

    # --- Public API ---------------------------------------------------------

    def match(
        self,
        facility: FacilityOutput,
        buyers: list[BuyerProfile],
    ) -> MarketMatchResult:
        """Run the full marketplace matching pipeline.

        Parameters
        ----------
        facility:
            The facility offering product output.
        buyers:
            All potential buyers to evaluate.

        Returns
        -------
        MarketMatchResult with allocated matches sorted by match_score descending.
        """
        eligible, filter_reasons = self._hard_filter(facility, buyers)
        scored = self._score_eligible(eligible)
        matches = self._allocate(facility.available_volume, scored)

        total_allocated = sum(m.allocated_volume for m in matches)

        return MarketMatchResult(
            facility_id=facility.facility_id,
            total_available=facility.available_volume,
            total_allocated=total_allocated,
            remaining_volume=facility.available_volume - total_allocated,
            matches=matches,
            n_eligible_buyers=len(eligible),
            n_filtered_buyers=len(filter_reasons),
            filter_reasons=filter_reasons,
        )
