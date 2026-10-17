"""Torrefaction pathway model.

All default parameter values are ILLUSTRATIVE — source: blueprint catalog (unvalidated).
Units: kg/d (mass flows), kWh/d (energy), wet-basis mass unless noted.
This model operates on a thermal (chemical energy) basis, not electricity.

Formulae (per kg wet feed):
    pellet_kg_per_kg       = 0.633   (torrefied-pellet yield)
    hhv_mj_per_kg          = 19.7    (HHV of torrefied pellets, MJ/kg)
    dryer_heat_kwh_per_kg  = 0.0349  (dryer heat demand, kWh/kg wet feed)
    aux_kwh_per_kg         = 0.0269  (0.005 sorting + 0.018 grind/dry +
                                       0.0209 torr+pellet + 0.003 packaging)
    mass_yield             = 0.70    (torrefied solid yield, kg dry solid
                                       per kg dry feed, ILLUSTRATIVE)
    target_moisture        = 0.10    (target moisture for pre-drying,
                                       ILLUSTRATIVE)

    pellets_kg_d           = M * pellet_kg_per_kg
    pellet_energy_kwh_d    = pellets_kg_d * hhv_mj_per_kg / 3.6
    dryer_heat_kwh_d       = M * dryer_heat_kwh_per_kg
    aux_kwh_d              = M * aux_kwh_per_kg
    e_net_energy_kwh_d     = pellet_energy_kwh_d - dryer_heat_kwh_d - aux_kwh_d

    dry_feed_kg_d          = M * (1 - moisture_fraction)
    torrefied_solid_kg_d   = dry_feed_kg_d * mass_yield

    water_to_remove_kg     = M * (moisture - target_moisture) /
                             (1 - target_moisture)  if moisture > target_moisture
                             else 0
    predry_energy_kwh_d    = water_to_remove_kg * 2.26 / 3.6
                             [latent heat of evaporation 2.26 MJ/kg]

    pellet_energy_density_mj_per_kg = hhv_mj_per_kg  (identical to params field)

    energy_yield_fraction  = pellet_energy_kwh_d /
                             (dry_feed_kg_d * lhv_dry_mj_per_kg / 3.6)
                             only computed when lhv_dry_mj_per_kg is supplied
                             (optional argument); key omitted when None.

Feasibility (MODEL ASSUMPTION, not a universal limit):
    moisture_fraction         <= 0.50
    lignocellulosic_fraction  >= 0.60
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .feedstock import Feedstock

# ---------------------------------------------------------------------------
# Torrefaction thresholds — MODEL ASSUMPTION, not a universal limit
# ---------------------------------------------------------------------------

_TORR_MAX_MOISTURE: float = 0.50   # MODEL ASSUMPTION, not a universal limit
_TORR_MIN_ORGANIC: float = 0.30    # MODEL ASSUMPTION, not a universal limit (retained for import compat)
_TORR_MIN_LIGNOCELLULOSIC: float = 0.60  # MODEL ASSUMPTION, not a universal limit

# ---------------------------------------------------------------------------
# Parameter dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TorrefactionParams:
    """Parameters for the torrefaction pathway model.

    All defaults are ILLUSTRATIVE — source: blueprint catalog (unvalidated).

    Parameters
    ----------
    pellet_kg_per_kg:
        Torrefied-pellet yield per kg wet feed.  Default 0.633.
    hhv_mj_per_kg:
        Higher heating value of torrefied pellets (MJ/kg).  Default 19.7.
    dryer_heat_kwh_per_kg:
        Dryer heat demand per kg wet feed (kWh/kg).  Default 0.0349.
    aux_sort_kwh_per_kg:
        Auxiliary electricity for sorting (kWh/kg).  Default 0.005.
    aux_grind_dry_kwh_per_kg:
        Auxiliary electricity for grinding/drying (kWh/kg).  Default 0.018.
    aux_torr_pellet_kwh_per_kg:
        Auxiliary electricity for torrefaction and pelletising (kWh/kg).  Default 0.0209.
    aux_packaging_kwh_per_kg:
        Auxiliary electricity for packaging (kWh/kg).  Default 0.003.
    mass_yield:
        Torrefied solid yield (kg dry torrefied solid per kg dry feed).
        Default 0.70.  Must be in [0, 1].
    target_moisture:
        Target moisture fraction for pre-drying (wet basis).  Default 0.10.
        Feeds drier than this skip pre-drying (predry_energy_kwh_d = 0).
        Must be in [0, 1).
    """

    pellet_kg_per_kg: float = 0.633
    hhv_mj_per_kg: float = 19.7
    dryer_heat_kwh_per_kg: float = 0.0349
    aux_sort_kwh_per_kg: float = 0.005
    aux_grind_dry_kwh_per_kg: float = 0.018
    aux_torr_pellet_kwh_per_kg: float = 0.0209
    aux_packaging_kwh_per_kg: float = 0.003
    mass_yield: float = 0.70
    target_moisture: float = 0.10

    def __post_init__(self) -> None:
        for attr in (
            "pellet_kg_per_kg",
            "hhv_mj_per_kg",
            "dryer_heat_kwh_per_kg",
            "aux_sort_kwh_per_kg",
            "aux_grind_dry_kwh_per_kg",
            "aux_torr_pellet_kwh_per_kg",
            "aux_packaging_kwh_per_kg",
        ):
            val = getattr(self, attr)
            if val < 0:
                raise ValueError(f"{attr} must be >= 0; got {val}")
        if not (0.0 <= self.mass_yield <= 1.0):
            raise ValueError(
                f"mass_yield must be in [0, 1]; got {self.mass_yield}"
            )
        if not (0.0 <= self.target_moisture < 1.0):
            raise ValueError(
                f"target_moisture must be in [0, 1); got {self.target_moisture}"
            )


# ---------------------------------------------------------------------------
# Simulation function
# ---------------------------------------------------------------------------


def simulate_torrefaction(
    feedstock: Feedstock,
    params: TorrefactionParams = TorrefactionParams(),
    lhv_dry_mj_per_kg: Optional[float] = None,
) -> Dict[str, Any]:
    """Run the torrefaction pellet-energy and process-heat model.

    Parameters
    ----------
    feedstock:
        A validated :class:`~feedstock.Feedstock` instance.
    params:
        Torrefaction model parameters.  Defaults to :class:`TorrefactionParams`.
    lhv_dry_mj_per_kg:
        Lower heating value of the dry feedstock (MJ/kg dry), used to compute
        ``energy_yield_fraction``.  When ``None`` (default) the key is omitted
        from the returned dict.

    Returns
    -------
    dict
        Keys (all per-day, wet-mass basis unless noted):

        Existing keys (unchanged):
            pellets_kg_d                — torrefied pellet mass (kg/d)
            pellet_energy_kwh_d         — chemical energy in pellets (kWh/d)
            dryer_heat_kwh_d            — catalogue dryer-heat demand (kWh/d)
            aux_kwh_d                   — total auxiliary electricity (kWh/d)
            e_net_energy_kwh_d          — net thermal energy (kWh/d)

        New keys (always present):
            dry_feed_kg_d               — dry feed mass (kg/d)
            torrefied_solid_kg_d        — dry torrefied solid by mass yield
                                          = dry_feed_kg_d * mass_yield (kg/d)
            predry_energy_kwh_d         — latent heat for pre-drying to
                                          target_moisture (kWh/d); 0 if already dry
            pellet_energy_density_mj_per_kg — HHV of pellets (MJ/kg),
                                          identical to params.hhv_mj_per_kg

        Optional key (present only when lhv_dry_mj_per_kg is not None):
            energy_yield_fraction       — pellet_energy / feed_chemical_energy
                                          (dimensionless)

        warnings (list[str]), status (str).
        All numeric values are plain Python floats.
    """
    if feedstock.total_mass_kg_d < 0:
        raise ValueError(
            f"feedstock.total_mass_kg_d must be >= 0; got {feedstock.total_mass_kg_d}"
        )

    M: float = feedstock.total_mass_kg_d
    w: float = feedstock.moisture_fraction

    # --- existing energy balance (values unchanged) -------------------------
    pellets_kg_d: float = M * params.pellet_kg_per_kg
    pellet_energy_kwh_d: float = pellets_kg_d * params.hhv_mj_per_kg / 3.6
    dryer_heat_kwh_d: float = M * params.dryer_heat_kwh_per_kg
    aux_kwh_per_kg: float = (
        params.aux_sort_kwh_per_kg
        + params.aux_grind_dry_kwh_per_kg
        + params.aux_torr_pellet_kwh_per_kg
        + params.aux_packaging_kwh_per_kg
    )
    aux_kwh_d: float = M * aux_kwh_per_kg
    e_net_energy_kwh_d: float = pellet_energy_kwh_d - dryer_heat_kwh_d - aux_kwh_d

    # --- new: dry feed and torrefied solid ----------------------------------
    dry_feed_kg_d: float = M * (1.0 - w)
    torrefied_solid_kg_d: float = dry_feed_kg_d * params.mass_yield

    # --- new: pre-drying energy (latent heat basis) -------------------------
    if w > params.target_moisture:
        water_to_remove: float = (
            M * (w - params.target_moisture) / (1.0 - params.target_moisture)
        )
    else:
        water_to_remove = 0.0
    predry_energy_kwh_d: float = water_to_remove * 2.26 / 3.6

    # --- new: pellet energy density (mirrors existing HHV param) ------------
    pellet_energy_density_mj_per_kg: float = params.hhv_mj_per_kg

    # --- warnings -----------------------------------------------------------
    warnings: List[str] = []
    if e_net_energy_kwh_d <= 0:
        warnings.append(
            f"e_net_energy_kwh_d {e_net_energy_kwh_d:.4g} <= 0; feedstock may "
            "have insufficient chemical energy for net-positive torrefaction"
        )
    if dryer_heat_kwh_d > 0:
        ratio = abs(predry_energy_kwh_d - dryer_heat_kwh_d) / dryer_heat_kwh_d
        if ratio > 0.50:
            warnings.append(
                f"predry_energy_kwh_d {predry_energy_kwh_d:.4g} and "
                f"dryer_heat_kwh_d {dryer_heat_kwh_d:.4g} differ by "
                f"{ratio*100:.1f}% (> 50%); verify drying parameters"
            )

    # --- base result dict ---------------------------------------------------
    result: Dict[str, Any] = {
        "pellets_kg_d": pellets_kg_d,
        "pellet_energy_kwh_d": pellet_energy_kwh_d,
        "dryer_heat_kwh_d": dryer_heat_kwh_d,
        "aux_kwh_d": aux_kwh_d,
        "e_net_energy_kwh_d": e_net_energy_kwh_d,
        "dry_feed_kg_d": dry_feed_kg_d,
        "torrefied_solid_kg_d": torrefied_solid_kg_d,
        "predry_energy_kwh_d": predry_energy_kwh_d,
        "pellet_energy_density_mj_per_kg": pellet_energy_density_mj_per_kg,
        "warnings": warnings,
        "status": "illustrative_estimate",
    }

    # --- optional: energy yield fraction ------------------------------------
    if lhv_dry_mj_per_kg is not None:
        feed_energy_kwh_d: float = dry_feed_kg_d * lhv_dry_mj_per_kg / 3.6
        if feed_energy_kwh_d > 0:
            result["energy_yield_fraction"] = pellet_energy_kwh_d / feed_energy_kwh_d
        else:
            result["energy_yield_fraction"] = 0.0

    return result
