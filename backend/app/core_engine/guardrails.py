"""
guardrails.py — Pure-function safety and stoichiometric checks for B1 Science Core.

All functions are side-effect-free.  None of them mutate state or raise on
out-of-range inputs (except buswell_bound on bad composition sum, and
parse_formula on unknown element / empty input — both are programming errors).

MODEL ASSUMPTION CONSTANTS are clearly labelled; they are calibrated to
typical mesophilic wet-AD of municipal organic waste and must be reviewed
before applying to other process configurations.
"""

from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Union

# ---------------------------------------------------------------------------
# Buswell stoichiometric coefficients (module-level constants, not Params fields)
# Source: Buswell & Mueller (1952); verified by Angelidaki & Sanders (2004).
# Derived from representative molecular formulas: C6H10O5, C5H7NO2, C57H104O6.
# ---------------------------------------------------------------------------
_BUSWELL_CARB: float = 0.415    # Nm³ CH4/kg VS  (carbohydrate)
_BUSWELL_PROT: float = 0.496    # Nm³ CH4/kg VS  (protein)
_BUSWELL_LIP: float = 1.014     # Nm³ CH4/kg VS  (lipid)

# MODEL ASSUMPTION: maximum fraction of VS biologically destroyed in a
# single-stage mesophilic AD system.  Literature range 0.60–0.90; 0.85 chosen.
_VS_DESTRUCTION_LIMIT: float = 0.85

# Molar volume of ideal gas at 0 °C, 1 atm [Nm³/mol]
_NM3_PER_MOL: float = 22.414e-3


# ===========================================================================
# 1. Buswell weighted bound
# ===========================================================================

def buswell_bound(
    composition: Union[Tuple[float, float, float], Dict[str, float]],
    coeffs: Tuple[float, float, float] = (_BUSWELL_CARB, _BUSWELL_PROT, _BUSWELL_LIP),
) -> float:
    """Return theoretical maximum CH4 yield [Nm³ / kg VS].

    Parameters
    ----------
    composition:
        Either a 3-tuple ``(carbs_fraction, protein_fraction, lipid_fraction)``
        or a dict with keys ``'carbs'``, ``'protein'``, ``'lipid'``.
        Fractions must sum to 1 ± 1e-6.
    coeffs:
        Buswell coefficients (carb, protein, lipid) in Nm³ CH4/kg VS.

    Raises
    ------
    ValueError
        If fractions do not sum to 1 ± 1e-6.
    """
    if isinstance(composition, dict):
        carbs   = composition.get("carbs", 0.0)
        protein = composition.get("protein", 0.0)
        lipid   = composition.get("lipid", 0.0)
    else:
        carbs, protein, lipid = composition

    total = carbs + protein + lipid
    if abs(total - 1.0) > 1e-6:
        raise ValueError(
            f"buswell_bound: composition fractions must sum to 1 (±1e-6); got {total:.8f}."
        )

    return carbs * coeffs[0] + protein * coeffs[1] + lipid * coeffs[2]


# ===========================================================================
# 2. Methane yield ceiling check
# ===========================================================================

def check_methane_yield(ch4_per_vs: float, bound: float) -> Optional[str]:
    """Return a warning string if ``ch4_per_vs`` exceeds the Buswell ceiling,
    else ``None``.  Exactly equal to bound is NOT a warning.
    """
    if ch4_per_vs > bound:
        return (
            f"WARNING: CH4 yield {ch4_per_vs:.4f} Nm³/kg VS exceeds the "
            f"theoretical Buswell ceiling {bound:.4f} Nm³/kg VS. "
            "Check feedstock composition or measurement accuracy."
        )
    return None


# ===========================================================================
# 3. VS destruction fraction check
# ===========================================================================

