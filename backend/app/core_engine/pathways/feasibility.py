"""Pathway feasibility checks for waste-to-energy technologies.

All numeric thresholds below are MODEL ASSUMPTIONS derived from engineering
literature ranges.  They are not universal limits; site-specific conditions,
feedstock variability, and technology suppliers may use different thresholds.
Each constant is annotated "MODEL ASSUMPTION, not a universal limit".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .feedstock import Feedstock

# ---------------------------------------------------------------------------
# Supported pathways
# ---------------------------------------------------------------------------

PATHWAYS = (
    "anaerobic_digestion",
    "composting",
    "incineration",
    "gasification",
    "pyrolysis",
)

# ---------------------------------------------------------------------------
# Threshold constants — MODEL ASSUMPTION, not a universal limit
# ---------------------------------------------------------------------------

_AD_MIN_ORGANIC: float = 0.30           # MODEL ASSUMPTION, not a universal limit
_AD_MIN_MOISTURE: float = 0.50          # MODEL ASSUMPTION, not a universal limit

_COMP_MIN_ORGANIC: float = 0.40         # MODEL ASSUMPTION, not a universal limit
_COMP_MAX_CONTAMINATION_PCT: float = 15.0  # MODEL ASSUMPTION, not a universal limit

_INC_MIN_LHV_WET_MJ_KG: float = 7.0    # MODEL ASSUMPTION, not a universal limit

_GAS_MAX_MOISTURE: float = 0.15         # MODEL ASSUMPTION, not a universal limit
_GAS_MIN_LHV_WET_MJ_KG: float = 10.0   # MODEL ASSUMPTION, not a universal limit

_PYR_MAX_MOISTURE: float = 0.10         # MODEL ASSUMPTION, not a universal limit
_PYR_MIN_PLASTIC_PAPER: float = 0.40    # MODEL ASSUMPTION, not a universal limit

# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Feasibility:
    """Feasibility assessment for one waste-to-energy pathway.

    Attributes
    ----------
    pathway:
        Name of the assessed pathway (one of :data:`PATHWAYS`).
    feasible:
        True when all threshold conditions are satisfied.
    reasons:
        List of human-readable strings explaining each failed condition.
        Empty when ``feasible`` is True.
    basis:
        Short string identifying the basis of the assessment.
    """

    pathway: str
    feasible: bool
    reasons: List[str] = field(default_factory=list)
    basis: str = "illustrative_model_assumptions"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def check_pathway(name: str, feedstock: Feedstock) -> Feasibility:
    """Check whether *feedstock* meets the indicative thresholds for *name*.

    Parameters
    ----------
    name:
        Pathway identifier — must be one of :data:`PATHWAYS`.
    feedstock:
        A validated :class:`~feedstock.Feedstock` instance.

    Returns
    -------
    Feasibility
        Frozen dataclass with ``feasible``, ``reasons``, and ``basis``.

    Raises
    ------
    ValueError
        If *name* is not in :data:`PATHWAYS`.
    """
    if name not in PATHWAYS:
        raise ValueError(
            f"Unknown pathway {name!r}. Must be one of {PATHWAYS}."
        )

    reasons: List[str] = []

    if name == "anaerobic_digestion":
        if feedstock.organic_fraction < _AD_MIN_ORGANIC:
            reasons.append(
                f"organic_fraction {feedstock.organic_fraction:.4g} below "
                f"{_AD_MIN_ORGANIC} minimum"
            )
        if feedstock.moisture_fraction < _AD_MIN_MOISTURE:
            reasons.append(
                f"moisture {feedstock.moisture_fraction:.4g} below "
                f"{_AD_MIN_MOISTURE} minimum"
            )

    elif name == "composting":
        if feedstock.organic_fraction < _COMP_MIN_ORGANIC:
            reasons.append(
                f"organic_fraction {feedstock.organic_fraction:.4g} below "
                f"{_COMP_MIN_ORGANIC} minimum"
            )
        if feedstock.contamination_pct > _COMP_MAX_CONTAMINATION_PCT:
            reasons.append(
                f"contamination_pct {feedstock.contamination_pct:.4g} above "
                f"{_COMP_MAX_CONTAMINATION_PCT} limit"
            )

    elif name == "incineration":
        lhv_wet = feedstock.lhv_wet_mj_per_kg()
        if lhv_wet < _INC_MIN_LHV_WET_MJ_KG:
            reasons.append(
                f"lhv_wet {lhv_wet:.4g} MJ/kg below {_INC_MIN_LHV_WET_MJ_KG} minimum"
            )

    elif name == "gasification":
        if feedstock.moisture_fraction > _GAS_MAX_MOISTURE:
            reasons.append(
                f"moisture {feedstock.moisture_fraction:.4g} above "
                f"{_GAS_MAX_MOISTURE} limit"
            )
        lhv_wet = feedstock.lhv_wet_mj_per_kg()
        if lhv_wet < _GAS_MIN_LHV_WET_MJ_KG:
            reasons.append(
                f"lhv_wet {lhv_wet:.4g} MJ/kg below {_GAS_MIN_LHV_WET_MJ_KG} minimum"
            )

    elif name == "pyrolysis":
        if feedstock.moisture_fraction > _PYR_MAX_MOISTURE:
            reasons.append(
                f"moisture {feedstock.moisture_fraction:.4g} above "
                f"{_PYR_MAX_MOISTURE} limit"
            )
        pp = feedstock.plastic_fraction + feedstock.paper_fraction
        if pp < _PYR_MIN_PLASTIC_PAPER:
            reasons.append(
                f"plastic+paper fraction {pp:.4g} below "
                f"{_PYR_MIN_PLASTIC_PAPER} minimum"
            )

    return Feasibility(
        pathway=name,
        feasible=len(reasons) == 0,
        reasons=reasons,
        basis="illustrative_model_assumptions",
    )
