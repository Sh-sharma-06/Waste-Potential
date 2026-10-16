"""weather.py — Weather context and moisture/drying adjustments for pathway models.

All formulas and sensitivity values are ILLUSTRATIVE — source=TBD, status="illustrative".
Pure functions: no file, network, or DB access.

Units
-----
ambient_temp_c          °C         (may be negative)
relative_humidity       fraction   [0, 1]
rainfall_mm_d           mm / day   >= 0
moisture_fraction       fraction   wet basis  [0, 1)
drying_energy_kwh_d     kWh / day
mass_kg_d               kg / day

Moisture adjustment formula (MODEL ASSUMPTION, not validated)
-------------------------------------------------------------
    delta = sensitivity * max(rainfall_mm_d / 10, 0)
    new_moisture = min(old_moisture + delta, 0.95)

Drying energy formula
---------------------
    Latent heat of vaporisation of water at 25 °C: 2.26 MJ/kg
    moisture_to_remove_kg_d = mass_kg_d * (moisture_from - moisture_to)
                              / (1 - moisture_to)
        [solids-conserving formula: same water removal approach used in
         gasification.py and pyrolysis.py]
    drying_energy_kwh_d = moisture_to_remove_kg_d * 2.26 / 3.6
    Returns 0.0 when moisture_from <= moisture_to (no drying needed).
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Tuple

from .feedstock import Feedstock

# ---------------------------------------------------------------------------
# Physics constant
# ---------------------------------------------------------------------------
_LATENT_HEAT_MJ_PER_KG: float = 2.26  # MJ/kg water at 25 °C, ILLUSTRATIVE


# ---------------------------------------------------------------------------
# WeatherContext
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class WeatherContext:
    """Site weather conditions relevant to feedstock and thermal models.

    Parameters
    ----------
    ambient_temp_c:
        Ambient (outdoor) air temperature [°C].  May be negative.
        Used by thermal formulas that need an ambient reference temperature
        (e.g. AD wall-loss via engine, pyrolysis/gasification preheat).
    relative_humidity:
        Relative humidity as a fraction [0, 1].
    rainfall_mm_d:
        Daily rainfall [mm/day].  Must be >= 0.
    """

    ambient_temp_c: float
    relative_humidity: float
    rainfall_mm_d: float

    def __post_init__(self) -> None:
        if not (0.0 <= self.relative_humidity <= 1.0):
            raise ValueError(
                f"WeatherContext.relative_humidity must be in [0, 1]; "
                f"got {self.relative_humidity}"
            )
        if self.rainfall_mm_d < 0:
            raise ValueError(
                f"WeatherContext.rainfall_mm_d must be >= 0; "
                f"got {self.rainfall_mm_d}"
            )


# ---------------------------------------------------------------------------
# adjust_feedstock_moisture
# ---------------------------------------------------------------------------

def adjust_feedstock_moisture(
    feedstock: Feedstock,
    weather: WeatherContext,
    enabled: bool = False,
    sensitivity: float = 0.05,
) -> Tuple[Feedstock, str]:
    """Optionally adjust feedstock moisture based on rainfall.

    When *enabled* is False the feedstock is returned unchanged with a note
    stating the adjustment was not applied.  When *enabled* is True, moisture
    is raised by ``sensitivity * max(rainfall_mm_d / 10, 0)`` and capped at
    0.95 (wet basis).

    Parameters
    ----------
    feedstock:
        A validated :class:`~feedstock.Feedstock` instance.
    weather:
        A validated :class:`WeatherContext` instance.
    enabled:
        When True, apply the rainfall-based moisture correction.
        Default False.
    sensitivity:
        Fractional increase in moisture per unit of normalised rainfall
        (dimensionless).  Default 0.05.  Must be >= 0.

    Returns
    -------
    (Feedstock, str)
        The (possibly updated) feedstock and a human-readable note string.
        The note always states the MODEL ASSUMPTION caveat when adjustment
        is applied.

    Raises
    ------
    ValueError
        If *sensitivity* < 0.
    """
    if sensitivity < 0:
        raise ValueError(
            f"sensitivity must be >= 0; got {sensitivity}"
        )

    if not enabled:
        return feedstock, "weather moisture adjustment not applied"

    # Delta moisture — MODEL ASSUMPTION, not validated
    delta = sensitivity * max(weather.rainfall_mm_d / 10.0, 0.0)
    new_moisture = min(feedstock.moisture_fraction + delta, 0.95)

    if new_moisture == feedstock.moisture_fraction:
        # No effective change (e.g. zero rainfall or already at 0.95)
        note = (
            "weather moisture adjustment applied (no change): "
            "MODEL ASSUMPTION, not validated"
        )
        return feedstock, note

    adjusted = dataclasses.replace(feedstock, moisture_fraction=new_moisture)
    note = (
        f"weather moisture adjustment applied: moisture "
        f"{feedstock.moisture_fraction:.4g} -> {new_moisture:.4g} "
        f"(rainfall={weather.rainfall_mm_d:.4g} mm/d, "
        f"sensitivity={sensitivity:.4g}): MODEL ASSUMPTION, not validated"
    )
    return adjusted, note


# ---------------------------------------------------------------------------
# drying_energy_kwh_d
# ---------------------------------------------------------------------------

def drying_energy_kwh_d(
    mass_kg_d: float,
    moisture_from: float,
    moisture_to: float,
) -> float:
    """Energy required to dry a wet feedstock stream to a target moisture.

    Uses the solids-conserving water-removal formula:

        dry_mass = mass_kg_d * (1 - moisture_from)
        water_at_target = dry_mass * moisture_to / (1 - moisture_to)
        moisture_to_remove = mass_kg_d * moisture_from - water_at_target
        drying_energy_kwh_d = moisture_to_remove * 2.26 / 3.6

    Returns 0.0 when ``moisture_from <= moisture_to`` (no drying needed).

    Parameters
    ----------
    mass_kg_d:
        Wet feedstock mass flow [kg/day].  Must be >= 0.
    moisture_from:
        Incoming moisture fraction (wet basis) [0, 1).  Must satisfy
        ``0 <= moisture_from < 1``.
    moisture_to:
        Target moisture fraction (wet basis) [0, 1).  Must satisfy
        ``0 <= moisture_to < 1``.

    Returns
    -------
    float
        Drying energy [kWh/day].  Always >= 0.

    Raises
    ------
    ValueError
        If any argument is out of range.
    """
    if mass_kg_d < 0:
        raise ValueError(f"mass_kg_d must be >= 0; got {mass_kg_d}")
    if not (0.0 <= moisture_from < 1.0):
        raise ValueError(f"moisture_from must be in [0, 1); got {moisture_from}")
    if not (0.0 <= moisture_to < 1.0):
        raise ValueError(f"moisture_to must be in [0, 1); got {moisture_to}")

    if moisture_from <= moisture_to:
        return 0.0

    dry_mass: float = mass_kg_d * (1.0 - moisture_from)
    water_in_feed: float = mass_kg_d * moisture_from
    water_at_target: float = dry_mass * moisture_to / (1.0 - moisture_to)
    moisture_to_remove: float = water_in_feed - water_at_target

    return moisture_to_remove * _LATENT_HEAT_MJ_PER_KG / 3.6