def check_vs_destruction(
    biogas_kg: float,
    vs_kg: float,
    limit: float = _VS_DESTRUCTION_LIMIT,  # MODEL ASSUMPTION
) -> Optional[str]:
    """Return a warning string if implied VS destruction > *limit*, else ``None``.

    ``vs_kg == 0`` silently returns ``None`` (avoids division by zero).
    *limit* is a MODEL ASSUMPTION (default 0.85).  Strictly greater than the
    limit triggers the warning.
    """
    if vs_kg == 0.0:
        return None
    destruction = biogas_kg / vs_kg
    if destruction > limit:
        return (
            f"WARNING: Implied VS destruction fraction {destruction:.4f} "
            f"({destruction * 100:.1f}%) exceeds the MODEL ASSUMPTION limit of "
            f"{limit * 100:.1f}%. "
            "Verify biogas measurement or feedstock VS content."
        )
    return None


# ===========================================================================
# 4. Input range checks (extrapolation flags — never raise)
# ===========================================================================

# MODEL ASSUMPTIONS: operational ranges for which the B1 kinetic model has
# been calibrated.  Values outside these ranges are extrapolations and may
# reduce accuracy.  These are NOT universal physical limits.
# Keys must match Params field names exactly.
SUPPORTED_RANGES: Dict[str, Tuple[float, float]] = {
    "ts_fraction":      (0.10, 0.40),   # Total-solids fraction of feed slurry
    "hrt_days":         (10.0, 60.0),   # Hydraulic retention time [days]
    "digester_temp_c":  (30.0, 60.0),   # Digester operating temperature [°C]
    "ch4_fraction":     (0.45, 0.75),   # Volumetric CH4 fraction in biogas
    "organic_fraction": (0.0,  1.0),    # Organic fraction of total waste
}


def check_input_ranges(
    params: Union[Dict[str, float], object],
) -> List[Tuple[str, float, float, float]]:
    """Return a list of ``(field, value, low, high)`` for values outside range.

    Accepts a ``Params`` dataclass instance or a plain dict.  Non-numeric
    values are silently skipped.  Unknown keys are silently ignored.
    Never raises.

    Parameters
    ----------
    params:
        A Params dataclass instance or a dict of ``{field_name: value}``.

    Returns
    -------
    list of (field, value, low, high)
        Empty list means all supplied parameters are within range.
    """
    if dataclasses.is_dataclass(params) and not isinstance(params, type):
        mapping: Dict = dataclasses.asdict(params)  # type: ignore[arg-type]
    else:
        mapping = dict(params)  # type: ignore[call-overload]

    out_of_range: List[Tuple[str, float, float, float]] = []
    for field, value in mapping.items():
        if field not in SUPPORTED_RANGES:
            continue
        if not isinstance(value, (int, float)):
            continue
        low, high = SUPPORTED_RANGES[field]
        if not (low <= value <= high):
            out_of_range.append((field, float(value), low, high))
    return out_of_range


# ===========================================================================
# 5. Formula string parser
# ===========================================================================

_KNOWN_ELEMENTS = {"C", "H", "O", "N", "S"}

# Matches one element token: uppercase letter optionally followed by lowercase
# letters (for two-letter symbols not used here, but parsed defensively),
# then an optional integer count.
_FORMULA_RE = re.compile(r"([A-Z][a-z]*)(\d*)")


def parse_formula(formula: str) -> "MolecularFormula":
    """Parse a molecular formula string into a :class:`MolecularFormula`.

    Recognised elements: C, H, O, N, S (case-sensitive).  Any other element
    symbol raises ``ValueError``.  Empty input raises ``ValueError``.

    Examples
    --------
    >>> parse_formula("C6H10O5")
    MolecularFormula(c=6, h=10, o=5, n=0.0, s=0.0)
    >>> parse_formula("C5H7NO2")
    MolecularFormula(c=5, h=7, o=2, n=1.0, s=0.0)
    """
    if not formula or not formula.strip():
        raise ValueError("parse_formula: formula string must not be empty.")

    counts: Dict[str, float] = {el: 0.0 for el in _KNOWN_ELEMENTS}
    pos = 0
    for m in _FORMULA_RE.finditer(formula):
        if m.start() != pos:
            raise ValueError(
                f"parse_formula: unexpected characters in '{formula}' at position {pos}."
            )
        symbol = m.group(1)
        if symbol not in _KNOWN_ELEMENTS:
            raise ValueError(
                f"parse_formula: unknown element '{symbol}' in '{formula}'. "
                f"Recognised elements: {sorted(_KNOWN_ELEMENTS)}."
            )
        count_str = m.group(2)
        counts[symbol] += float(count_str) if count_str else 1.0
        pos = m.end()

    if pos != len(formula):
        raise ValueError(
            f"parse_formula: could not fully parse '{formula}' (stopped at pos {pos})."
        )
    if all(v == 0.0 for v in counts.values()):
        raise ValueError(f"parse_formula: no atoms found in '{formula}'.")

    return MolecularFormula(
        c=counts["C"], h=counts["H"], o=counts["O"],
        n=counts["N"], s=counts["S"],
    )


