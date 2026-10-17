"""Adapter layer: converts raw waste-stream dicts into pathway physics inputs.

All functions are pure (no file, network, or DB access).
Units: mass in kg/d (wet basis), energy in kWh/d, gas in Nm³ at 0 °C.
GHG outputs are in kg CO2-equivalent per tonne of total_mass_kg_d input.

GWP assumptions (MODEL ASSUMPTION, source="IPCC AR6 WGI Table 7.SM.7", status="illustrative"):
    CH4   GWP-100 = 29.8  (IPCC AR6)
    N2O   GWP-100 = 273   (IPCC AR6)
"""
from __future__ import annotations

import dataclasses
from typing import Any, Dict, List

from .feedstock import Feedstock
from .feasibility import PATHWAYS, check_pathway
from .extended import PATHWAYS_EXTENDED, check_extended
from .composting import simulate_composting
from .incineration import simulate_incineration
from .gasification import simulate_gasification
from .pyrolysis import simulate_pyrolysis

# GWP-100 constants (MODEL ASSUMPTION, source="IPCC AR6 WGI Table 7.SM.7", status="illustrative")
_GWP_CH4: float = 29.8   # kg CO2-eq / kg CH4   — IPCC AR6
_GWP_N2O: float = 273.0  # kg CO2-eq / kg N2O   — IPCC AR6

# Per-pathway primary product and energy/GHG metadata — MODEL ASSUMPTION,
# a pathway's headline product may differ in practice (e.g. AD can produce CBG).
_PRIMARY_PRODUCT: dict = {
    "anaerobic_digestion": "electricity",
    "composting":          "compost",
    "incineration":        "electricity",
    "gasification":        "electricity",
    "pyrolysis":           "fuel",
    "htc":                 "fuel",
    "torrefaction":        "fuel",
}
_ENERGY_BASIS: dict = {
    "anaerobic_digestion": "electrical",
    "composting":          "electrical",
    "incineration":        "electrical",
    "gasification":        "electrical",
    "pyrolysis":           "thermal",
    "htc":                 "thermal",
    "torrefaction":        "thermal",
}
_GHG_MODELLED: dict = {
    "anaerobic_digestion": False,
    "composting":          True,
    "incineration":        True,
    "gasification":        False,
    "pyrolysis":           False,
    "htc":                 False,
    "torrefaction":        False,
}

# Feedstock field names that must be present in a stream dict
_REQUIRED_KEYS: tuple = (
    "total_mass_kg_d",
    "organic_fraction",
    "plastic_fraction",
    "paper_fraction",
    "other_fraction",
    "moisture_fraction",
    "ash_fraction_dry",
    "lhv_dry_mj_per_kg",
    "contamination_pct",
)


def _unwrap(value: Any, key: str) -> float:
    """Unwrap a plain float or a ``{"value": x, "meta": {...}}`` wrapper.

    Parameters
    ----------
    value:
        Raw value from the stream dict: either a plain ``float`` / ``int``,
        or a dict with at minimum a ``"value"`` key.
    key:
        Field name used in error messages.

    Returns
    -------
    float
        The unwrapped numeric value.

    Raises
    ------
    ValueError
        If *value* is a dict but lacks a ``"value"`` key, or if the extracted
        number cannot be converted to float.
    """
    if isinstance(value, dict):
        if "value" not in value:
            raise ValueError(
                f"Stream field '{key}' is a dict but has no 'value' key: {value!r}"
            )
        value = value["value"]
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(
            f"Stream field '{key}' cannot be converted to float: {value!r}"
        ) from exc


