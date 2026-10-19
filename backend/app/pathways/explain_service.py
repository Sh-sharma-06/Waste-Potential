"""explain_service.py — Grounding guard and template builder for POST /pathways/explain.

Grounding guard
---------------
Extracts every number from a Gemini-generated text, then checks each against
the FACTS dict that was sent to the model.  A number is "supported" if it
matches any numeric FACTS value within 1 % (relative tolerance).  Any number
that cannot be traced back to FACTS is considered unsupported.

Template builder
----------------
Produces a deterministic, LLM-free explanation from FACTS when Gemini is
unavailable or its output fails the grounding check.
"""

from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------------------
# Number extraction
# ---------------------------------------------------------------------------

_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?")


def extract_numbers(text: str) -> list[float]:
    """Return all numeric literals found in *text* as floats."""
    return [float(m) for m in _NUMBER_RE.findall(text)]


# ---------------------------------------------------------------------------
# Grounding check (1 % relative tolerance)
# ---------------------------------------------------------------------------

_GROUNDING_TOLERANCE = 0.01   # 1 %


def _facts_numbers(facts: dict[str, Any]) -> list[float]:
    """Collect every numeric leaf value from a (possibly nested) FACTS dict."""
    result: list[float] = []
    for v in facts.values():
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v is not None:
            result.append(float(v))
        elif isinstance(v, dict):
            result.extend(_facts_numbers(v))
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, (int, float)) and not isinstance(item, bool):
                    result.append(float(item))
    return result


def _is_supported(number: float, fact_nums: list[float]) -> bool:
    """Return True if *number* matches any value in *fact_nums* within 1 %."""
    for f in fact_nums:
        if f == 0.0:
            if abs(number) < 1e-9:
                return True
        else:
            if abs(number - f) / abs(f) <= _GROUNDING_TOLERANCE:
                return True
    return False


def check_grounding(text: str, facts: dict[str, Any]) -> tuple[bool, list[float]]:
    """Check every number in *text* against *facts*.

    Returns
    -------
    (grounded, unsupported_numbers)
        *grounded* is True iff every number in the text is supported by FACTS.
        *unsupported_numbers* lists any numbers that could not be matched.
    """
    fact_nums = _facts_numbers(facts)
    text_nums = extract_numbers(text)
    unsupported = [n for n in text_nums if not _is_supported(n, fact_nums)]
    return (len(unsupported) == 0), unsupported


# ---------------------------------------------------------------------------
# Template builder
# ---------------------------------------------------------------------------

def build_template(pathway: str, facts: dict[str, Any]) -> str:
    """Return a short deterministic explanation built from *facts* alone."""
    feasible = facts.get("feasible", True)
    reasons = facts.get("reasons") or []
    e_net = facts.get("e_net_kwh_d")
    net_val = facts.get("annual_net_value_inr")
    opt_share = facts.get("optimality_share")
    primary = facts.get("primary_product", "energy")
    energy_basis = facts.get("energy_basis", "")
    warnings = facts.get("warnings") or []

    # Status sentence
    if not feasible:
        reason_text = "; ".join(reasons) if reasons else "unspecified constraint"
        status_line = (
            f"{pathway} is currently screened out ({reason_text})."
        )
    else:
        status_line = f"{pathway} passed the coarse feasibility screen."

    # Energy sentence
    energy_line = ""
    if e_net is not None:
        energy_label = "thermal output" if energy_basis == "thermal" else "net electricity"
        energy_line = (
            f"Its modelled {energy_label} is {e_net:.1f} kWh/d."
        )

    # Financial sentence
    financial_line = ""
    if net_val is not None:
        financial_line = (
            f"The illustrative annual net value is {net_val:.0f} INR/year."
        )

    # Optimality sentence
    opt_line = ""
    if opt_share is not None:
        pct = round(opt_share * 100, 1)
        opt_line = (
            f"In Monte Carlo screening it was optimal in {pct}% of runs."
        )

    # Warning snippet
    warn_line = ""
    if warnings:
        first_warn = warnings[0]
        # Truncate long warnings
        if len(first_warn) > 120:
            first_warn = first_warn[:117] + "..."
        warn_line = f"Note: {first_warn}"

    parts = [s for s in [status_line, energy_line, financial_line, opt_line, warn_line] if s]
    return (
        " ".join(parts)
        + " Ranking depends on assumed price and cost distributions and is not validated."
    )