# ===========================================================================
# 6. Elemental stoichiometric balance (independent Buswell equation)
# ===========================================================================

@dataclass(frozen=True)
class MolecularFormula:
    """Atom counts for a molecule C_c H_h O_o N_n S_s."""
    c: float
    h: float
    o: float
    n: float = 0.0
    s: float = 0.0


# Representative molecular formulas — kept as objects for use by existing code.
FORMULA_CARB  = MolecularFormula(c=6,  h=10,  o=5, n=0, s=0)   # C6H10O5
FORMULA_PROT  = MolecularFormula(c=5,  h=7,   o=2, n=1, s=0)   # C5H7NO2
FORMULA_LIPID = MolecularFormula(c=57, h=104,  o=6, n=0, s=0)  # C57H104O6


def _ch4_moles(f: MolecularFormula) -> float:
    return f.c / 2 + f.h / 8 - f.o / 4 - 3 * f.n / 8 - f.s / 4


def _co2_moles(f: MolecularFormula) -> float:
    return f.c / 2 - f.h / 8 + f.o / 4 + 3 * f.n / 8 + f.s / 4


def _h2o_moles(f: MolecularFormula) -> float:
    return f.c - f.h / 4 - f.o / 2 + 3 * f.n / 4 + f.s / 2


def _molar_mass(f: MolecularFormula) -> float:
    return 12.011 * f.c + 1.008 * f.h + 15.999 * f.o + 14.007 * f.n + 32.06 * f.s


def atom_balance(formula: Union[str, MolecularFormula]) -> Dict[str, float]:
    """Compute elemental residuals for the general Buswell equation.

    Accepts either a formula string (e.g. ``"C6H10O5"``) or a
    :class:`MolecularFormula` instance.  All residuals should be < 1e-9 for a
    balanced reaction.

    Returns
    -------
    dict
        Keys ``'C'``, ``'H'``, ``'O'``, ``'N'``, ``'S'`` — residual
        (reactant atoms − product atoms).
    """
    f = parse_formula(formula) if isinstance(formula, str) else formula

    ch4   = _ch4_moles(f)
    co2   = _co2_moles(f)
    water = _h2o_moles(f)
    nh3   = f.n
    h2s   = f.s

    r_c = f.c
    r_h = f.h + 2 * water
    r_o = f.o + water
    r_n = f.n
    r_s = f.s

    p_c = ch4 + co2
    p_h = 4 * ch4 + 3 * nh3 + 2 * h2s
    p_o = 2 * co2
    p_n = nh3
    p_s = h2s

    return {
        "C": r_c - p_c,
        "H": r_h - p_h,
        "O": r_o - p_o,
        "N": r_n - p_n,
        "S": r_s - p_s,
    }


def theoretical_ch4_nm3_per_kg_vs(formula: Union[str, MolecularFormula]) -> float:
    """Return theoretical CH4 yield [Nm³ / kg VS].

    Accepts either a formula string (e.g. ``"C6H10O5"``) or a
    :class:`MolecularFormula` instance.  Uses the general Buswell equation and
    ideal-gas molar volume at 0 °C, 1 atm (22.414 L/mol).
    """
    f = parse_formula(formula) if isinstance(formula, str) else formula
    ch4_per_mol = _ch4_moles(f)
    mw = _molar_mass(f)
    return ch4_per_mol * _NM3_PER_MOL * 1000.0 / mw
