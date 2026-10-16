"""Incineration pathway model — mass balance, energy output, and fossil CO2.

All default parameter values are ILLUSTRATIVE, not validated plant data.
Units: kg/d (mass flows), kWh/d (energy), wet-basis mass unless noted.

Formulae
--------
lhv_wet          = feedstock.lhv_wet_mj_per_kg()          [MJ/kg wet, floored at 0]
e_thermal_kwh_d  = M * lhv_wet / 3.6                      [MJ → kWh: divide by 3.6]
e_gross_kwh_d    = e_thermal_kwh_d * eta_el
aux_kwh_d        = aux_kwh_per_t * M / 1000
e_net_kwh_d      = e_gross_kwh_d - aux_kwh_d
ash_kg_d         = M * (1 - moisture_fraction) * ash_fraction_dry
co2_fossil_kg_d  = M * plastic_fraction * carbon_content_plastic * (44/12)
                   [stoichiometric CO2 from complete combustion of plastic carbon]
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from .feedstock import Feedstock


# ---------------------------------------------------------------------------
# Parameter dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class IncinerationParams:
    """Parameters for the incineration pathway model.

    All default values are ILLUSTRATIVE — replace with site-specific data.

    Parameters
    ----------
    eta_el:
        Net electrical efficiency of the energy-from-waste boiler + turbine
        (fraction of thermal input recovered as electricity).  Default 0.22.
    aux_kwh_per_t:
        Parasitic electricity for fans, conveyors, flue-gas treatment, etc.
        (kWh per tonne wet input).  Default 70.
    carbon_content_plastic:
        Mass fraction of carbon in the plastic fraction (kg C / kg plastic).
        Default 0.75.
    """

    eta_el: float = 0.22
    aux_kwh_per_t: float = 70.0
    carbon_content_plastic: float = 0.75

    def __post_init__(self) -> None:
        if not (0.0 < self.eta_el <= 1.0):
            raise ValueError(
                f"eta_el must be in (0, 1]; got {self.eta_el}"
            )
        if self.aux_kwh_per_t < 0:
            raise ValueError(
                f"aux_kwh_per_t must be >= 0; got {self.aux_kwh_per_t}"
            )
        if not (0.0 <= self.carbon_content_plastic <= 1.0):
            raise ValueError(
                f"carbon_content_plastic must be in [0, 1]; got {self.carbon_content_plastic}"
            )


# ---------------------------------------------------------------------------
# Simulation function
# ---------------------------------------------------------------------------

def simulate_incineration(
    feedstock: Feedstock,
    params: IncinerationParams = IncinerationParams(),
) -> Dict[str, Any]:
    """Run the incineration mass-balance and energy model.

    Parameters
    ----------
    feedstock:
        A validated :class:`~feedstock.Feedstock` instance.
    params:
        Incineration model parameters.  Defaults to :class:`IncinerationParams`.

    Returns
    -------
    dict
        Keys: e_thermal_kwh_d, e_gross_kwh_d, aux_kwh_d, e_net_kwh_d,
        ash_kg_d, co2_fossil_kg_d, warnings (list[str]), status (str).
        All numeric values are plain Python floats.
    """
    if feedstock.total_mass_kg_d < 0:
        raise ValueError(
            f"feedstock.total_mass_kg_d must be >= 0; got {feedstock.total_mass_kg_d}"
        )

    M: float = feedstock.total_mass_kg_d
    lhv_wet: float = feedstock.lhv_wet_mj_per_kg()

    e_thermal_kwh_d: float = M * lhv_wet / 3.6
    e_gross_kwh_d: float = e_thermal_kwh_d * params.eta_el
    aux_kwh_d: float = params.aux_kwh_per_t * M / 1000.0
    e_net_kwh_d: float = e_gross_kwh_d - aux_kwh_d

    ash_kg_d: float = M * (1.0 - feedstock.moisture_fraction) * feedstock.ash_fraction_dry
    co2_fossil_kg_d: float = (
        M * feedstock.plastic_fraction * params.carbon_content_plastic * (44.0 / 12.0)
    )

    warnings: List[str] = []
    if e_net_kwh_d <= 0:
        warnings.append(
            f"e_net_kwh_d {e_net_kwh_d:.4g} <= 0; feedstock energy content "
            "may be too low for net-positive power generation"
        )

    return {
        "e_thermal_kwh_d": e_thermal_kwh_d,
        "e_gross_kwh_d": e_gross_kwh_d,
        "aux_kwh_d": aux_kwh_d,
        "e_net_kwh_d": e_net_kwh_d,
        "ash_kg_d": ash_kg_d,
        "co2_fossil_kg_d": co2_fossil_kg_d,
        "warnings": warnings,
        "status": "illustrative_estimate",
    }
