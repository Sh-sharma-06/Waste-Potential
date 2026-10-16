"""
Data service layer for the Waste-Potential screening pipeline.

Provides two synchronous getter functions consumed by the pathways screening
layer (app.pathways.compare) and the FastAPI route handlers:

  get_stream(location_id)          → dict matching Feedstock schema
  get_location_context(location_id) → dict matching LocationContext schema

Design decisions
----------------
- Pure in-process functions with no network I/O — callers receive results
  immediately.  Database integration (PostGIS) will be added in P4 by wrapping
  these functions with an async DB lookup and falling back to the defaults
  when a record is not found.
- Return plain Python dicts (not Pydantic instances) so the router can choose
  whether to validate with the schema or pass directly to downstream functions.
- All defaults are documented below under "Default catalogue" so that any
  future calibration / measurement can be compared against them explicitly.
- Metadata provenance: unmeasured or defaulted values always carry
  kind="estimated", source_id="default_v1".

Default catalogue (India MSW, peri-urban, 2024 baseline)
---------------------------------------------------------
  LHV_dry                   16.5  MJ/kg   IPCC 2006 Vol.5 Table 2.4 MSW range
  contamination_pct          5.0  %       Field survey average, India CPCB 2022
  moisture_fraction          0.55         NEERI 2020 India MSW characterisation
  ash_fraction_dry           0.18         NEERI 2020
  organic_fraction           0.55         NEERI 2020 (dominant fraction)
  plastic_fraction           0.09         NEERI 2020
  paper_fraction             0.07         NEERI 2020
  other_fraction             0.29         NEERI 2020 (balancing term)

  electricity_tariff_inr_kwh  7.50  INR/kWh  CERC 2024 avg. agricultural tariff
  compost_price_inr_kg        4.00  INR/kg   India compost spot price 2024
  heat_price_inr_kwh          2.50  INR/kWh  Industrial process heat proxy

  ambient_temp_c             25.0  °C      Open-Meteo India peri-urban annual avg
  relative_humidity           0.65         Open-Meteo India annual avg (65 %)
  rainfall_mm_d               0.0  mm/day  Conservative dry-season default

  Sinks (demand-side buyers, default catalogue):
    industrial_heat   — 500 kWh/d,  8.50 INR/kWh, 5.0 km
    residential_grid  — 300 kWh/d,  7.50 INR/kWh, 2.0 km
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Metadata helpers — plain dicts for the return type
# ---------------------------------------------------------------------------

def _meta(kind: str = "estimated", resolution: str = "n/a", source_id: str = "default_v1") -> dict:
    return {"kind": kind, "resolution": resolution, "source_id": source_id}


def _field(value: float, **meta_kwargs: Any) -> dict:
    """Return a dict with 'value' and 'meta' keys matching FeedstockField / LocationScalarField."""
    return {"value": value, "meta": _meta(**meta_kwargs)}


# ---------------------------------------------------------------------------
# Default catalogue constants (see module docstring for references)
# ---------------------------------------------------------------------------

_DEFAULT_LHV_DRY_MJ_KG: float = 16.5
_DEFAULT_CONTAMINATION_PCT: float = 5.0
_DEFAULT_MOISTURE_FRACTION: float = 0.55
_DEFAULT_ASH_FRACTION_DRY: float = 0.18

# Composition fractions — must sum to 1.0
_DEFAULT_ORGANIC_FRACTION: float = 0.55
_DEFAULT_PLASTIC_FRACTION: float = 0.09
_DEFAULT_PAPER_FRACTION: float = 0.07
_DEFAULT_OTHER_FRACTION: float = 0.29      # 0.55+0.09+0.07+0.29 = 1.00 ✓

_DEFAULT_ELECTRICITY_TARIFF_INR_KWH: float = 7.50
_DEFAULT_COMPOST_PRICE_INR_KG: float = 4.00
_DEFAULT_HEAT_PRICE_INR_KWH: float = 2.50

# Weather defaults (Open-Meteo style, India peri-urban annual averages)
_DEFAULT_AMBIENT_TEMP_C: float = 25.0
_DEFAULT_RELATIVE_HUMIDITY: float = 0.65
_DEFAULT_RAINFALL_MM_D: float = 0.0

# Default facilities registered for any unknown location
_DEFAULT_FACILITIES: list[dict] = [
    {"pathway": "anaerobic_digestion", "capacity_t_d": 50.0, "road_km": 15.0},
    {"pathway": "composting",          "capacity_t_d": 30.0, "road_km": 8.0},
    {"pathway": "rdf",                 "capacity_t_d": 20.0, "road_km": 25.0},
]

# Default demand-side sinks (energy buyers)
# industrial_heat pays more per kWh → sorted first by the greedy matcher
_DEFAULT_SINKS: list[dict] = [
    {
        "customer_class": "industrial",
        "accepts": ["heat", "electricity"],
        "demand_kwh_d": 500.0,
        "road_km": 5.0,
        "price": 8.50,    # INR/kWh — industrial process heat, higher tariff
    },
    {
        "customer_class": "residential",
        "accepts": ["electricity"],
        "demand_kwh_d": 300.0,
        "road_km": 2.0,
        "price": 7.50,    # INR/kWh — residential microgrid, standard tariff
    },
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_stream(location_id: str) -> dict:
    """Return feedstock characterisation for *location_id*.

    In Phase 1 all values are populated from the default catalogue
    (kind="estimated", source_id="default_v1").  Phase 4 will replace this
    with a PostGIS lookup that falls back to these defaults on a cache miss.

    Parameters
    ----------
    location_id:
        Unique identifier of the waste-source location (farm, ward, depot).
        Currently unused — future DB integration will key on this value.

    Returns
    -------
    dict
        Plain dictionary that validates against ``app.schemas.data.Feedstock``.

    Notes
    -----
    The total_mass_kg_d default of 1 000 kg/day represents a small peri-urban
    farm / community cluster.  The caller must override this with a real survey
    value or the ML predictor output (app.ml.predictor.YieldPredictor) before
    passing to the LP optimiser.
    """
    _default = _meta()  # shorthand

    return {
        "total_mass_kg_d": _field(1_000.0),   # 1 tonne/day placeholder
        "organic_fraction": _field(_DEFAULT_ORGANIC_FRACTION),
        "plastic_fraction": _field(_DEFAULT_PLASTIC_FRACTION),
        "paper_fraction":   _field(_DEFAULT_PAPER_FRACTION),
        "other_fraction":   _field(_DEFAULT_OTHER_FRACTION),
        "moisture_fraction":  _field(_DEFAULT_MOISTURE_FRACTION),
        "ash_fraction_dry":   _field(_DEFAULT_ASH_FRACTION_DRY),
        "lhv_dry_mj_per_kg":  _field(_DEFAULT_LHV_DRY_MJ_KG),
        "contamination_pct":  _field(_DEFAULT_CONTAMINATION_PCT),
    }


def get_location_context(location_id: str) -> dict:
    """Return site-level economic, environmental and logistical context.

    In Phase 1 all scalar values are populated from the default catalogue
    (kind="estimated", source_id="default_v1").  Phase 4 will replace this
    with a PostGIS + Open-Meteo lookup.

    Parameters
    ----------
    location_id:
        Unique identifier of the site.  Currently unused.

    Returns
    -------
    dict
        Plain dictionary that validates against ``app.schemas.data.LocationContext``.
        New fields vs Phase 1: ambient_temp_c, relative_humidity, rainfall_mm_d,
        sinks.
    """
    return {
        "electricity_tariff_inr_per_kwh": _field(_DEFAULT_ELECTRICITY_TARIFF_INR_KWH),
        "compost_price_inr_per_kg":       _field(_DEFAULT_COMPOST_PRICE_INR_KG),
        "heat_price_inr_per_kwh":         _field(_DEFAULT_HEAT_PRICE_INR_KWH),
        "grid_available": True,
        "facilities": list(_DEFAULT_FACILITIES),
        # --- weather fields (Open-Meteo style defaults) ---
        "ambient_temp_c":      _field(_DEFAULT_AMBIENT_TEMP_C),
        "relative_humidity":   _field(_DEFAULT_RELATIVE_HUMIDITY),
        "rainfall_mm_d":       _field(_DEFAULT_RAINFALL_MM_D),
        # --- demand sinks ---
        "sinks": list(_DEFAULT_SINKS),
    }
