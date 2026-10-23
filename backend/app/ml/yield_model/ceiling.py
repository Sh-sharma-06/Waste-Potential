"""Buswell methane ceiling for compositions that include a lignin share.

Lignin is treated as non-degradable, so it contributes zero. The ceiling is a
METHANE bound in Nm3 CH4 per kg VS; apply it before any biogas conversion.
Coefficients live in app.core_engine.engine (single source of truth).
"""

from app.core_engine.engine import buswell_bound


def ceiling_with_lignin(carb: float, protein: float, lipid: float, lignin: float = 0.0) -> float:
    """Return the Buswell methane ceiling per kg VS, with lignin contributing zero.

    All four shares are fractions of VS and must sum to 1 within 1e-6.

    Raises:
        ValueError: if lignin is outside [0, 1), any share is negative, the
                    shares do not sum to 1 within 1e-6, or carb+protein+lipid is zero.
    """
    if not (0.0 <= lignin < 1.0):
        raise ValueError(f"lignin must be in [0, 1), got {lignin}")
    if min(carb, protein, lipid) < 0.0:
        raise ValueError("carb, protein and lipid must be non-negative")
    if abs(carb + protein + lipid + lignin - 1.0) > 1e-6:
        raise ValueError("carb + protein + lipid + lignin must sum to 1 within 1e-6")

    # Scale the degradable shares to sum to exactly 1 for buswell_bound, then
    # scale the result back, so lignin contributes zero.
    s = carb + protein + lipid
    if s <= 0.0:
        raise ValueError("carb + protein + lipid must be greater than zero")
    return buswell_bound((carb / s, protein / s, lipid / s)) * s