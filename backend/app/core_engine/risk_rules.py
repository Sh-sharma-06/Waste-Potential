from typing import List


def guardrails(
    ch4_per_vs: float,
    buswell_bound_val: float,
    vs_destruction: float,
    net_electricity_val: float,
) -> List[str]:
    """Checks for physical limits and guardrail violations in the B1 engine."""
    warnings = []

    if ch4_per_vs > buswell_bound_val:
        warnings.append(
            f"WARNING: CH4 yield ({ch4_per_vs}) exceeds theoretical Buswell ceiling ({buswell_bound_val})."
        )

    if vs_destruction > 0.85:
        warnings.append(
            f"WARNING: Implied volatile solids destruction ({vs_destruction * 100}%) exceeds safe biological limit (85%)."
        )

    if net_electricity_val <= 0:
        warnings.append(
            "WARNING: Net electricity generation is zero or negative. System is running at an energy deficit."
        )

    return warnings
