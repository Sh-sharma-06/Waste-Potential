"""
Cost engine for the Waste-Potential decision module.

Computes annualised CAPEX (via Capital Recovery Factor), combines with OPEX and
revenue streams, and assembles per-tonne LP objective coefficients consumed by
optimizer.py.

Design decisions:
- Global defaults: discount_rate=0.07, asset_life_years=20.
- Per-technology overrides via a cost_params dict — same pattern as AR6 /
  operator-override in emission_factors.py.
- net_electricity ≤ 0 returns cost_per_kwh=None (sentinel) and adds a grid
  import cost instead; electricity_revenue is forced to 0.0.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Global defaults (overridable per technology via cost_params)
# ---------------------------------------------------------------------------
DEFAULT_DISCOUNT_RATE: float = 0.07       # 7 %
DEFAULT_ASSET_LIFE_YEARS: int = 20        # years
DEFAULT_GRID_IMPORT_PRICE: float = 0.30   # £/kWh — operator should override


# ---------------------------------------------------------------------------
# Standalone CRF helper — importable by other modules without instantiating
# CostEngine (e.g. pathways/compare.py uses this directly).
# ---------------------------------------------------------------------------

def crf(rate: float, years: int) -> float:
    """Capital Recovery Factor — module-level convenience wrapper.

    Delegates to CostEngine.crf() so the formula lives in exactly one place.

    Parameters
    ----------
    rate:
        Discount rate (dimensionless, e.g. 0.07 for 7 %).
    years:
        Asset life in years (positive integer).

    Returns
    -------
    float
        CRF value: rate · (1 + rate)^years / [(1 + rate)^years − 1].

    Raises
    ------
    ValueError
        If rate ≤ 0 or years ≤ 0.
    """
    return CostEngine.crf(rate, years)


# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TechnologyParams:
    """All financial and operational parameters for a single treatment technology.

    Attributes
    ----------
    tech_id:
        String identifier of the technology (matches the LP key `j`).
        Accepts any string (e.g. PostGIS UUID, integer string).
    capex:
        Total capital expenditure (£ or $). Must be ≥ 0.
    opex_annual:
        Annual operating expenditure (already annualised, same currency as capex).
    throughput_tonnes_yr:
        Design throughput in tonnes/year. Must be > 0.
    net_electricity_kwh_yr:
        Net electricity exported to the grid per year (kWh/year). Positive =
        exporter; zero or negative = consumer or break-even.
    gate_fee_per_tonne:
        Revenue received per tonne of waste accepted (£/tonne). Default 0.
    hauling_cost_per_tonne_km:
        Road hauling cost in currency per tonne-km (e.g. INR/tonne-km).
        Multiplied by ``road_km`` (from cost_params) to add a per-tonne
        transport cost to the LP coefficient.  Default 0.0 (no hauling cost).
    cost_params:
        Optional overrides for discount_rate, asset_life_years, grid_import_price,
        and road_km.  Keys:
          "discount_rate"       (float)
          "asset_life_years"    (int)
          "grid_import_price"   (float, £/kWh)
          "road_km"             (float) — one-way road distance for hauling cost
    """
    tech_id: str
    capex: float
    opex_annual: float
    throughput_tonnes_yr: float
    net_electricity_kwh_yr: float = 0.0
    gate_fee_per_tonne: float = 0.0
    hauling_cost_per_tonne_km: float = 0.0
    cost_params: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.capex < 0:
            raise ValueError(f"capex must be ≥ 0, got {self.capex}")
        if self.throughput_tonnes_yr <= 0:
            raise ValueError(
                f"throughput_tonnes_yr must be > 0, got {self.throughput_tonnes_yr}"
            )
        if self.hauling_cost_per_tonne_km < 0:
            raise ValueError(
                f"hauling_cost_per_tonne_km must be ≥ 0, got {self.hauling_cost_per_tonne_km}"
            )


@dataclass
class LPCostCoeff:
    """Per-tonne LP objective coefficients for technology *j*.

    The optimizer uses:
      net_cost_per_tonne = cost_per_tonne + hauling_cost_per_tonne
                         + grid_import_cost_per_tonne
                         - gate_fee_per_tonne
                         - electricity_revenue_per_tonne

    Attributes
    ----------
    tech_id:
        Technology string identifier.
    cost_per_tonne:
        Total annualised cost divided by design throughput (£/tonne).
    gate_fee_per_tonne:
        Revenue per tonne of waste accepted.
    electricity_revenue_per_tonne:
        Electricity export revenue per tonne processed. Zero when
        net_electricity ≤ 0.
    grid_import_cost_per_tonne:
        Additional grid electricity purchase cost per tonne when the
        technology is a net consumer. Zero when net_electricity > 0.
    hauling_cost_per_tonne:
        Road transport cost per tonne (hauling_cost_per_tonne_km × road_km).
        Zero when either factor is 0.
    cost_per_kwh:
        Total annualised cost divided by net electricity exported. None when
        net_electricity ≤ 0 (undefined — callers must check before use).
    """
    tech_id: str
    cost_per_tonne: float
    gate_fee_per_tonne: float
    electricity_revenue_per_tonne: float
    grid_import_cost_per_tonne: float
    hauling_cost_per_tonne: float
    cost_per_kwh: Optional[float]

    @property
    def net_cost_per_tonne(self) -> float:
        """Net cost coefficient for the LP objective (cost minus revenues)."""
        return (
            self.cost_per_tonne
            + self.hauling_cost_per_tonne
            + self.grid_import_cost_per_tonne
            - self.gate_fee_per_tonne
            - self.electricity_revenue_per_tonne
        )


# ---------------------------------------------------------------------------
# Cost Engine
# ---------------------------------------------------------------------------

class CostEngine:
    """Computes Capital Recovery Factor-based cost coefficients.

    Usage
    -----
    >>> engine = CostEngine(electricity_export_price=0.12)
    >>> coeffs = engine.lp_coefficients(technologies)
    """

    def __init__(
        self,
        electricity_export_price: float = 0.12,   # £/kWh — feed-in / export tariff
    ) -> None:
        """
        Parameters
        ----------
        electricity_export_price:
            Price received per kWh exported to the grid (£/kWh).
        """
        if electricity_export_price < 0:
            raise ValueError(
                f"electricity_export_price must be ≥ 0, got {electricity_export_price}"
            )
        self.electricity_export_price = electricity_export_price

    # ------------------------------------------------------------------
    # Core financial formulas
    # ------------------------------------------------------------------

    @staticmethod
    def crf(r: float, n: int) -> float:
        """Capital Recovery Factor.

        CRF(r, n) = r · (1 + r)^n / [(1 + r)^n − 1]

        Parameters
        ----------
        r:
            Discount rate (dimensionless, e.g. 0.07 for 7 %).
        n:
            Asset life in years (positive integer).

        Raises
        ------
        ValueError
            If r ≤ 0 or n ≤ 0.
        """
        if r <= 0:
            raise ValueError(f"discount_rate must be > 0, got {r}")
        if n <= 0:
            raise ValueError(f"asset_life_years must be > 0, got {n}")
        factor = math.pow(1.0 + r, n)
        return r * factor / (factor - 1.0)

    @staticmethod
    def annualized_capex(capex: float, r: float, n: int) -> float:
        """Return annualised CAPEX = capex × CRF(r, n).

        Parameters
        ----------
        capex:
            Total capital cost (£ or $).
        r:
            Discount rate.
        n:
            Asset life in years.
        """
        return capex * CostEngine.crf(r, n)

    # ------------------------------------------------------------------
    # Per-technology helpers
    # ------------------------------------------------------------------

    def _resolve_params(self, tech: TechnologyParams) -> tuple[float, int, float, float]:
        """Return (discount_rate, asset_life_years, grid_import_price, road_km) for *tech*."""
        r = float(tech.cost_params.get("discount_rate", DEFAULT_DISCOUNT_RATE))
        n = int(tech.cost_params.get("asset_life_years", DEFAULT_ASSET_LIFE_YEARS))
        grid_price = float(
            tech.cost_params.get("grid_import_price", DEFAULT_GRID_IMPORT_PRICE)
        )
        road_km = float(tech.cost_params.get("road_km", 0.0))
        return r, n, grid_price, road_km

    def cost_per_tonne(self, tech: TechnologyParams) -> float:
        """Total annualised cost (CAPEX + OPEX) per tonne of throughput.

        cost_per_tonne = (annualised_capex + opex_annual) / throughput_tonnes_yr
        """
        r, n, _, _road = self._resolve_params(tech)
        ann_capex = self.annualized_capex(tech.capex, r, n)
        total_annual = ann_capex + tech.opex_annual
        return total_annual / tech.throughput_tonnes_yr

    def cost_per_kwh(self, tech: TechnologyParams) -> Optional[float]:
        """Total annualised cost per kWh of net electricity exported.

        Returns None when net_electricity_kwh_yr ≤ 0 (undefined — technology
        is a net electricity consumer). Callers must test for None before use.
        """
        if tech.net_electricity_kwh_yr <= 0:
            return None
        r, n, _, _road = self._resolve_params(tech)
        ann_capex = self.annualized_capex(tech.capex, r, n)
        total_annual = ann_capex + tech.opex_annual
        return total_annual / tech.net_electricity_kwh_yr

    def lp_coefficients(
        self, technologies: list[TechnologyParams]
    ) -> dict[str, LPCostCoeff]:
        """Assemble LP objective cost coefficients for all technologies.

        Parameters
        ----------
        technologies:
            List of TechnologyParams, one per treatment technology.

        Returns
        -------
        dict mapping tech_id (str) → LPCostCoeff.
        """
        result: dict[str, LPCostCoeff] = {}

        for tech in technologies:
            r, n, grid_import_price, road_km = self._resolve_params(tech)
            ann_capex = self.annualized_capex(tech.capex, r, n)
            total_annual = ann_capex + tech.opex_annual
            cpt = total_annual / tech.throughput_tonnes_yr

            net_kwh = tech.net_electricity_kwh_yr

            # Hauling cost (INR/tonne) = rate × road distance
            hauling_cost_per_tonne = tech.hauling_cost_per_tonne_km * road_km

            if net_kwh > 0:
                # Net exporter — electricity revenue applies
                elec_revenue_annual = net_kwh * self.electricity_export_price
                elec_rev_per_tonne = elec_revenue_annual / tech.throughput_tonnes_yr
                grid_import_cost_per_tonne = 0.0
                cpkwh: Optional[float] = total_annual / net_kwh
            else:
                # Net consumer or break-even — no grid revenue; add import cost
                elec_rev_per_tonne = 0.0
                import_kwh = abs(net_kwh)
                grid_import_annual = import_kwh * grid_import_price
                grid_import_cost_per_tonne = grid_import_annual / tech.throughput_tonnes_yr
                cpkwh = None  # undefined sentinel

            result[tech.tech_id] = LPCostCoeff(
                tech_id=tech.tech_id,
                cost_per_tonne=cpt,
                gate_fee_per_tonne=tech.gate_fee_per_tonne,
                electricity_revenue_per_tonne=elec_rev_per_tonne,
                grid_import_cost_per_tonne=grid_import_cost_per_tonne,
                hauling_cost_per_tonne=hauling_cost_per_tonne,
                cost_per_kwh=cpkwh,
            )

        return result
