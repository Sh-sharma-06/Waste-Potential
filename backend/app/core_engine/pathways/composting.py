"""Composting pathway model — mass balance and auxiliary energy.

All default parameter values are ILLUSTRATIVE, not validated plant data.
Units: kg/d (mass flows), kWh/d (energy), wet-basis mass unless noted.
There is no energy product; e_net_kwh_d is always negative (parasitic load).

Formulae
--------
dry_in           = M * (1 - moisture_fraction)
organic_dry      = M * organic_fraction * (1 - moisture_fraction)
vs_loss_kg_d     = vs_loss_fraction * organic_dry        [VS lost as CO2 + H2O]
dry_out          = dry_in - vs_loss_kg_d
compost_kg_d     = dry_out / (1 - target_moisture)       [rewetted compost product]
mass_loss_kg_d   = M - compost_kg_d
aux_kwh_d        = aeration_kwh_per_t * M / 1000
e_net_kwh_d      = -aux_kwh_d
ch4_kg_d         = ch4_kg_per_t * M / 1000
n2o_kg_d         = n2o_kg_per_t * M / 1000
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List

from .feedstock import Feedstock


# ---------------------------------------------------------------------------
# Parameter dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class CompostingParams:
    """Parameters for the composting pathway model.

    All default values are ILLUSTRATIVE — replace with site-specific data.

    Parameters
    ----------
    vs_loss_fraction:
        Fraction of organic dry solids lost as CO2 and water during
        biodegradation.  Default 0.50.
    target_moisture:
        Target moisture fraction of the finished compost product (wet basis).
        Default 0.40.
    aeration_kwh_per_t:
        Parasitic electricity for aeration and turning (kWh per tonne
        wet input).  Default 30.
    ch4_kg_per_t:
        Fugitive methane emission factor (kg CH4 per tonne wet input).
        Default 4.
    n2o_kg_per_t:
        Fugitive nitrous oxide emission factor (kg N2O per tonne wet input).
        Default 0.3.
    """

    vs_loss_fraction: float = 0.50
    target_moisture: float = 0.40
    aeration_kwh_per_t: float = 30.0
    ch4_kg_per_t: float = 4.0
    n2o_kg_per_t: float = 0.3

    def __post_init__(self) -> None:
        if not (0.0 < self.vs_loss_fraction <= 1.0):
            raise ValueError(
                f"vs_loss_fraction must be in (0, 1]; got {self.vs_loss_fraction}"
            )
        if not (0.0 <= self.target_moisture < 1.0):
            raise ValueError(
                f"target_moisture must be in [0, 1); got {self.target_moisture}"
            )
        if self.aeration_kwh_per_t < 0:
            raise ValueError(
                f"aeration_kwh_per_t must be >= 0; got {self.aeration_kwh_per_t}"
            )
        if self.ch4_kg_per_t < 0:
            raise ValueError(
                f"ch4_kg_per_t must be >= 0; got {self.ch4_kg_per_t}"
            )
        if self.n2o_kg_per_t < 0:
            raise ValueError(
                f"n2o_kg_per_t must be >= 0; got {self.n2o_kg_per_t}"
            )


# ---------------------------------------------------------------------------
# Simulation function
# ---------------------------------------------------------------------------

def simulate_composting(
    feedstock: Feedstock,
    params: CompostingParams = CompostingParams(),
) -> Dict[str, Any]:
    """Run the composting mass-balance model.

    Parameters
    ----------
    feedstock:
        A validated :class:`~feedstock.Feedstock` instance.
    params:
        Composting model parameters.  Defaults to :class:`CompostingParams`.

    Returns
    -------
    dict
        Keys: compost_kg_d, mass_loss_kg_d, aux_kwh_d, ch4_kg_d, n2o_kg_d,
        e_net_kwh_d, warnings (list[str]), status (str).
        All numeric values are plain Python floats.
    """
    if feedstock.total_mass_kg_d < 0:
        raise ValueError(
            f"feedstock.total_mass_kg_d must be >= 0; got {feedstock.total_mass_kg_d}"
        )

    M: float = feedstock.total_mass_kg_d
    w: float = feedstock.moisture_fraction

    dry_in: float = M * (1.0 - w)
    organic_dry: float = M * feedstock.organic_fraction * (1.0 - w)
    vs_loss_kg_d: float = params.vs_loss_fraction * organic_dry
    dry_out: float = dry_in - vs_loss_kg_d
    compost_kg_d: float = dry_out / (1.0 - params.target_moisture)
    mass_loss_kg_d: float = M - compost_kg_d
    aux_kwh_d: float = params.aeration_kwh_per_t * M / 1000.0
    e_net_kwh_d: float = -aux_kwh_d
    ch4_kg_d: float = params.ch4_kg_per_t * M / 1000.0
    n2o_kg_d: float = params.n2o_kg_per_t * M / 1000.0

    warnings: List[str] = []
    if compost_kg_d > M:
        warnings.append(
            f"compost_kg_d {compost_kg_d:.4g} exceeds input mass {M:.4g} kg/d — "
            "check moisture and vs_loss_fraction settings"
        )
    if e_net_kwh_d > 0:
        warnings.append(
            f"e_net_kwh_d {e_net_kwh_d:.4g} > 0; unexpected for composting "
            "(should be negative/zero)"
        )

    return {
        "compost_kg_d": compost_kg_d,
        "mass_loss_kg_d": mass_loss_kg_d,
        "aux_kwh_d": aux_kwh_d,
        "ch4_kg_d": ch4_kg_d,
        "n2o_kg_d": n2o_kg_d,
        "e_net_kwh_d": e_net_kwh_d,
        "warnings": warnings,
        "status": "illustrative_estimate",
    }
