"""
P3 foundational data schema contracts for the Waste-Potential screening pipeline.

Three top-level schemas are defined here and shared across the data service layer
(app.data.service), the ML predictor (app.ml.predictor), and the pathways
screening layer (app.pathways).

Schema design rules:
  - Every numeric quantity on Feedstock and LocationContext carries an associated
    Metadata sub-object that records measurement provenance (measured / estimated),
    spatial or temporal resolution, and the source identifier.
  - Fraction fields on Feedstock must sum to 1.0 ±1 × 10⁻⁶ (root validator).
  - All schemas are immutable (frozen) to prevent accidental mutation after
    construction in service functions.

Part 2 additions (P3-B):
  - SinkEntry — a demand-side buyer that can absorb kWh/day of energy output.
  - LocationContext extended with ambient_temp_c, relative_humidity,
    rainfall_mm_d (Open-Meteo style weather defaults) and a sinks list.
"""

from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


# ===========================================================================
# Metadata — attached to every measured / estimated scalar
# ===========================================================================

class Metadata(BaseModel, frozen=True):
    """Provenance descriptor attached to individual measured or estimated values.

    Attributes
    ----------
    kind:
        ``"measured"`` — value was directly measured (sensor, lab, survey).
        ``"estimated"`` — value was derived, modelled, or set to a documented
        default.
    resolution:
        Temporal or spatial resolution of the underlying measurement, e.g.
        ``"daily"``, ``"monthly_avg"``, ``"point"``, ``"1km_grid"``.
        Use ``"n/a"`` for defaults that carry no spatial or temporal meaning.
    source_id:
        Identifier of the data source, model version, or document from which
        the value was obtained.  Defaults must use ``"default_v1"`` so that
        any future calibration run can locate and supersede them.
    """

    kind: Literal["measured", "reported", "estimated", "simulated"]
    resolution: str
    source_id: str


# ---------------------------------------------------------------------------
# Shared default Metadata instances for service-layer defaults
# ---------------------------------------------------------------------------

_DEFAULT_META = Metadata(
    kind="estimated",
    resolution="n/a",
    source_id="default_v1",
)

_MEASURED_DAILY = Metadata(
    kind="measured",
    resolution="daily",
    source_id="sensor_v1",
)


# ===========================================================================
# Feedstock — characterisation of a single waste stream
# ===========================================================================

class FeedstockField(BaseModel, frozen=True):
    """A single numeric feedstock measurement bundled with its provenance.

    Attributes
    ----------
    value:
        The numeric quantity.
    meta:
        Provenance descriptor.
    """

    value: float
    meta: Metadata


class Feedstock(BaseModel, frozen=True):
    """Characterisation of a waste feedstock arriving at a treatment facility.

    All mass-fraction fields (``organic_fraction``, ``plastic_fraction``,
    ``paper_fraction``, ``other_fraction``, ``lignocellulosic_fraction``) must
    sum to 1.0 within a tolerance of 1 × 10⁻⁶.  The validator checks the
    ``.value`` attribute of each.

    Attributes
    ----------
    total_mass_kg_d:
        Total incoming waste mass in kg per day.
    category:
        Categorical label for the feedstock type, e.g. ``"mixed"``,
        ``"agricultural"``, ``"municipal"``.  Used by P2's ML yield engine for
        stream classification.  Defaults to ``"mixed"``.
    organic_fraction:
        Mass fraction of organic / biodegradable material (0–1).
    plastic_fraction:
        Mass fraction of plastics (0–1).
    paper_fraction:
        Mass fraction of paper / cardboard (0–1).
    other_fraction:
        Mass fraction of all other materials (0–1).
    lignocellulosic_fraction:
        Mass fraction of lignocellulosic biomass (straw, wood chips, crop
        residues; 0–1).  Required by the Torrefaction pathway physics engine.
        Defaults to 0.0 so existing stream dicts that omit the field remain
        valid.
    moisture_fraction:
        As-received moisture content (0–1).
    ash_fraction_dry:
        Ash content on a dry-matter basis (0–1).
    lhv_dry_mj_per_kg:
        Lower heating value on a dry basis (MJ/kg).
    contamination_pct:
        Percentage of the stream that is non-processable contamination (0–100).
    """

    total_mass_kg_d: FeedstockField = Field(
        ..., description="Total daily waste throughput (kg/day)."
    )
    category: str = Field(
        "",
        description="Categorical label for the feedstock type "
                    "(e.g. 'mixed', 'agricultural', 'municipal'). "
                    "Empty string when unknown — the ML engine will reject "
                    "uncategorised streams with a 422 error.",
    )
    organic_fraction: FeedstockField = Field(
        ..., description="Organic / biodegradable mass fraction (0–1)."
    )
    plastic_fraction: FeedstockField = Field(
        ..., description="Plastic mass fraction (0–1)."
    )
    paper_fraction: FeedstockField = Field(
        ..., description="Paper / cardboard mass fraction (0–1)."
    )
    other_fraction: FeedstockField = Field(
        ..., description="All other materials mass fraction (0–1)."
    )
    lignocellulosic_fraction: FeedstockField = Field(
        default_factory=lambda: FeedstockField(
            value=0.0,
            meta=Metadata(kind="estimated", resolution="n/a", source_id="default_v1"),
        ),
        description="Lignocellulosic biomass mass fraction (0–1). "
                    "Used by the Torrefaction pathway physics engine.",
    )
    organic_moisture_fraction: FeedstockField = Field(
        default_factory=lambda: FeedstockField(
            value=0.73,
            # Unsourced placeholder — no measured/reported data available at P1 scope.
            # Corresponds to ts_fraction = 1.0 − 0.73 = 0.27, which matches Params() default.
            meta=Metadata(kind="estimated", resolution="n/a", source_id="placeholder_general"),
        ),
        description="Moisture fraction of the organic component (0–1). "
                    "Unsourced placeholder (kind='estimated', source_id='placeholder_general'). "
                    "Used by the AD digester total-solids calculation: ts_fraction = 1 − value.",
    )
    moisture_fraction: FeedstockField = Field(
        ..., description="As-received moisture content (0–1)."
    )
    ash_fraction_dry: FeedstockField = Field(
        ..., description="Ash content on dry basis (0–1)."
    )
    lhv_dry_mj_per_kg: FeedstockField = Field(
        ..., description="Lower heating value, dry basis (MJ/kg)."
    )
    contamination_pct: FeedstockField = Field(
        ..., description="Non-processable contamination percentage (0–100)."
    )

    @model_validator(mode="after")
    def _fractions_sum_to_one(self) -> "Feedstock":
        """Ensure organic + plastic + paper + other + lignocellulosic == 1.0 ±1e-6."""
        total = (
            self.organic_fraction.value
            + self.plastic_fraction.value
            + self.paper_fraction.value
            + self.other_fraction.value
            + self.lignocellulosic_fraction.value
        )
        if not math.isclose(total, 1.0, abs_tol=1e-6):
            raise ValueError(
                f"Feedstock composition fractions must sum to 1.0; "
                f"got organic={self.organic_fraction.value}, "
                f"plastic={self.plastic_fraction.value}, "
                f"paper={self.paper_fraction.value}, "
                f"other={self.other_fraction.value}, "
                f"lignocellulosic={self.lignocellulosic_fraction.value} "
                f"(sum={total:.8f})."
            )
        return self


