"""Extended pathway registry — adds HTC and torrefaction to the existing five.

PATHWAYS_EXTENDED is a tuple of all seven supported pathway names.
check_extended() delegates to the existing check_pathway() for the five original
pathways and applies the new feasibility rules for "htc" and "torrefaction".

New-pathway thresholds are MODEL ASSUMPTIONS, not universal limits.
"""
from __future__ import annotations

from typing import List, Optional

from .feasibility import PATHWAYS, Feasibility, check_pathway
from .feedstock import Feedstock
from .htc import _HTC_MIN_MOISTURE, _HTC_MIN_ORGANIC
from .torrefaction import _TORR_MAX_MOISTURE, _TORR_MIN_LIGNOCELLULOSIC

# ---------------------------------------------------------------------------
# Extended pathway registry
# ---------------------------------------------------------------------------

PATHWAYS_EXTENDED: tuple = PATHWAYS + ("htc", "torrefaction")

# ---------------------------------------------------------------------------
# check_extended
# ---------------------------------------------------------------------------


def check_extended(
    name: str,
    feedstock: Feedstock,
    lignocellulosic_fraction: Optional[float] = None,
) -> Feasibility:
    """Check whether *feedstock* meets indicative thresholds for *name*.

    For the five original pathways this delegates to
    :func:`~feasibility.check_pathway`.  For ``"htc"`` and
    ``"torrefaction"`` it applies the new rules described below.

    Parameters
    ----------
    name:
        Pathway identifier — must be one of :data:`PATHWAYS_EXTENDED`.
    feedstock:
        A validated :class:`~feedstock.Feedstock` instance.
    lignocellulosic_fraction:
        Lignocellulosic fraction of the feedstock [0, 1].  Used only for
        ``"torrefaction"``.  When ``None`` (default), ``organic_fraction``
        is used as a proxy and the reason list will include a note:
        "lignocellulosic share not supplied; organic fraction used as proxy".

    Returns
    -------
    Feasibility
        Frozen dataclass with ``feasible``, ``reasons``, and ``basis``.

    Raises
    ------
    ValueError
        If *name* is not in :data:`PATHWAYS_EXTENDED`.

    Notes
    -----
    HTC feasibility (MODEL ASSUMPTION, not a universal limit):
        ``moisture_fraction >= 0.50`` **and** ``organic_fraction >= 0.50``

    Torrefaction feasibility (MODEL ASSUMPTION, not a universal limit):
        ``moisture_fraction <= 0.50`` **and**
        ``lignocellulosic_fraction >= 0.60``
        (proxy: ``organic_fraction`` when ``lignocellulosic_fraction`` is None)
    """
    if name in PATHWAYS:
        return check_pathway(name, feedstock)

    if name not in PATHWAYS_EXTENDED:
        raise ValueError(
            f"Unknown pathway {name!r}. Must be one of {PATHWAYS_EXTENDED}."
        )

    reasons: List[str] = []

    if name == "htc":
        if feedstock.moisture_fraction < _HTC_MIN_MOISTURE:
            reasons.append(
                f"moisture {feedstock.moisture_fraction:.4g} below "
                f"{_HTC_MIN_MOISTURE} minimum (MODEL ASSUMPTION)"
            )
        if feedstock.organic_fraction < _HTC_MIN_ORGANIC:
            reasons.append(
                f"organic_fraction {feedstock.organic_fraction:.4g} below "
                f"{_HTC_MIN_ORGANIC} minimum (MODEL ASSUMPTION)"
            )

    elif name == "torrefaction":
        if feedstock.moisture_fraction > _TORR_MAX_MOISTURE:
            reasons.append(
                f"moisture {feedstock.moisture_fraction:.4g} above "
                f"{_TORR_MAX_MOISTURE} limit (MODEL ASSUMPTION)"
            )
        if lignocellulosic_fraction is None:
            ligno_value: float = feedstock.organic_fraction
            reasons.append(
                "lignocellulosic share not supplied; organic fraction used as proxy"
            )
        else:
            ligno_value = lignocellulosic_fraction
        if ligno_value < _TORR_MIN_LIGNOCELLULOSIC:
            reasons.append(
                f"lignocellulosic_fraction {ligno_value:.4g} below "
                f"{_TORR_MIN_LIGNOCELLULOSIC} minimum (MODEL ASSUMPTION)"
            )

    return Feasibility(
        pathway=name,
        feasible=len(reasons) == 0,
        reasons=reasons,
        basis="illustrative_model_assumptions",
    )
