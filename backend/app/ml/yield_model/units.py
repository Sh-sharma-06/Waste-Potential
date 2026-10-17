"""Unit conversion utilities for biogas and methane yields.

Provides the single authoritative function converting yields across different mass bases
(fresh, total solids, volatile solids) to standard Nm3 biogas and CH4 per kg VS.
"""

from dataclasses import dataclass
from typing import Literal, Optional


@dataclass(frozen=True)
class ConvertedYield:
    """Standardized yield representation.

    All yields are strictly reported on a volatile-solids basis (Nm3 per kg VS).
    """
    y_biogas_nm3_per_kg_vs: float
    y_ch4_nm3_per_kg_vs: float
    basis: str = "per kg VS"


def convert_to_vs_yield(
    yield_value: float,
    from_basis: Literal["per_kg_vs", "per_kg_ts", "per_kg_fresh", "vs", "ts", "fresh"],
    ts_fraction: Optional[float] = None,
    vs_of_ts: Optional[float] = None,
    ch4_fraction: float = 0.60,
    gas_type: Literal["biogas", "ch4"] = "biogas"
) -> ConvertedYield:
    """Converts any yield (per kg fresh, TS, or VS) into Nm3 biogas and CH4 per kg VS.

    Mass basis relationships:
      - VS mass = Fresh mass * ts_fraction * vs_of_ts
      - VS mass = TS mass * vs_of_ts
      - Yield_per_VS = Yield_per_TS / vs_of_ts
      - Yield_per_VS = Yield_per_fresh / (ts_fraction * vs_of_ts)

    Args:
        yield_value: The numeric yield value (must be >= 0).
        from_basis: The mass basis of the input yield ('per_kg_vs', 'per_kg_ts', or 'per_kg_fresh').
        ts_fraction: Total solids fraction of fresh feedstock (0 < ts_fraction <= 1.0).
                     Required when from_basis is 'per_kg_fresh' or 'fresh'.
        vs_of_ts: Volatile solids fraction of total solids (0 < vs_of_ts <= 1.0).
                  Required when from_basis is 'per_kg_fresh', 'fresh', 'per_kg_ts', or 'ts'.
        ch4_fraction: Volumetric methane fraction in biogas (0 < ch4_fraction <= 1.0). Default is 0.60.
        gas_type: Whether yield_value is measured as 'biogas' or 'ch4'. Default is 'biogas'.

    Returns:
        ConvertedYield dataclass with:
          - y_biogas_nm3_per_kg_vs: float (Nm3 biogas / kg VS)
          - y_ch4_nm3_per_kg_vs: float (Nm3 CH4 / kg VS)
          - basis: "per kg VS"

    Raises:
        ValueError: If yield_value is negative, fractions are out of bounds,
                    required fractions for the basis are omitted, or unrecognized basis.
    """
    if yield_value < 0:
        raise ValueError(f"yield_value must be non-negative, got {yield_value}")

    if not (0.0 < ch4_fraction <= 1.0):
        raise ValueError(f"ch4_fraction must be in (0, 1.0], got {ch4_fraction}")

    basis_norm = from_basis.lower().strip()
    if basis_norm in ("per_kg_vs", "vs", "per_vs"):
        y_norm = float(yield_value)

    elif basis_norm in ("per_kg_ts", "ts", "per_ts"):
        if vs_of_ts is None:
            raise ValueError("vs_of_ts is required when converting from a TS basis")
        if not (0.0 < vs_of_ts <= 1.0):
            raise ValueError(f"vs_of_ts must be in (0, 1.0], got {vs_of_ts}")
        y_norm = yield_value / vs_of_ts

    elif basis_norm in ("per_kg_fresh", "fresh", "per_fresh"):
        if ts_fraction is None:
            raise ValueError("ts_fraction is required when converting from a fresh basis")
        if not (0.0 < ts_fraction <= 1.0):
            raise ValueError(f"ts_fraction must be in (0, 1.0], got {ts_fraction}")
        if vs_of_ts is None:
            raise ValueError("vs_of_ts is required when converting from a fresh basis")
        if not (0.0 < vs_of_ts <= 1.0):
            raise ValueError(f"vs_of_ts must be in (0, 1.0], got {vs_of_ts}")
        vs_fraction_of_fresh = ts_fraction * vs_of_ts
        y_norm = yield_value / vs_fraction_of_fresh

    else:
        raise ValueError(f"Unrecognized mass basis: '{from_basis}'. Must be per_kg_vs, per_kg_ts, or per_kg_fresh.")

    # Determine biogas and CH4 yields on VS basis
    if gas_type.lower() == "biogas":
        y_biogas = y_norm
        y_ch4 = y_biogas * ch4_fraction
    elif gas_type.lower() == "ch4":
        y_ch4 = y_norm
        y_biogas = y_ch4 / ch4_fraction
    else:
        raise ValueError(f"Unrecognized gas_type: '{gas_type}'. Must be 'biogas' or 'ch4'.")

    return ConvertedYield(
        y_biogas_nm3_per_kg_vs=y_biogas,
        y_ch4_nm3_per_kg_vs=y_ch4,
        basis="per kg VS"
    )