def feedstock_from_stream(stream: dict) -> Feedstock:
    """Build a validated :class:`~feedstock.Feedstock` from a raw stream dict.

    Each field in *stream* may be either a plain ``float`` or a
    ``{"value": x, "meta": {...}}`` wrapper dict — both are accepted.
    Missing required keys raise :exc:`ValueError` naming the missing key.

    When ``lignocellulosic_fraction`` is present the five composition fractions
    (organic, plastic, paper, other, lignocellulosic) must sum to 1 ± 1e-6.
    The Feedstock is built with ``other_fraction = other + lignocellulosic``
    so the existing four-fraction sum rule is preserved.

    Parameters
    ----------
    stream:
        Dictionary with (at minimum) the nine Feedstock fields:
        ``total_mass_kg_d``, ``organic_fraction``, ``plastic_fraction``,
        ``paper_fraction``, ``other_fraction``, ``moisture_fraction``,
        ``ash_fraction_dry``, ``lhv_dry_mj_per_kg``, ``contamination_pct``.
        Optionally ``lignocellulosic_fraction``.

    Returns
    -------
    Feedstock
        A fully validated, frozen :class:`~feedstock.Feedstock` instance.

    Raises
    ------
    ValueError
        If any required key is absent, if the five fractions do not sum to 1,
        or if the unwrapped values fail the Feedstock validation rules.
    """
    for key in _REQUIRED_KEYS:
        if key not in stream:
            raise ValueError(
                f"Missing required stream field: '{key}'"
            )

    kwargs: Dict[str, float] = {
        key: _unwrap(stream[key], key) for key in _REQUIRED_KEYS
    }

    if "lignocellulosic_fraction" in stream:
        ligno = _unwrap(stream["lignocellulosic_fraction"], "lignocellulosic_fraction")
        five_sum = (
            kwargs["organic_fraction"]
            + kwargs["plastic_fraction"]
            + kwargs["paper_fraction"]
            + kwargs["other_fraction"]
            + ligno
        )
        if abs(five_sum - 1.0) > 1e-6:
            raise ValueError(
                f"organic_fraction + plastic_fraction + paper_fraction + "
                f"other_fraction + lignocellulosic_fraction must sum to 1.0 "
                f"(got {five_sum:.8f})"
            )
        kwargs["other_fraction"] = kwargs["other_fraction"] + ligno

    return Feedstock(**kwargs)


