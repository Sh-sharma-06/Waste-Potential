"""
params.py — Centralised parameter defaults for the B1 Science Core.

All 22 Params fields are operational inputs that callers may override.
Physics constants (LHV, Buswell coefficients) live as MODULE-LEVEL constants
below so they are not part of the parameter space that the API exposes.

Validation rules enforced in __post_init__:
  Fractions [0, 1]: organic_fraction, suitable_fraction, ts_fraction, vs_of_ts,
      target_ts, ch4_fraction, ch4_slip, availability, eta_el, eta_th, eta_boiler
  Non-negative: total_mass_kg_d, hrt_days, cp_kj_kg_k, u_wall_w_m2k,
      aux_mix_kwh_m3_d, aux_sort_kwh_t, aux_gas_kwh_nm3
  composition tuple: each element >= 0 and sum == 1 ± 1e-6
  eta_boiler > eta_th
  Temperatures (digester_temp_c, ambient_temp_c) are allowed to be negative.
  Physically implausible but numerically valid values (availability=0.0,
  y_biogas_nm3_per_kg_vs=1.5) are NOT rejected here — callers must issue
  warnings via guardrails.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

# ---------------------------------------------------------------------------
# Module-level physics constants (NOT Params fields)
# Source: Buswell & Mueller 1952; Angelidaki & Sanders 2004 (verify)
# ---------------------------------------------------------------------------
LHV_CH4: float = 9.94          # kWh / Nm³ CH4 at 0 °C, 1 atm
BUSWELL_CARB: float = 0.415     # Nm³ CH4 / kg VS  (carbohydrate C6H10O5)
BUSWELL_PROT: float = 0.496     # Nm³ CH4 / kg VS  (protein C5H7NO2)
BUSWELL_LIP: float = 1.014      # Nm³ CH4 / kg VS  (lipid C57H104O6)


@dataclass(frozen=True)
class Params:
    # ------------------------------------------------------------------ #
    # Feedstock mass flow                                                  #
    # ------------------------------------------------------------------ #
    total_mass_kg_d: float = 1000.0
    """Total fresh waste intake [kg/day]."""

    # ------------------------------------------------------------------ #
    # Feedstock characterisation                                          #
    # ------------------------------------------------------------------ #
    organic_fraction: float = 0.45
    """Organic (biodegradable) fraction of total fresh waste [0-1]."""

    suitable_fraction: float = 0.80
    """Fraction of organic waste suitable for anaerobic digestion [0-1]."""

    ts_fraction: float = 0.27
    """Total solids content of fresh feedstock [kg TS / kg fresh, 0-1]."""

    vs_of_ts: float = 0.88
    """Volatile solids as fraction of total solids [kg VS / kg TS, 0-1]."""

    target_ts: float = 0.10
    """Target TS concentration in digester feed slurry [0-1]."""

    # ------------------------------------------------------------------ #
    # Biogas / methane yield                                              #
    # ------------------------------------------------------------------ #
    y_biogas_nm3_per_kg_vs: float = 0.55
    """Biogas yield per kg VS destroyed [Nm³/kg VS]."""

    ch4_fraction: float = 0.60
    """Volumetric CH4 fraction in raw biogas [0-1]."""

    ch4_slip: float = 0.015
    """Methane slip (fugitive loss) fraction of produced CH4 [0-1]."""

    # ------------------------------------------------------------------ #
    # Plant operating conditions                                          #
    # ------------------------------------------------------------------ #
    availability: float = 0.90
    """Plant annual availability / load factor [0-1]."""

    # ------------------------------------------------------------------ #
    # CHP / boiler efficiencies                                           #
    # ------------------------------------------------------------------ #
    eta_el: float = 0.35
    """CHP electrical efficiency (fraction of gross biogas energy) [0-1]."""

    eta_th: float = 0.45
    """CHP thermal recovery efficiency (fraction of gross biogas energy) [0-1]."""

    eta_boiler: float = 0.90
    """Auxiliary boiler thermal efficiency [0-1]. Must be > eta_th."""

    # ------------------------------------------------------------------ #
    # Thermal / digester conditions                                       #
    # ------------------------------------------------------------------ #
    digester_temp_c: float = 37.0
    """Mesophilic digestion target temperature [°C]. May be negative."""

    ambient_temp_c: float = 25.0
    """Ambient (incoming feed) temperature [°C]. May be negative."""

    hrt_days: float = 30.0
    """Hydraulic retention time [days]."""

    # ------------------------------------------------------------------ #
    # Heat-transfer / thermodynamic constants                             #
    # ------------------------------------------------------------------ #
    cp_kj_kg_k: float = 4.0
    """Specific heat capacity of feedstock slurry [kJ / kg·K]."""

    u_wall_w_m2k: float = 0.5
    """Overall heat-transfer coefficient for digester vessel wall [W / m²·K]."""

    # ------------------------------------------------------------------ #
    # Auxiliary energy draws                                              #
    # ------------------------------------------------------------------ #
    aux_mix_kwh_m3_d: float = 0.15
    """Mixing parasitic energy per m³ of digester volume per day [kWh / m³/day]."""

    aux_sort_kwh_t: float = 5.0
    """Pre-sorting / pre-treatment energy per tonne of fresh waste [kWh / t]."""

    aux_gas_kwh_nm3: float = 0.02
    """Gas handling / compression energy per Nm³ of biogas [kWh / Nm³]."""

    # ------------------------------------------------------------------ #
    # Biochemical composition of VS (carbs, protein, lipid fractions)    #
    # ------------------------------------------------------------------ #
    composition: Tuple[float, float, float] = (0.6, 0.2, 0.2)
    """Mass fractions of VS as (carbohydrates, protein, lipid).
    Must sum to 1 ± 1e-6."""

    # ------------------------------------------------------------------ #
    # Validation                                                          #
    # ------------------------------------------------------------------ #
    def __post_init__(self) -> None:
        _fractions = {
            "organic_fraction":  self.organic_fraction,
            "suitable_fraction": self.suitable_fraction,
            "ts_fraction":       self.ts_fraction,
            "vs_of_ts":          self.vs_of_ts,
            "target_ts":         self.target_ts,
            "ch4_fraction":      self.ch4_fraction,
            "ch4_slip":          self.ch4_slip,
            "availability":      self.availability,
            "eta_el":            self.eta_el,
            "eta_th":            self.eta_th,
            "eta_boiler":        self.eta_boiler,
        }
        for name, val in _fractions.items():
            if not (0.0 <= val <= 1.0):
                raise ValueError(f"Params.{name} must be in [0, 1]; got {val}")

        _non_neg = {
            "total_mass_kg_d":   self.total_mass_kg_d,
            "hrt_days":          self.hrt_days,
            "cp_kj_kg_k":        self.cp_kj_kg_k,
            "u_wall_w_m2k":      self.u_wall_w_m2k,
            "aux_mix_kwh_m3_d":  self.aux_mix_kwh_m3_d,
            "aux_sort_kwh_t":    self.aux_sort_kwh_t,
            "aux_gas_kwh_nm3":   self.aux_gas_kwh_nm3,
        }
        for name, val in _non_neg.items():
            if val < 0.0:
                raise ValueError(f"Params.{name} must be >= 0; got {val}")

        if self.eta_boiler <= self.eta_th:
            raise ValueError(
                f"Params.eta_boiler ({self.eta_boiler}) must be > eta_th ({self.eta_th})"
            )

        comp_sum = sum(self.composition)
        if abs(comp_sum - 1.0) > 1e-6:
            raise ValueError(
                f"Params.composition must sum to 1 (±1e-6); got {comp_sum:.8f}"
            )
        for i, v in enumerate(self.composition):
            if v < 0.0:
                raise ValueError(
                    f"Params.composition[{i}] must be >= 0; got {v}"
                )