# ===========================================================================
# LocationContext — site-level economic and logistical parameters
# ===========================================================================

class LocationScalarField(BaseModel, frozen=True):
    """A single numeric location-context value bundled with its provenance.

    Attributes
    ----------
    value:
        The numeric quantity.
    meta:
        Provenance descriptor.
    """

    value: float
    meta: Metadata


class FacilityEntry(BaseModel, frozen=True):
    """A single treatment facility available to a given location.

    Attributes
    ----------
    pathway:
        Treatment pathway identifier, e.g. ``"anaerobic_digestion"``.
    capacity_t_d:
        Design throughput capacity in tonnes per day.
    road_km:
        One-way road distance from the source location to this facility (km).
    """

    pathway: str
    capacity_t_d: float = Field(..., ge=0.0)
    road_km: float = Field(..., ge=0.0)


class SinkEntry(BaseModel, frozen=True):
    """A demand-side energy buyer (sink) that can absorb supply from a pathway.

    Attributes
    ----------
    customer_class:
        High-level classification of the buyer, e.g. ``"industrial"``,
        ``"residential"``, ``"agricultural"``.
    accepts:
        List of energy or product types this sink will purchase, e.g.
        ``["electricity", "heat"]`` or ``["biogas"]``.
    demand_kwh_d:
        Maximum daily demand the sink can absorb (kWh/day).  Must be ≥ 0.
    road_km:
        One-way road distance from the supply site to this sink (km).
    price:
        Price the sink pays per kWh (INR/kWh).  Used by the greedy matcher
        to maximise revenue.  Must be ≥ 0.
    """

    customer_class: str
    accepts: list[str]
    demand_kwh_d: float = Field(..., ge=0.0)
    road_km: float = Field(..., ge=0.0)
    price: float = Field(..., ge=0.0)


class LocationContext(BaseModel, frozen=True):
    """Site-level economic, environmental, and logistical context for a location.

    All scalar economic and weather fields carry a ``Metadata`` provenance
    object.

    Attributes
    ----------
    electricity_tariff_inr_per_kwh:
        Prevailing electricity buy / sell tariff in INR per kWh.
    compost_price_inr_per_kg:
        Local market price for compost in INR per kg.
    heat_price_inr_per_kwh:
        Local market price for thermal energy (district heat / process steam)
        in INR per kWh.
    grid_available:
        ``True`` if the site has a reliable grid connection for electricity
        import / export.
    facilities:
        List of nearby treatment facilities with pathway, capacity, and road
        distance.
    ambient_temp_c:
        Ambient air temperature (°C).  Used by the AD kinetic model to
        adjust digester performance.
    relative_humidity:
        Relative humidity (0–1).  Used for composting aerobic efficiency
        estimates.
    rainfall_mm_d:
        Mean daily rainfall (mm/day).  Used for open-air pathway feasibility
        checks.
    sinks:
        Demand-side buyers that can absorb energy / product output from
        treatment pathways.
    """

    electricity_tariff_inr_per_kwh: LocationScalarField = Field(
        ..., description="Electricity tariff INR/kWh."
    )
    compost_price_inr_per_kg: LocationScalarField = Field(
        ..., description="Compost market price INR/kg."
    )
    heat_price_inr_per_kwh: LocationScalarField = Field(
        ..., description="Thermal energy price INR/kWh."
    )
    grid_available: bool = Field(
        ..., description="True if grid connection is available."
    )
    facilities: list[FacilityEntry] = Field(
        default_factory=list,
        description="Nearby treatment facilities with pathway, capacity, and distance.",
    )
    ambient_temp_c: LocationScalarField = Field(
        ..., description="Ambient air temperature (°C)."
    )
    relative_humidity: LocationScalarField = Field(
        ..., description="Relative humidity (0–1)."
    )
    rainfall_mm_d: LocationScalarField = Field(
        ..., description="Mean daily rainfall (mm/day)."
    )
    sinks: list[SinkEntry] = Field(
        default_factory=list,
        description="Demand-side buyers for energy / product output.",
    )