def physics_inputs(
    stream: dict,
    ambient_temp_c: float = 25.0,
) -> Dict[str, Dict[str, Any]]:
    """Compute per-pathway feasibility and physics outputs for a waste stream.

    For each pathway in :data:`~feasibility.PATHWAYS`, the result contains:
    ``feasible`` (bool), ``reasons`` (list[str] — empty when feasible),
    ``net_kwh_per_tonne`` (float, kWh per tonne of total_mass_kg_d),
    ``direct_ghg_kg_per_tonne`` (float, kg CO2-eq per tonne of total_mass_kg_d),
    ``model_status`` (str), ``warnings`` (list[str]).

    Infeasible pathways return ``net_kwh_per_tonne = 0.0`` and the reasons from
    :func:`~feasibility.check_pathway`.  GHG is modelled only for composting
    (CH4 + N2O, GWP-100) and incineration (fossil CO2 from plastics); all
    other pathways return 0.0 with a warning.

    Parameters
    ----------
    stream:
        Raw stream dict — same format as accepted by :func:`feedstock_from_stream`.
    ambient_temp_c:
        Ambient (feed inlet) temperature in °C, used as the AD Params field.
        Default 25.0 °C.

    Returns
    -------
    dict
        Outer key = pathway name (one of :data:`~feasibility.PATHWAYS`);
        inner dict has six keys: ``feasible``, ``reasons``,
        ``net_kwh_per_tonne``, ``direct_ghg_kg_per_tonne``,
        ``model_status``, ``warnings``.
    """
    feedstock: Feedstock = feedstock_from_stream(stream)
    mass_t_d: float = feedstock.total_mass_kg_d / 1000.0

    # Optional new stream fields
    lignocellulosic_fraction: Any = None
    if "lignocellulosic_fraction" in stream:
        lignocellulosic_fraction = _unwrap(
            stream["lignocellulosic_fraction"], "lignocellulosic_fraction"
        )

    organic_moisture_fraction: Any = None
    if "organic_moisture_fraction" in stream:
        organic_moisture_fraction = _unwrap(
            stream["organic_moisture_fraction"], "organic_moisture_fraction"
        )

    result: Dict[str, Dict[str, Any]] = {}

    for pathway in PATHWAYS_EXTENDED:
        # Use check_extended for all pathways (it delegates for the original five)
        feasibility = check_extended(pathway, feedstock, lignocellulosic_fraction)

        if not feasibility.feasible:
            entry: Dict[str, Any] = {
                "feasible": False,
                "reasons": list(feasibility.reasons),
                "net_kwh_per_tonne": 0.0,
                "direct_ghg_kg_per_tonne": 0.0,
                "model_status": "infeasible",
                "warnings": list(feasibility.reasons),
                "primary_product": _PRIMARY_PRODUCT[pathway],
                "energy_basis": _ENERGY_BASIS[pathway],
                "ghg_modelled": _GHG_MODELLED[pathway],
            }
            if pathway == "torrefaction":
                entry["lignocellulosic_source"] = (
                    "stream" if lignocellulosic_fraction is not None else "proxy"
                )
            if pathway == "anaerobic_digestion":
                entry["ts_source"] = (
                    "stream" if organic_moisture_fraction is not None else "default"
                )
            result[pathway] = entry
            continue

        # --- run the appropriate simulator ---
        sim_warnings: List[str] = []
        ghg_kg_d: float = 0.0
        ghg_warnings: List[str] = []

        if pathway == "anaerobic_digestion":
            # Import here to avoid circular dependency; lazy import is fine
            # in a pure-function context.
            from app.core_engine.params import Params
            from app.core_engine.engine import simulate as _simulate_ad
            p = dataclasses.replace(
                Params(),
                total_mass_kg_d=feedstock.total_mass_kg_d,
                organic_fraction=feedstock.organic_fraction,
                ambient_temp_c=ambient_temp_c,
            )
            if organic_moisture_fraction is not None:
                p = dataclasses.replace(p, ts_fraction=1.0 - organic_moisture_fraction)
            sim = _simulate_ad(p)
            e_net_kwh_d: float = sim["e_net_kwh_d"]
            sim_warnings = list(sim.get("warnings", []))
            model_status: str = sim.get("status", "illustrative_estimate")
            ghg_warnings = ["GHG not modelled"]

        elif pathway == "composting":
            sim = simulate_composting(feedstock)
            e_net_kwh_d = sim["e_net_kwh_d"]
            sim_warnings = list(sim.get("warnings", []))
            model_status = sim.get("status", "illustrative_estimate")
            ch4_kg_d: float = sim["ch4_kg_d"]
            n2o_kg_d: float = sim["n2o_kg_d"]
            ghg_kg_d = ch4_kg_d * _GWP_CH4 + n2o_kg_d * _GWP_N2O

        elif pathway == "incineration":
            sim = simulate_incineration(feedstock)
            e_net_kwh_d = sim["e_net_kwh_d"]
            sim_warnings = list(sim.get("warnings", []))
            model_status = sim.get("status", "illustrative_estimate")
            ghg_kg_d = sim["co2_fossil_kg_d"]

        elif pathway == "gasification":
            sim = simulate_gasification(feedstock)
            e_net_kwh_d = sim["e_net_kwh_d"]
            sim_warnings = list(sim.get("warnings", []))
            model_status = sim.get("status", "illustrative_estimate")
            ghg_warnings = ["GHG not modelled"]

        elif pathway == "pyrolysis":
            sim = simulate_pyrolysis(feedstock)
            # pyrolysis uses e_net_energy_kwh_d (thermal basis)
            e_net_kwh_d = sim["e_net_energy_kwh_d"]
            sim_warnings = list(sim.get("warnings", []))
            model_status = sim.get("status", "illustrative_estimate")
            ghg_warnings = ["GHG not modelled"]

        elif pathway == "htc":
            from .htc import simulate_htc
            sim = simulate_htc(feedstock)
            e_net_kwh_d = sim.get("e_net_energy_kwh_d", 0.0)
            sim_warnings = list(sim.get("warnings", []))
            model_status = sim.get("status", "illustrative_estimate")
            ghg_warnings = ["GHG not modelled"]

        elif pathway == "torrefaction":
            from .torrefaction import simulate_torrefaction
            sim = simulate_torrefaction(feedstock)
            e_net_kwh_d = sim.get("e_net_energy_kwh_d", 0.0)
            sim_warnings = list(sim.get("warnings", []))
            model_status = sim.get("status", "illustrative_estimate")
            ghg_warnings = ["GHG not modelled"]

        net_kwh_per_tonne: float = (
            e_net_kwh_d / mass_t_d if mass_t_d > 0.0 else 0.0
        )
        ghg_per_tonne: float = (
            ghg_kg_d / mass_t_d if mass_t_d > 0.0 else 0.0
        )

        all_warnings: List[str] = sim_warnings + ghg_warnings

        entry = {
            "feasible": True,
            "reasons": [],
            "net_kwh_per_tonne": net_kwh_per_tonne,
            "direct_ghg_kg_per_tonne": ghg_per_tonne,
            "model_status": model_status,
            "warnings": all_warnings,
            "primary_product": _PRIMARY_PRODUCT[pathway],
            "energy_basis": _ENERGY_BASIS[pathway],
            "ghg_modelled": _GHG_MODELLED[pathway],
        }
        if pathway == "torrefaction":
            entry["lignocellulosic_source"] = (
                "stream" if lignocellulosic_fraction is not None else "proxy"
            )
        if pathway == "anaerobic_digestion":
            entry["ts_source"] = (
                "stream" if organic_moisture_fraction is not None else "default"
            )
        result[pathway] = entry

    return result
