"""
Carbon calculator for the Waste-Potential decision module.

Computes ghg_delta — the net GHG change of a proposed waste treatment scenario
relative to a defined baseline — using itemized component accounting and strict
IPCC system-boundary matching.

Sign convention (ISO 14064-2 / standard GHG accounting):
  ghg_delta = proposed_emissions - baseline_emissions
  Negative = proposed scenario reduces emissions  (better)
  Positive = proposed scenario increases emissions (worse)

Baseline type is read dynamically from WasteScenario.baseline_type. It is never
hardcoded. New baseline types are registered in emission_factors.BASELINE_TYPE_FACTOR_MAP.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .emission_factors import (
    GWP_PERIOD,
    get_factor,
    get_baseline_factor_key,
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class BoundaryMismatchError(ValueError):
    """Raised when the baseline and proposed scenarios have incompatible system
    boundaries, making direct comparison invalid under IPCC guidelines."""


# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------

@dataclass
class WasteStream:
    """A single waste stream source.

    Attributes
    ----------
    stream_id:
        String identifier of the waste stream (matches LP key `i`).
        Accepts any string (e.g. PostGIS UUID, integer string).
    supply_tonnes_yr:
        Available waste tonnage per year.
    baseline_type:
        Disposal method representing the counterfactual baseline.
        Must be a key registered in BASELINE_TYPE_FACTOR_MAP.
        Examples: "landfill", "open_burning", "incineration_no_recovery".
    distance_to_baseline_km:
        One-way road distance (km) from the waste source to the current
        disposal site. Supply 0.0 if transport emissions are excluded.
    """
    stream_id: str
    supply_tonnes_yr: float
    baseline_type: str
    distance_to_baseline_km: float = 0.0

    def __post_init__(self) -> None:
        if self.supply_tonnes_yr < 0:
            raise ValueError(
                f"supply_tonnes_yr must be ≥ 0, got {self.supply_tonnes_yr}"
            )
        if self.distance_to_baseline_km < 0:
            raise ValueError(
                f"distance_to_baseline_km must be ≥ 0, got {self.distance_to_baseline_km}"
            )


@dataclass
class ProposedTechnology:
    """Emission-relevant parameters for a single treatment technology.

    Attributes
    ----------
    tech_id:
        String identifier (matches LP key `j`).
        Accepts any string (e.g. PostGIS UUID, integer string).
    direct_emission_factor:
        kgCO2e emitted per tonne processed (stack + fugitive, non-biogenic).
    net_electricity_kwh_per_tonne:
        Net kWh exported to the grid per tonne processed.  Positive = exporter.
        Zero or negative = consumer — no electricity credit is applied.
    aux_energy_kwh_per_tonne:
        On-site auxiliary electricity consumption per tonne (kWh/tonne), which
        is treated as a grid import and adds to emissions.
    distances_to_facility_km:
        Dict mapping stream_id → one-way road distance (km) from waste source
        to this facility. Missing stream_ids are treated as 0 km.
    """
    tech_id: str
    direct_emission_factor: float       # kgCO2e / tonne processed
    net_electricity_kwh_per_tonne: float = 0.0
    aux_energy_kwh_per_tonne: float = 0.0
    distances_to_facility_km: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.direct_emission_factor < 0:
            raise ValueError(
                f"direct_emission_factor must be ≥ 0, got {self.direct_emission_factor}"
            )
        if self.aux_energy_kwh_per_tonne < 0:
            raise ValueError(
                f"aux_energy_kwh_per_tonne must be ≥ 0, got {self.aux_energy_kwh_per_tonne}"
            )


@dataclass
class BaselineScenario:
    """Describes the counterfactual baseline scenario.

    Attributes
    ----------
    waste_streams:
        List of WasteStream objects. Every stream_id must be unique.
    include_transport:
        Whether baseline transport emissions are included in the boundary.
        Must match proposed_scenario.include_transport (Rule 3).
    gwp_period:
        GWP characterisation period. Must match proposed_scenario.gwp_period
        (Rule 5). Default: "GWP100".
    """
    waste_streams: list[WasteStream]
    include_transport: bool = True
    gwp_period: str = GWP_PERIOD


@dataclass
class ProposedScenario:
    """Describes the proposed waste treatment scenario.

    Attributes
    ----------
    technologies:
        List of ProposedTechnology objects. Every tech_id must be unique.
    include_transport:
        Whether proposed transport emissions are included in the boundary.
        Must match baseline_scenario.include_transport (Rule 3).
    gwp_period:
        GWP characterisation period. Must match baseline_scenario.gwp_period
        (Rule 5). Default: "GWP100".
    """
    technologies: list[ProposedTechnology]
    include_transport: bool = True
    gwp_period: str = GWP_PERIOD


@dataclass
class GHGResult:
    """Output of the carbon calculator.

    Attributes
    ----------
    total_delta:
        ghg_delta = proposed_total - baseline_total (kgCO2e/year).
        Negative = proposed scenario avoids emissions.
    baseline_total:
        Total baseline emissions (kgCO2e/year).
    proposed_total:
        Total proposed emissions (kgCO2e/year).
    breakdown:
        Itemized components keyed by descriptive label (kgCO2e/year).
    """
    total_delta: float
    baseline_total: float
    proposed_total: float
    breakdown: dict[str, float]


# ---------------------------------------------------------------------------
# Boundary Validator (IPCC Rules 1–5)
# ---------------------------------------------------------------------------

class BoundaryValidator:
    """Validates that baseline and proposed scenarios share compatible system
    boundaries before any GHG calculation is performed.

    Rules (per IPCC guidelines and ISO 14064-2):
      1. Same waste streams — stream_id sets must be identical.
      2. Same functional unit — tonnes/year (enforced by data contract;
         not separately checked at runtime).
      3. Transport symmetry — if one side includes transport, both must.
      4. Grid credit only on proposed side — baseline must not claim electricity.
      5. Consistent GWP period — both scenarios must use the same period.
    """

    @staticmethod
    def validate(
        baseline: BaselineScenario,
        proposed: ProposedScenario,
        allocation: dict[tuple[str, str], float],
    ) -> None:
        """Validate boundary consistency.

        Parameters
        ----------
        baseline:
            The counterfactual baseline scenario.
        proposed:
            The proposed treatment scenario.
        allocation:
            The LP allocation result: dict[(stream_id, tech_id)] -> tonnes/yr.

        Raises
        ------
        BoundaryMismatchError
            On any rule violation.
        """
        # Rule 1 — Same waste streams
        baseline_stream_ids = {ws.stream_id for ws in baseline.waste_streams}
        allocated_stream_ids = {i for i, _ in allocation}
        missing_from_baseline = allocated_stream_ids - baseline_stream_ids
        if missing_from_baseline:
            raise BoundaryMismatchError(
                f"Rule 1 violated: stream_ids {missing_from_baseline} appear in the "
                f"allocation but are absent from the baseline scenario."
            )

        # Rule 3 — Transport symmetry
        if proposed.include_transport != baseline.include_transport:
            raise BoundaryMismatchError(
                f"Rule 3 violated: proposed.include_transport={proposed.include_transport} "
                f"but baseline.include_transport={baseline.include_transport}. "
                "Transport must be included or excluded consistently on both sides."
            )

        # Rule 4 — No grid credit for baseline
        # (Structurally enforced by the data contract — BaselineScenario has no
        # electricity export field. This check guards against any future extension
        # that might accidentally add one.)
        # Nothing to check programmatically in Phase 1.

        # Rule 5 — Consistent GWP period
        if proposed.gwp_period != baseline.gwp_period:
            raise BoundaryMismatchError(
                f"Rule 5 violated: baseline uses GWP period '{baseline.gwp_period}' "
                f"but proposed uses '{proposed.gwp_period}'. "
                "Both scenarios must use the same GWP characterisation period."
            )


# ---------------------------------------------------------------------------
# Carbon Calculator
# ---------------------------------------------------------------------------

_validator = BoundaryValidator()


class CarbonCalculator:
    """Computes itemized GHG delta for a proposed vs. baseline waste scenario.

    All emission factor lookups are delegated to emission_factors.get_factor().
    The calculator itself contains no hardcoded factor values.

    Usage
    -----
    >>> calc = CarbonCalculator()
    >>> result = calc.ghg_delta(baseline, proposed, allocation)
    >>> print(result.total_delta)  # negative = better
    """

    def __init__(
        self,
        region: Optional[str] = None,
        operator_overrides: Optional[dict[str, float]] = None,
    ) -> None:
        """
        Parameters
        ----------
        region:
            Optional ISO 3166-1 alpha-2 region code for regional AR6 variants
            (e.g. "EU", "US"). Passed through to get_factor().
        operator_overrides:
            Optional DB-backed operator emission factor overrides. Plain dict
            of {factor_key: float}. Passed through to get_factor().
        """
        self._region = region
        self._overrides = operator_overrides or {}

    def _factor(self, key: str) -> float:
        return get_factor(key, region=self._region, operator_overrides=self._overrides)

    # ------------------------------------------------------------------
    # Baseline emission itemization
    # ------------------------------------------------------------------

    def _baseline_emissions(
        self, baseline: BaselineScenario
    ) -> tuple[float, dict[str, float]]:
        """Return (total_kgco2e_yr, itemized_breakdown) for the baseline.

        Components:
          - Primary disposal (per baseline_type)
          - Baseline transport (if include_transport is True)
        """
        transport_factor = self._factor("transport_road")
        disposal_total = 0.0
        transport_total = 0.0

        for ws in baseline.waste_streams:
            factor_key = get_baseline_factor_key(ws.baseline_type)
            disposal_factor = self._factor(factor_key)
            disposal_total += ws.supply_tonnes_yr * disposal_factor

            if baseline.include_transport:
                transport_total += (
                    ws.supply_tonnes_yr
                    * ws.distance_to_baseline_km
                    * transport_factor
                )

        breakdown: dict[str, float] = {
            "baseline_disposal": disposal_total,
            "baseline_transport": transport_total,
        }
        total = disposal_total + transport_total
        return total, breakdown

    # ------------------------------------------------------------------
    # Proposed emission itemization
    # ------------------------------------------------------------------

    def _proposed_emissions(
        self,
        proposed: ProposedScenario,
        allocation: dict[tuple[str, str], float],
    ) -> tuple[float, dict[str, float]]:
        """Return (total_kgco2e_yr, itemized_breakdown) for the proposed scenario.

        Components per (i, j) pair:
          - Direct process emissions
          - Electricity export credit (negative contribution when net > 0)
          - Auxiliary energy emissions
          - Proposed transport (if include_transport is True)
        """
        grid_factor = self._factor("grid_electricity")
        transport_factor = self._factor("transport_road")

        # Build tech lookup for O(1) access
        tech_map: dict[str, ProposedTechnology] = {
            t.tech_id: t for t in proposed.technologies
        }

        direct_total = 0.0
        elec_credit_total = 0.0
        aux_energy_total = 0.0
        transport_total = 0.0

        for (stream_id, tech_id), tonnes in allocation.items():
            if tonnes <= 0:
                continue

            tech = tech_map[tech_id]

            direct_total += tonnes * tech.direct_emission_factor

            # Electricity export credit — only when net export is positive
            if tech.net_electricity_kwh_per_tonne > 0:
                elec_credit_total += (
                    tonnes
                    * tech.net_electricity_kwh_per_tonne
                    * grid_factor
                )

            aux_energy_total += tonnes * tech.aux_energy_kwh_per_tonne * grid_factor

            if proposed.include_transport:
                dist = tech.distances_to_facility_km.get(stream_id, 0.0)
                transport_total += tonnes * dist * transport_factor

        # Credit is subtracted (reduces proposed emissions)
        breakdown: dict[str, float] = {
            "proposed_direct_process": direct_total,
            "proposed_electricity_export_credit": -elec_credit_total,
            "proposed_auxiliary_energy": aux_energy_total,
            "proposed_transport": transport_total,
        }
        total = direct_total - elec_credit_total + aux_energy_total + transport_total
        return total, breakdown

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def ghg_delta(
        self,
        baseline: BaselineScenario,
        proposed: ProposedScenario,
        allocation: dict[tuple[str, str], float],
    ) -> GHGResult:
        """Compute the net GHG delta.

        ghg_delta = proposed_emissions - baseline_emissions

        Negative result = proposed scenario reduces emissions (better).
        Positive result = proposed scenario increases emissions (worse).

        Parameters
        ----------
        baseline:
            The counterfactual baseline scenario.
        proposed:
            The proposed waste treatment scenario.
        allocation:
            LP allocation result: dict[(stream_id, tech_id)] -> tonnes/year.
            Produced by Optimizer.solve().

        Returns
        -------
        GHGResult
            Contains total_delta, baseline_total, proposed_total, and itemized
            breakdown.

        Raises
        ------
        BoundaryMismatchError
            If the scenarios violate IPCC boundary-matching rules.
        """
        _validator.validate(baseline, proposed, allocation)

        baseline_total, baseline_breakdown = self._baseline_emissions(baseline)
        proposed_total, proposed_breakdown = self._proposed_emissions(
            proposed, allocation
        )

        combined_breakdown = {**baseline_breakdown, **proposed_breakdown}
        delta = proposed_total - baseline_total

        return GHGResult(
            total_delta=delta,
            baseline_total=baseline_total,
            proposed_total=proposed_total,
            breakdown=combined_breakdown,
        )

    def itemized_breakdown(
        self,
        baseline: BaselineScenario,
        proposed: ProposedScenario,
        allocation: dict[tuple[str, str], float],
    ) -> dict[str, float]:
        """Return only the itemized breakdown dict from ghg_delta().

        Convenience method — equivalent to ghg_delta(...).breakdown.
        """
        return self.ghg_delta(baseline, proposed, allocation).breakdown
