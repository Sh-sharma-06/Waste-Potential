"""Hydrothermal Carbonisation (HTC) pathway model.

All default parameter values are ILLUSTRATIVE — source: blueprint catalog (unvalidated).
Units: kg/d (mass flows), kWh/d (energy), wet-basis mass unless noted.
This model operates on a thermal (chemical energy) basis, not electricity.

Mass basis (per kg wet feed):
    hydrochar_dry_kg_per_kg  = 0.135   (dry hydrochar yield)
    hhv_mj_per_kg            = 20.0    (HHV of hydrochar, MJ/kg dry)
    heat_kwh_per_kg          = 0.158   (process heat, kWh/kg wet feed)
    aux_kwh_per_kg           = 0.028   (0.005 sorting + 0.006 press +
                                        0.012 pellet + 0.005 dosing)
    gas_fraction             = 0.05    (dissolved/non-condensable gas yield,
                                        ILLUSTRATIVE named constant)
    cp_kj_kg_k               = 4.0    (effective heat capacity of slurry,
                                        kJ/kg·K, ILLUSTRATIVE)
    reactor_temp_c           = 220.0   (reactor temperature, °C, ILLUSTRATIVE)
    feed_temp_c              = 25.0    (feed inlet temperature, °C, ILLUSTRATIVE)
    heat_recovery_fraction   = 0.60    (fraction of reactor heat recovered,
                                        ILLUSTRATIVE)

Formulae:
    hydrochar_kg_d           = M * hydrochar_dry_kg_per_kg
    hydrochar_energy_kwh_d   = hydrochar_kg_d * hhv_mj_per_kg / 3.6
    heat_kwh_d               = M * heat_kwh_per_kg
    aux_kwh_d                = M * aux_kwh_per_kg
    e_net_energy_kwh_d       = hydrochar_energy_kwh_d - heat_kwh_d - aux_kwh_d

    gas_kg_d                 = M * _HTC_GAS_FRACTION
    water_out_kg_d           = M - hydrochar_kg_d - gas_kg_d
        (simplified mass closure: all remaining mass leaves as process water)
    reactor_heat_kwh_d       = M * cp_kj_kg_k * (reactor_temp_c - feed_temp_c)
                               / 3600 * (1 - heat_recovery_fraction)

Feasibility (MODEL ASSUMPTION, not a universal limit):
    moisture_fraction >= 0.50
    organic_fraction  >= 0.50
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from .feedstock import Feedstock

# ---------------------------------------------------------------------------
# HTC threshold constants — MODEL ASSUMPTION, not a universal limit
# ---------------------------------------------------------------------------

_HTC_MIN_MOISTURE: float = 0.50   # MODEL ASSUMPTION, not a universal limit
_HTC_MIN_ORGANIC: float = 0.50    # MODEL ASSUMPTION, not a universal limit
_HTC_GAS_FRACTION: float = 0.05   # illustrative non-condensable gas yield (kg/kg wet)

# ---------------------------------------------------------------------------
# Parameter dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HTCParams:
    """Parameters for the HTC pathway model.

    All defaults are ILLUSTRATIVE — source: blueprint catalog (unvalidated).

    Parameters
    ----------
    hydrochar_dry_kg_per_kg:
        Dry hydrochar yield per kg wet feed.  Default 0.135.
    hhv_mj_per_kg:
        Higher heating value of dry hydrochar (MJ/kg).  Default 20.0.
    heat_kwh_per_kg:
        Process heat demand per kg wet feed (kWh/kg).  Default 0.158.
    aux_sort_kwh_per_kg:
        Auxiliary electricity for sorting (kWh/kg).  Default 0.005.
    aux_press_kwh_per_kg:
        Auxiliary electricity for pressing (kWh/kg).  Default 0.006.
    aux_pellet_kwh_per_kg:
        Auxiliary electricity for pelletising (kWh/kg).  Default 0.012.
    aux_dosing_kwh_per_kg:
        Auxiliary electricity for dosing (kWh/kg).  Default 0.005.
    cp_kj_kg_k:
        Effective heat capacity of the reaction slurry (kJ/kg·K).  Default 4.0.
    reactor_temp_c:
        Reactor operating temperature (°C).  Default 220.0.
    feed_temp_c:
        Feed inlet temperature (°C).  Default 25.0.  Must be < reactor_temp_c.
    heat_recovery_fraction:
        Fraction of reactor sensible heat recovered and reused [0, 1].  Default 0.60.
    """

    hydrochar_dry_kg_per_kg: float = 0.135
    hhv_mj_per_kg: float = 20.0
    heat_kwh_per_kg: float = 0.158
    aux_sort_kwh_per_kg: float = 0.005
    aux_press_kwh_per_kg: float = 0.006
    aux_pellet_kwh_per_kg: float = 0.012
    aux_dosing_kwh_per_kg: float = 0.005
    cp_kj_kg_k: float = 4.0
    reactor_temp_c: float = 220.0
    feed_temp_c: float = 25.0
    heat_recovery_fraction: float = 0.60

    def __post_init__(self) -> None:
        for attr in (
            "hydrochar_dry_kg_per_kg",
            "hhv_mj_per_kg",
            "heat_kwh_per_kg",
            "aux_sort_kwh_per_kg",
            "aux_press_kwh_per_kg",
            "aux_pellet_kwh_per_kg",
            "aux_dosing_kwh_per_kg",
            "cp_kj_kg_k",
        ):
            val = getattr(self, attr)
            if val < 0:
                raise ValueError(f"{attr} must be >= 0; got {val}")
        if not (0.0 <= self.heat_recovery_fraction <= 1.0):
            raise ValueError(
                f"heat_recovery_fraction must be in [0, 1]; "
                f"got {self.heat_recovery_fraction}"
            )
        if self.reactor_temp_c <= self.feed_temp_c:
            raise ValueError(
                f"reactor_temp_c ({self.reactor_temp_c}) must be greater than "
                f"feed_temp_c ({self.feed_temp_c})"
            )


# ---------------------------------------------------------------------------
# Simulation function
# ---------------------------------------------------------------------------


def simulate_htc(
    feedstock: Feedstock,
    params: HTCParams = HTCParams(),
) -> Dict[str, Any]:
    """Run the HTC hydrochar-energy and process-heat model.

    Parameters
    ----------
    feedstock:
        A validated :class:`~feedstock.Feedstock` instance.
    params:
        HTC model parameters.  Defaults to :class:`HTCParams`.

    Returns
    -------
    dict
        Keys (all per-day, wet-mass basis unless noted):

        Existing keys (unchanged):
            hydrochar_kg_d          — dry hydrochar mass (kg/d)
            hydrochar_energy_kwh_d  — chemical energy in hydrochar (kWh/d)
            heat_kwh_d              — catalogue process-heat demand (kWh/d)
            aux_kwh_d               — total auxiliary electricity (kWh/d)
            e_net_energy_kwh_d      — net thermal energy (kWh/d)

        New keys:
            gas_kg_d                — non-condensable gas mass (kg/d)
            water_out_kg_d          — process-water output by mass closure
                                      = M - hydrochar_kg_d - gas_kg_d (kg/d)
            reactor_heat_kwh_d      — sensible reactor heat after recovery
                                      = M*cp*(T_reactor-T_feed)/3600
                                        *(1-heat_recovery_fraction) (kWh/d)

        warnings (list[str]), status (str).
        All numeric values are plain Python floats.
    """
    if feedstock.total_mass_kg_d < 0:
        raise ValueError(
            f"feedstock.total_mass_kg_d must be >= 0; got {feedstock.total_mass_kg_d}"
        )

    M: float = feedstock.total_mass_kg_d

    # --- existing energy balance (values unchanged) -------------------------
    hydrochar_kg_d: float = M * params.hydrochar_dry_kg_per_kg
    hydrochar_energy_kwh_d: float = hydrochar_kg_d * params.hhv_mj_per_kg / 3.6
    heat_kwh_d: float = M * params.heat_kwh_per_kg
    aux_kwh_per_kg: float = (
        params.aux_sort_kwh_per_kg
        + params.aux_press_kwh_per_kg
        + params.aux_pellet_kwh_per_kg
        + params.aux_dosing_kwh_per_kg
    )
    aux_kwh_d: float = M * aux_kwh_per_kg
    e_net_energy_kwh_d: float = hydrochar_energy_kwh_d - heat_kwh_d - aux_kwh_d

    # --- new: mass closure --------------------------------------------------
    gas_kg_d: float = M * _HTC_GAS_FRACTION
    water_out_kg_d: float = M - hydrochar_kg_d - gas_kg_d

    # --- new: reactor sensible heat -----------------------------------------
    reactor_heat_kwh_d: float = (
        M
        * params.cp_kj_kg_k
        * (params.reactor_temp_c - params.feed_temp_c)
        / 3600.0
        * (1.0 - params.heat_recovery_fraction)
    )

    # --- warnings -----------------------------------------------------------
    warnings: List[str] = []
    if e_net_energy_kwh_d <= 0:
        warnings.append(
            f"e_net_energy_kwh_d {e_net_energy_kwh_d:.4g} <= 0; feedstock may "
            "have insufficient chemical energy for net-positive HTC"
        )
    if water_out_kg_d < 0:
        warnings.append(
            f"water_out_kg_d {water_out_kg_d:.4g} < 0; hydrochar + gas yields "
            "exceed total feed mass — check parameters"
        )
    if heat_kwh_d > 0:
        ratio = abs(reactor_heat_kwh_d - heat_kwh_d) / heat_kwh_d
        if ratio > 0.50:
            warnings.append(
                f"reactor_heat_kwh_d {reactor_heat_kwh_d:.4g} and heat_kwh_d "
                f"{heat_kwh_d:.4g} differ by {ratio*100:.1f}% (> 50%); "
                "verify reactor and catalogue heat parameters"
            )

    return {
        "hydrochar_kg_d": hydrochar_kg_d,
        "hydrochar_energy_kwh_d": hydrochar_energy_kwh_d,
        "heat_kwh_d": heat_kwh_d,
        "aux_kwh_d": aux_kwh_d,
        "e_net_energy_kwh_d": e_net_energy_kwh_d,
        "gas_kg_d": gas_kg_d,
        "water_out_kg_d": water_out_kg_d,
        "reactor_heat_kwh_d": reactor_heat_kwh_d,
        "warnings": warnings,
        "status": "illustrative_estimate",
    }
