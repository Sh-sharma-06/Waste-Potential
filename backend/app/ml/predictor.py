"""
YieldPredictor — crop-based biomass and biogas yield estimation.

This module provides a synchronous, in-process predictor that converts
agronomy inputs (crop type, cultivated area, soil quality index) into
daily mass generation estimates consumed by the pathways screening pipeline.

Architecture
------------
Phase 1 uses a calibrated lookup table of crop-specific residue-to-product
ratios (the "agronomy factor model").  The table is sourced from FAOSTAT 2023
crop residue data and IPCC 2006 Vol.4 default residue-to-product ratios.

Phase 2 will replace the lookup with the trained hybrid ML model (GBR +
residual neural net) in app.ml.yield_model once a labelled dataset is
available.  The interface (predict_yield signature and return dict keys)
is intentionally frozen so the swap is transparent to callers.

Return contract (keys are fixed — do not rename without updating all callers):
  total_mass_kg_d   float — daily raw biomass / crop residue (kg/day)
  dry_matter_kg_d   float — dry-matter equivalent (kg/day)
  biogas_m3_d       float — indicative biogas potential (Nm³/day) for AD pathway

Usage
-----
>>> from app.ml.predictor import YieldPredictor
>>> p = YieldPredictor()
>>> result = p.predict_yield("maize", area_ha=5.0, soil_index=0.75)
>>> result["total_mass_kg_d"]
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Crop agronomy factor table
#
# Source:
#   FAOSTAT 2023 — Crop residue-to-product ratio (RPR) and residue dry-matter
#   fraction.  Values are global medians; India-specific overrides can be
#   added to the CROP_OVERRIDES dict below without changing the class.
#
# Columns:
#   rpr         residue-to-product ratio (kg residue / kg grain or fruit)
#   dm_fraction dry-matter fraction of fresh residue (0–1)
#   vs_fraction volatile-solids fraction of dry matter (0–1); used for AD
#   y0_nm3_kg   indicative maximum biogas yield (Nm³/kg VS); Chen-Hashimoto Y0
#   fresh_yield_t_ha_yr tonnes of fresh primary product per ha per year
# ---------------------------------------------------------------------------

_CROP_TABLE: dict[str, dict[str, float]] = {
    "maize": {
        "rpr": 1.50, "dm_fraction": 0.85, "vs_fraction": 0.90,
        "y0_nm3_kg": 0.45, "fresh_yield_t_ha_yr": 8.0,
    },
    "wheat": {
        "rpr": 1.30, "dm_fraction": 0.87, "vs_fraction": 0.88,
        "y0_nm3_kg": 0.38, "fresh_yield_t_ha_yr": 4.5,
    },
    "rice": {
        "rpr": 1.40, "dm_fraction": 0.88, "vs_fraction": 0.80,
        "y0_nm3_kg": 0.35, "fresh_yield_t_ha_yr": 5.5,
    },
    "sugarcane": {
        "rpr": 0.30, "dm_fraction": 0.50, "vs_fraction": 0.85,
        "y0_nm3_kg": 0.30, "fresh_yield_t_ha_yr": 70.0,
    },
    "sorghum": {
        "rpr": 1.20, "dm_fraction": 0.84, "vs_fraction": 0.88,
        "y0_nm3_kg": 0.42, "fresh_yield_t_ha_yr": 3.5,
    },
    "cassava": {
        "rpr": 0.50, "dm_fraction": 0.40, "vs_fraction": 0.90,
        "y0_nm3_kg": 0.40, "fresh_yield_t_ha_yr": 25.0,
    },
    "banana": {
        "rpr": 2.50, "dm_fraction": 0.18, "vs_fraction": 0.92,
        "y0_nm3_kg": 0.42, "fresh_yield_t_ha_yr": 40.0,
    },
    # Generic / unknown fallback
    "_default": {
        "rpr": 1.00, "dm_fraction": 0.75, "vs_fraction": 0.85,
        "y0_nm3_kg": 0.38, "fresh_yield_t_ha_yr": 5.0,
    },
}

_DAYS_PER_YEAR: float = 365.25

# Indicative HRT for a standard AD digester (days) — used for biogas estimate
_DEFAULT_HRT_DAYS: float = 25.0

# Chen-Hashimoto kinetic defaults (global median, all feedstocks)
_DEFAULT_MU: float = 0.40   # 1/day
_DEFAULT_K:  float = 0.80   # dimensionless


def _chen_hashimoto(y0: float, hrt: float, mu: float, k: float) -> float:
    """Estimate biogas yield (Nm³/kg VS) via the Chen-Hashimoto kinetic model.

    Y = Y0 × (1 − K / (HRT × μ − 1 + K))

    Returns 0.0 if the denominator is non-physical (≤ 0).
    """
    denom = hrt * mu - 1.0 + k
    if denom <= 1e-9:
        return 0.0
    return y0 * (1.0 - k / denom)


class YieldPredictor:
    """Synchronous agronomy-factor model for crop residue yield estimation.

    Instantiate once and call ``predict_yield()`` for each farm record.
    The class is stateless and thread-safe.

    Methods
    -------
    predict_yield(crop_type, area_ha, soil_index) → dict
    """

    def __init__(self, hrt_days: float = _DEFAULT_HRT_DAYS) -> None:
        """
        Parameters
        ----------
        hrt_days:
            Hydraulic Retention Time (days) used for the biogas estimate.
            Defaults to 25 days (typical for a mesophilic CSTR digester).
        """
        self._hrt = hrt_days

    def predict_yield(
        self,
        crop_type: str,
        area_ha: float,
        soil_index: float,
    ) -> dict:
        """Predict daily biomass and biogas generation for *crop_type*.

        The soil quality index is applied as a multiplicative yield modifier
        on the crop-specific fresh yield (soil_index=1.0 → median yield;
        soil_index=0.5 → 50 % of median).

        Parameters
        ----------
        crop_type:
            Crop identifier (case-insensitive).  Falls back to ``"_default"``
            if the crop is not in the lookup table.
        area_ha:
            Cultivated area in hectares.  Must be > 0.
        soil_index:
            Relative soil quality index in [0, 1].  1.0 = best-practice
            (FAO "good" soils), 0.0 would imply zero yield (clamped to 0.05
            to avoid degenerate outputs).

        Returns
        -------
        dict with keys:
            total_mass_kg_d : float  — daily raw biomass (residue) in kg/day
            dry_matter_kg_d : float  — dry-matter equivalent in kg/day
            biogas_m3_d     : float  — indicative biogas volume (Nm³/day)

        Raises
        ------
        ValueError
            If area_ha ≤ 0.
        """
        if area_ha <= 0:
            raise ValueError(f"area_ha must be > 0, got {area_ha}")

        # Clamp soil index to [0.05, 1.0] to avoid degenerate zero
        si = max(0.05, min(1.0, soil_index))

        # Lookup — case-insensitive, fallback to _default
        row = _CROP_TABLE.get(crop_type.lower(), _CROP_TABLE["_default"])

        # Annual fresh primary product (tonnes/ha/yr), soil-adjusted
        fresh_annual_t = row["fresh_yield_t_ha_yr"] * area_ha * si

        # Annual residue (tonnes/yr)
        residue_annual_t = fresh_annual_t * row["rpr"]

        # Daily residue (kg/day)
        total_mass_kg_d = (residue_annual_t * 1_000.0) / _DAYS_PER_YEAR

        # Dry matter (kg/day)
        dry_matter_kg_d = total_mass_kg_d * row["dm_fraction"]

        # Volatile solids fed to digester (kg/day)
        vs_kg_d = dry_matter_kg_d * row["vs_fraction"]

        # Biogas yield per kg VS (Nm³/kg VS) via Chen-Hashimoto kinetics
        y_nm3_per_kg_vs = _chen_hashimoto(
            row["y0_nm3_kg"], self._hrt, _DEFAULT_MU, _DEFAULT_K
        )

        # Total daily biogas (Nm³/day)
        biogas_m3_d = vs_kg_d * y_nm3_per_kg_vs

        return {
            "total_mass_kg_d": round(total_mass_kg_d, 4),
            "dry_matter_kg_d": round(dry_matter_kg_d, 4),
            "biogas_m3_d":     round(biogas_m3_d, 4),
        }
