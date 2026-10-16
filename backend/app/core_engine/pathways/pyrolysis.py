"""Pyrolysis pathway model — product energy and process heat balance.

All default parameter values are ILLUSTRATIVE, not validated plant data.
Units: kg/d (mass flows), kWh/d (energy), wet-basis mass unless noted.
This model operates on a thermal (chemical energy) basis, not electricity.

Formulae
--------
dry_kg_d              = M * (1 - moisture_fraction)
moisture_to_remove    = max(0, water_in_feed - water_at_target_moisture)
drying_kwh_d          = moisture_to_remove * 2.26 / 3.6
                        [assumed electric drying; 2.26 MJ/kg latent heat of evaporation]
oil_kg_d              = dry_kg_d * oil_yield
char_kg_d             = dry_kg_d * char_yield
gas_kg_d              = dry_kg_d * gas_yield
product_energy_kwh_d  = (oil_kg_d*lhv_oil + char_kg_d*lhv_char + gas_kg_d*lhv_gas) / 3.6
process_heat_kwh_d    = dry_kg_d * cp_kj_kg_k * delta_t_k / 3600 + drying_kwh_d
                        [cp=1.5 kJ/kg·K, dT=450 K default; drying counted in process heat]
e_net_energy_kwh_d    = product_energy_kwh_d - process_heat_kwh_d
                        [thermal basis only — electricity conversion not modelled here]
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from .feedstock import Feedstock

# ---------------------------------------------------------------------------
# LHV constants — ILLUSTRATIVE, not validated plant data
# ---------------------------------------------------------------------------

_LHV_OIL_MJ_KG: float = 40.0   # MJ/kg pyrolysis oil — ILLUSTRATIVE
_LHV_CHAR_MJ_KG: float = 25.0  # MJ/kg char — ILLUSTRATIVE
_LHV_GAS_MJ_KG: float = 15.0   # MJ/kg pyrolysis gas — ILLUSTRATIVE


# ---------------------------------------------------------------------------
# Parameter dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PyrolysisParams:
    """Parameters for the pyrolysis pathway model.

    All defaults are ILLUSTRATIVE — replace with reactor/feedstock-specific data.

    Parameters
    ----------
    oil_yield:
        Mass fraction of dry feed converted to pyrolysis oil.  Default 0.40.
    char_yield:
        Mass fraction of dry feed converted to char.  Default 0.30.
    gas_yield:
        Mass fraction of dry feed converted to non-condensable gas.  Default 0.30.
        ``oil_yield + char_yield + gas_yield`` must equal 1.0 (tolerance 1e-6).
    cp_kj_kg_k:
        Heat capacity of dry feedstock (kJ/kg·K).  Default 1.5.
    delta_t_k:
        Temperature rise from ambient to pyrolysis temperature (K).  Default 450.
    target_moisture:
        Maximum moisture fraction accepted without pre-drying (wet basis).
        Default 0.20.
    """

    oil_yield: float = 0.40
    char_yield: float = 0.30
    gas_yield: float = 0.30
    cp_kj_kg_k: float = 1.5
    delta_t_k: float = 450.0
    target_moisture: float = 0.20

    def __post_init__(self) -> None:
        for name, val in (
            ("oil_yield", self.oil_yield),
            ("char_yield", self.char_yield),
            ("gas_yield", self.gas_yield),
        ):
            if not (0.0 <= val <= 1.0):
                raise ValueError(f"{name} must be in [0, 1]; got {val}")

        total = self.oil_yield + self.char_yield + self.gas_yield
        if abs(total - 1.0) > 1e-6:
            raise ValueError(
                f"oil_yield + char_yield + gas_yield must sum to 1.0; "
                f"got {total:.8f}"
            )
        if self.cp_kj_kg_k < 0:
            raise ValueError(
                f"cp_kj_kg_k must be >= 0; got {self.cp_kj_kg_k}"
            )
        if self.delta_t_k < 0:
            raise ValueError(
                f"delta_t_k must be >= 0; got {self.delta_t_k}"
            )
        if not (0.0 <= self.target_moisture < 1.0):
            raise ValueError(
                f"target_moisture must be in [0, 1); got {self.target_moisture}"
            )


# ---------------------------------------------------------------------------
# Simulation function
# ---------------------------------------------------------------------------

def simulate_pyrolysis(
    feedstock: Feedstock,
    params: PyrolysisParams = PyrolysisParams(),
) -> Dict[str, Any]:
    """Run the pyrolysis product-energy and process-heat model.

    Parameters
    ----------
    feedstock:
        A validated :class:`~feedstock.Feedstock` instance.
    params:
        Pyrolysis model parameters.  Defaults to :class:`PyrolysisParams`.

    Returns
    -------
    dict
        Keys: dry_kg_d, drying_kwh_d, oil_kg_d, char_kg_d, gas_kg_d,
        product_energy_kwh_d, process_heat_kwh_d, e_net_energy_kwh_d,
        warnings (list[str]), status (str).
        All numeric values are plain Python floats.
    """
    if feedstock.total_mass_kg_d < 0:
        raise ValueError(
            f"feedstock.total_mass_kg_d must be >= 0; got {feedstock.total_mass_kg_d}"
        )

    M: float = feedstock.total_mass_kg_d
    w: float = feedstock.moisture_fraction

    dry_kg_d: float = M * (1.0 - w)

    # Drying load (same formula as gasification)
    water_in_feed: float = M * w
    if w > params.target_moisture:
        dry_mass: float = M * (1.0 - w)
        water_at_target: float = dry_mass * params.target_moisture / (1.0 - params.target_moisture)
        moisture_to_remove: float = water_in_feed - water_at_target
    else:
        moisture_to_remove = 0.0

    drying_kwh_d: float = moisture_to_remove * 2.26 / 3.6

    # Product yields (applied to dry feed mass)
    oil_kg_d: float = dry_kg_d * params.oil_yield
    char_kg_d: float = dry_kg_d * params.char_yield
    gas_kg_d: float = dry_kg_d * params.gas_yield

    product_energy_kwh_d: float = (
        oil_kg_d * _LHV_OIL_MJ_KG
        + char_kg_d * _LHV_CHAR_MJ_KG
        + gas_kg_d * _LHV_GAS_MJ_KG
    ) / 3.6

    # Process heat = sensible heating of dry feedstock + drying
    process_heat_kwh_d: float = (
        dry_kg_d * params.cp_kj_kg_k * params.delta_t_k / 3600.0
        + drying_kwh_d
    )

    e_net_energy_kwh_d: float = product_energy_kwh_d - process_heat_kwh_d

    warnings: List[str] = []
    if w > params.target_moisture:
        warnings.append(
            f"moisture {w:.4g} exceeds target {params.target_moisture:.4g}; "
            f"electric pre-drying assumed ({drying_kwh_d:.4g} kWh/d)"
        )
    if e_net_energy_kwh_d <= 0:
        warnings.append(
            f"e_net_energy_kwh_d {e_net_energy_kwh_d:.4g} <= 0; feedstock may be "
            "too wet or have insufficient chemical energy for net-positive pyrolysis"
        )

    return {
        "dry_kg_d": dry_kg_d,
        "drying_kwh_d": drying_kwh_d,
        "oil_kg_d": oil_kg_d,
        "char_kg_d": char_kg_d,
        "gas_kg_d": gas_kg_d,
        "product_energy_kwh_d": product_energy_kwh_d,
        "process_heat_kwh_d": process_heat_kwh_d,
        "e_net_energy_kwh_d": e_net_energy_kwh_d,
        "warnings": warnings,
        "status": "illustrative_estimate",
    }
