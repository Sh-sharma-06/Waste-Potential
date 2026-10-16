"""Gasification pathway model — syngas energy balance.

All default parameter values are ILLUSTRATIVE, not validated plant data.
Units: kg/d (mass flows), kWh/d (energy), wet-basis mass unless noted.

Formulae
--------
dry_kg_d            = M * (1 - moisture_fraction)
moisture_to_remove  = max(0, M * moisture_fraction - M * target_moisture)
                      [kg/d of water that must be removed before gasification]
drying_kwh_d        = moisture_to_remove * 2.26 / 3.6
                      [assumed electric drying; 2.26 MJ/kg latent heat of evaporation]
syngas_energy_kwh_d = dry_kg_d * lhv_dry_mj_per_kg / 3.6 * cold_gas_efficiency
e_gross_kwh_d       = syngas_energy_kwh_d * eta_engine
aux_kwh_d           = aux_kwh_per_t * M / 1000
e_net_kwh_d         = e_gross_kwh_d - aux_kwh_d - drying_kwh_d
char_kg_d           = dry_kg_d * ash_fraction_dry * 1.5   [illustrative; includes
                      residual carbon; 1.5 factor is MODEL ASSUMPTION]
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from .feedstock import Feedstock


# ---------------------------------------------------------------------------
# Parameter dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GasificationParams:
    """Parameters for the gasification pathway model.

    All defaults are ILLUSTRATIVE — replace with plant-specific data.

    Parameters
    ----------
    cold_gas_efficiency:
        Fraction of the dry feedstock's chemical energy transferred to syngas
        (cold-gas efficiency, dimensionless).  Default 0.70.
    eta_engine:
        Engine/turbine electrical efficiency applied to syngas energy.
        Default 0.30.
    aux_kwh_per_t:
        Parasitic electricity for fans, controls, gas clean-up, etc.
        (kWh per tonne wet input).  Default 100.
    target_moisture:
        Maximum moisture fraction the gasifier can accept (wet basis).
        Feedstock is electrically dried to this level when wetter.  Default 0.15.
    """

    cold_gas_efficiency: float = 0.70
    eta_engine: float = 0.30
    aux_kwh_per_t: float = 100.0
    target_moisture: float = 0.15

    def __post_init__(self) -> None:
        if not (0.0 < self.cold_gas_efficiency <= 1.0):
            raise ValueError(
                f"cold_gas_efficiency must be in (0, 1]; got {self.cold_gas_efficiency}"
            )
        if not (0.0 < self.eta_engine <= 1.0):
            raise ValueError(
                f"eta_engine must be in (0, 1]; got {self.eta_engine}"
            )
        if self.aux_kwh_per_t < 0:
            raise ValueError(
                f"aux_kwh_per_t must be >= 0; got {self.aux_kwh_per_t}"
            )
        if not (0.0 <= self.target_moisture < 1.0):
            raise ValueError(
                f"target_moisture must be in [0, 1); got {self.target_moisture}"
            )


# ---------------------------------------------------------------------------
# Simulation function
# ---------------------------------------------------------------------------

def simulate_gasification(
    feedstock: Feedstock,
    params: GasificationParams = GasificationParams(),
) -> Dict[str, Any]:
    """Run the gasification mass-balance and energy model.

    Parameters
    ----------
    feedstock:
        A validated :class:`~feedstock.Feedstock` instance.
    params:
        Gasification model parameters.  Defaults to :class:`GasificationParams`.

    Returns
    -------
    dict
        Keys: dry_kg_d, drying_kwh_d, syngas_energy_kwh_d, e_gross_kwh_d,
        aux_kwh_d, e_net_kwh_d, char_kg_d, warnings (list[str]),
        status (str).  All numeric values are plain Python floats.
    """
    if feedstock.total_mass_kg_d < 0:
        raise ValueError(
            f"feedstock.total_mass_kg_d must be >= 0; got {feedstock.total_mass_kg_d}"
        )

    M: float = feedstock.total_mass_kg_d
    w: float = feedstock.moisture_fraction

    dry_kg_d: float = M * (1.0 - w)

    # Drying load — remove moisture down to target (assumed electric)
    # moisture_to_remove = max(0, water_in_feed - water_at_target_moisture)
    # water_at_target = (M - water_in_feed) * target / (1 - target)
    water_in_feed: float = M * w
    if w > params.target_moisture:
        dry_mass: float = M * (1.0 - w)
        water_at_target: float = dry_mass * params.target_moisture / (1.0 - params.target_moisture)
        moisture_to_remove: float = water_in_feed - water_at_target
    else:
        moisture_to_remove = 0.0

    drying_kwh_d: float = moisture_to_remove * 2.26 / 3.6

    syngas_energy_kwh_d: float = (
        dry_kg_d * feedstock.lhv_dry_mj_per_kg / 3.6 * params.cold_gas_efficiency
    )
    e_gross_kwh_d: float = syngas_energy_kwh_d * params.eta_engine
    aux_kwh_d: float = params.aux_kwh_per_t * M / 1000.0
    e_net_kwh_d: float = e_gross_kwh_d - aux_kwh_d - drying_kwh_d

    char_kg_d: float = dry_kg_d * feedstock.ash_fraction_dry * 1.5

    warnings: List[str] = []
    if w > params.target_moisture:
        warnings.append(
            f"moisture {w:.4g} exceeds target {params.target_moisture:.4g}; "
            f"electric pre-drying assumed ({drying_kwh_d:.4g} kWh/d)"
        )
    if e_net_kwh_d <= 0:
        warnings.append(
            f"e_net_kwh_d {e_net_kwh_d:.4g} <= 0; feedstock energy content "
            "may be insufficient for net-positive gasification"
        )

    return {
        "dry_kg_d": dry_kg_d,
        "drying_kwh_d": drying_kwh_d,
        "syngas_energy_kwh_d": syngas_energy_kwh_d,
        "e_gross_kwh_d": e_gross_kwh_d,
        "aux_kwh_d": aux_kwh_d,
        "e_net_kwh_d": e_net_kwh_d,
        "char_kg_d": char_kg_d,
        "warnings": warnings,
        "status": "illustrative_estimate",
    }
