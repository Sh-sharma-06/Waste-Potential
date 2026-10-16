"""
thermal.py — Heat demand and CHP/boiler split calculations for B1 Science Core.

All functions are pure (no side effects).  Both return frozen dataclasses so
callers can unpack results by field name rather than by position.

Geometry assumption for wall-loss calculation
---------------------------------------------
The digester is modelled as a vertical cylinder whose height equals its
diameter (H = D).  Given volume V:
    D = (4V / π)^(1/3)
    A_total = π*D*H + 2*(π/4)*D² = π*D² + π/2*D² = 1.5*π*D²
This gives A = 1.5*π*D², which is used for the wall-loss term.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Return-value dataclasses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class HeatDemand:
    """Daily thermal energy demand broken down by component [kWh/day]."""
    feed_heating_kwh_d: float
    wall_loss_kwh_d: float
    total_kwh_d: float


@dataclass(frozen=True)
class HeatSplit:
    """Allocation of chemical energy between boiler and CHP [kWh/day]."""
    boiler_fuel_kwh_d: float
    chp_fuel_kwh_d: float
    heat_deficit: bool   # True when boiler cap was hit (demand still unmet)


# ---------------------------------------------------------------------------
# 1. heat_demand_kwh
# ---------------------------------------------------------------------------

def heat_demand_kwh(
    feed_kg_d: float,
    delta_t_k: float,
    digester_m3: float,
    cp_kj_kg_k: float,
    u_wall_w_m2k: float,
) -> HeatDemand:
    """Return daily thermal heat demand split into feed-heating and wall-loss.

    Parameters
    ----------
    feed_kg_d:
        Daily mass of conditioned feed entering the digester [kg/day].
    delta_t_k:
        Temperature difference (digester − ambient) [K].
        Values ≤ 0 yield zero demand (no heating needed).
    digester_m3:
        Active digester volume [m³].  Zero produces zero wall loss.
    cp_kj_kg_k:
        Specific heat capacity of feed slurry [kJ / kg·K].
    u_wall_w_m2k:
        Overall heat-transfer coefficient of digester wall [W / m²·K].

    Returns
    -------
    HeatDemand
        ``feed_heating_kwh_d`` — sensible heat to raise feed to digester temp.
        ``wall_loss_kwh_d``    — steady-state heat lost through vessel wall.
        ``total_kwh_d``        — sum of both components.

    Raises
    ------
    ValueError
        If any of ``feed_kg_d``, ``digester_m3``, ``cp_kj_kg_k``, or
        ``u_wall_w_m2k`` is negative.

    Notes
    -----
    Geometry: cylinder with H = D.
        D = (4V/π)^(1/3),  A = 1.5·π·D²
    Feed heating  [kWh/d] = feed × cp × max(dT, 0) / 3600
    Wall loss     [kWh/d] = U × A × max(dT, 0) × 24 / 1000
    """
    if feed_kg_d < 0:
        raise ValueError(f"feed_kg_d must be >= 0; got {feed_kg_d}")
    if digester_m3 < 0:
        raise ValueError(f"digester_m3 must be >= 0; got {digester_m3}")
    if cp_kj_kg_k < 0:
        raise ValueError(f"cp_kj_kg_k must be >= 0; got {cp_kj_kg_k}")
    if u_wall_w_m2k < 0:
        raise ValueError(f"u_wall_w_m2k must be >= 0; got {u_wall_w_m2k}")

    dt = max(delta_t_k, 0.0)

    feed_heating = feed_kg_d * cp_kj_kg_k * dt / 3600.0

    if digester_m3 == 0.0:
        wall_loss = 0.0
    else:
        d = (4.0 * digester_m3 / math.pi) ** (1.0 / 3.0)
        area = 1.5 * math.pi * d * d
        wall_loss = u_wall_w_m2k * area * dt * 24.0 / 1000.0

    return HeatDemand(
        feed_heating_kwh_d=feed_heating,
        wall_loss_kwh_d=wall_loss,
        total_kwh_d=feed_heating + wall_loss,
    )


# ---------------------------------------------------------------------------
# 2. split_chp_boiler
# ---------------------------------------------------------------------------

def split_chp_boiler(
    c_chem_kwh_d: float,
    q_demand_kwh_d: float,
    eta_th: float,
    eta_boiler: float,
) -> HeatSplit:
    """Allocate available chemical energy between CHP and auxiliary boiler.

    CHP thermal output covers the heat demand first.  If CHP heat alone is
    insufficient, an auxiliary boiler supplements; the boiler fuel draw is
    capped at ``c_chem_kwh_d`` (cannot burn more than is available).

    Parameters
    ----------
    c_chem_kwh_d:
        Total available chemical energy from biogas [kWh/day].
    q_demand_kwh_d:
        Total daily heat demand [kWh/day].
    eta_th:
        CHP thermal efficiency (fraction of gross chemical energy recovered
        as useful heat) [0-1].
    eta_boiler:
        Auxiliary boiler thermal efficiency [0-1].  Must be strictly greater
        than ``eta_th`` to avoid division by zero.

    Returns
    -------
    HeatSplit
        ``boiler_fuel_kwh_d`` — chemical energy routed to boiler [kWh/day].
        ``chp_fuel_kwh_d``    — chemical energy routed to CHP [kWh/day].
        ``heat_deficit``      — True when boiler cap was hit and demand is
                                still not fully met.

    Raises
    ------
    ValueError
        If ``eta_boiler <= eta_th`` (would cause division by zero / nonsensical
        result) or if ``c_chem_kwh_d`` or ``q_demand_kwh_d`` is negative.
    """
    if c_chem_kwh_d < 0:
        raise ValueError(f"c_chem_kwh_d must be >= 0; got {c_chem_kwh_d}")
    if q_demand_kwh_d < 0:
        raise ValueError(f"q_demand_kwh_d must be >= 0; got {q_demand_kwh_d}")
    if eta_boiler <= eta_th:
        raise ValueError(
            f"eta_boiler ({eta_boiler}) must be > eta_th ({eta_th}) "
            "to avoid division by zero in the boiler fuel calculation."
        )

    chp_heat_available = c_chem_kwh_d * eta_th

    if q_demand_kwh_d <= chp_heat_available:
        # CHP thermal output is sufficient — no boiler needed
        boiler = 0.0
        deficit = False
    else:
        boiler = (q_demand_kwh_d - chp_heat_available) / (eta_boiler - eta_th)
        if boiler > c_chem_kwh_d:
            boiler = c_chem_kwh_d
            deficit = True
        else:
            deficit = False

    return HeatSplit(
        boiler_fuel_kwh_d=boiler,
        chp_fuel_kwh_d=c_chem_kwh_d - boiler,
        heat_deficit=deficit,
    )
