"""Feedstock dataclass for waste-to-energy pathway analysis.

All fraction fields are dimensionless (kg/kg of total wet mass) and must sum to 1.0
within a tolerance of 1e-6.  ``moisture_fraction`` is on a wet basis.
``lhv_dry_mj_per_kg`` is the lower heating value of the dry fraction (MJ/kg dry).
``lhv_wet_mj_per_kg()`` applies the wet-basis correction:
    lhv_wet = lhv_dry * (1 - w) - 2.44 * w
where w is the moisture fraction and 2.44 MJ/kg is the latent heat of vaporisation
of water at 25 °C.  The result is floored at 0 (non-combustible wet materials).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Feedstock:
    """Characterisation of a waste feedstock stream.

    Parameters
    ----------
    total_mass_kg_d:
        Total incoming mass flow (kg/d, wet basis).  Must be >= 0.
    organic_fraction:
        Organics (food, garden waste, etc.) as fraction of total wet mass.
    plastic_fraction:
        Plastics as fraction of total wet mass.
    paper_fraction:
        Paper/cardboard as fraction of total wet mass.
    other_fraction:
        All remaining material as fraction of total wet mass.
        The four fractions (organic, plastic, paper, other) must sum to 1.0.
    moisture_fraction:
        Water content on a wet basis (kg water / kg wet feedstock).
    ash_fraction_dry:
        Inorganic ash as fraction of the dry feedstock mass.
    lhv_dry_mj_per_kg:
        Lower heating value of the dry (moisture-free) feedstock (MJ/kg dry).
    contamination_pct:
        Contamination level as a percentage (0–100).
    """

    total_mass_kg_d: float
    organic_fraction: float
    plastic_fraction: float
    paper_fraction: float
    other_fraction: float
    moisture_fraction: float
    ash_fraction_dry: float
    lhv_dry_mj_per_kg: float
    contamination_pct: float

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def __post_init__(self) -> None:
        # Non-negative masses/LHV
        if self.total_mass_kg_d < 0:
            raise ValueError(
                f"total_mass_kg_d must be >= 0; got {self.total_mass_kg_d}"
            )
        if self.lhv_dry_mj_per_kg < 0:
            raise ValueError(
                f"lhv_dry_mj_per_kg must be >= 0; got {self.lhv_dry_mj_per_kg}"
            )

        # [0, 1] fraction checks
        _FRACTION_FIELDS = {
            "organic_fraction": self.organic_fraction,
            "plastic_fraction": self.plastic_fraction,
            "paper_fraction": self.paper_fraction,
            "other_fraction": self.other_fraction,
            "moisture_fraction": self.moisture_fraction,
            "ash_fraction_dry": self.ash_fraction_dry,
        }
        for name, val in _FRACTION_FIELDS.items():
            if not (0.0 <= val <= 1.0):
                raise ValueError(
                    f"{name} must be in [0, 1]; got {val}"
                )

        # contamination_pct in [0, 100]
        if not (0.0 <= self.contamination_pct <= 100.0):
            raise ValueError(
                f"contamination_pct must be in [0, 100]; got {self.contamination_pct}"
            )

        # Composition fractions must sum to 1
        composition_sum = (
            self.organic_fraction
            + self.plastic_fraction
            + self.paper_fraction
            + self.other_fraction
        )
        if abs(composition_sum - 1.0) > 1e-6:
            raise ValueError(
                f"organic_fraction + plastic_fraction + paper_fraction + "
                f"other_fraction must sum to 1.0 (got {composition_sum:.8f})"
            )

    # ------------------------------------------------------------------
    # Derived quantity
    # ------------------------------------------------------------------

    def lhv_wet_mj_per_kg(self) -> float:
        """Lower heating value on a wet basis (MJ/kg wet feedstock).

        Formula:
            lhv_wet = lhv_dry * (1 - w) - 2.44 * w

        where w is the moisture_fraction (wet basis) and 2.44 MJ/kg is the
        latent heat of vaporisation of water at 25 °C.  The result is floored
        at 0.0 because a negative heating value is physically meaningless for
        a combustion/gasification pathway assessment.
        """
        w = self.moisture_fraction
        return max(0.0, self.lhv_dry_mj_per_kg * (1.0 - w) - 2.44 * w)
