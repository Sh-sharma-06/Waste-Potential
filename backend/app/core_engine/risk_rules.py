"""
risk_rules.py — Structured operational risk rules for the B1 Science Core.

Produces typed RuleWarning objects derived strictly from engine result numbers.
Never parses warning strings.  Never asserts universal safety limits.
Never diagnoses a real incident — all outputs are model-based explanations only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, List, Optional

# Import the VS destruction limit constant from guardrails (single source of truth).
from app.core_engine.guardrails import _VS_DESTRUCTION_LIMIT as _VS_LIMIT

_VALID_SEVERITIES = {"info", "warning", "critical"}
_VALID_BASES = {"engine_rule", "model_assumption", "documented"}

# Keys that must be present and non-None for a result dict to be complete.
_REQUIRED_KEYS = ("organic_kg_d", "suitable_kg_d", "e_net_kwh_d")


# ---------------------------------------------------------------------------
# RuleWarning dataclass
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RuleWarning:
    """A single structured operational risk finding.

    Attributes
    ----------
    code:
        Short machine-readable identifier (e.g. ``"NEG_NET"``).
    severity:
        One of ``"info"``, ``"warning"``, ``"critical"``.
    stage:
        Process stage to which this finding applies.
    message:
        Plain-language explanation for a human reader.
    basis:
        Source of the rule: ``"engine_rule"`` (derived from physics equations),
        ``"model_assumption"`` (calibrated threshold), or ``"documented"``
        (from a published reference).
    """
    code: str
    severity: str
    stage: str
    message: str
    basis: str

    def __post_init__(self) -> None:
        if self.severity not in _VALID_SEVERITIES:
            raise ValueError(
                f"RuleWarning.severity must be one of {_VALID_SEVERITIES}; "
                f"got '{self.severity}'."
            )
        if self.basis not in _VALID_BASES:
            raise ValueError(
                f"RuleWarning.basis must be one of {_VALID_BASES}; "
                f"got '{self.basis}'."
            )


# ---------------------------------------------------------------------------
# 1. stage_risks — static explanatory catalogue
# ---------------------------------------------------------------------------

def stage_risks() -> List[Dict[str, str]]:
    """Return a list of 8 dicts describing potential issues at each AD stage.

    Each dict has keys ``stage``, ``potential_issue``, ``explanation``.
    These are model-level explanations of what could go wrong at each step;
    they are not a safety system and do not replace operational procedures.
    """
    return [
        {
            "stage": "reception",
            "potential_issue": "Unexpected contamination",
            "explanation": (
                "Incoming waste may contain non-biodegradable or hazardous materials "
                "that differ from the assumed feedstock composition. "
                "This is a model explanation of a potential deviation, not a safety system."
            ),
        },
        {
            "stage": "sorting",
            "potential_issue": "Excessive rejected material",
            "explanation": (
                "A higher-than-modelled rejection rate reduces the suitable fraction "
                "and therefore lowers biogas yield and net energy output. "
                "This is a model explanation of a potential deviation, not a safety system."
            ),
        },
        {
            "stage": "conditioning",
            "potential_issue": "Wrong feedstock assumptions",
            "explanation": (
                "If the actual total-solids or volatile-solids content differs from "
                "the model defaults, the water-conditioning calculation will be "
                "inaccurate and the digester may receive slurry outside its design range. "
                "This is a model explanation of a potential deviation, not a safety system."
            ),
        },
        {
            "stage": "digestion",
            "potential_issue": "Biological instability",
            "explanation": (
                "Operating outside the supported temperature or HRT range may reduce "
                "microbial activity and cause volatile-fatty-acid accumulation, "
                "suppressing methanogenesis. "
                "This is a model explanation of a potential deviation, not a safety system."
            ),
        },
        {
            "stage": "gas collection",
            "potential_issue": "Gas leakage",
            "explanation": (
                "Uncontrolled methane losses (slip) beyond the modelled ch4_slip fraction "
                "reduce usable energy and increase greenhouse-gas emissions. "
                "This is a model explanation of a potential deviation, not a safety system."
            ),
        },
        {
            "stage": "gas treatment",
            "potential_issue": "Poor gas quality",
            "explanation": (
                "If the CH4 fraction in raw biogas is below the assumed range, "
                "the CHP unit may operate inefficiently or not at all. "
                "This is a model explanation of a potential deviation, not a safety system."
            ),
        },
        {
            "stage": "electricity generation",
            "potential_issue": "Downtime or low efficiency",
            "explanation": (
                "The model assumes a fixed availability factor; unplanned outages or "
                "CHP efficiency below the eta_el assumption will reduce gross electricity "
                "output and may push net generation negative. "
                "This is a model explanation of a potential deviation, not a safety system."
            ),
        },
        {
            "stage": "digestate",
            "potential_issue": "Unsuitable quality",
            "explanation": (
                "Heavy-metal or pathogen levels in digestate depend on feedstock quality "
                "and are not modelled here; the engine only tracks mass and energy flows. "
                "This is a model explanation of a potential deviation, not a safety system."
            ),
        },
    ]


# ---------------------------------------------------------------------------
# 2. rule_warnings — derive RuleWarnings from result dict numbers
# ---------------------------------------------------------------------------

def rule_warnings(
    result: Dict[str, Any],
    extrapolation_flag: bool = False,
    contamination_pct: Optional[float] = None,
    contamination_threshold_pct: Optional[float] = None,
) -> List[RuleWarning]:
    """Derive structured risk warnings from engine result numbers.

    Parameters
    ----------
    result:
        The dict returned by ``engine.simulate()``.
    extrapolation_flag:
        Set True when the ML layer signals the input is outside its training
        domain (triggers ML_EXTRAPOLATION warning).
    contamination_pct:
        Measured contamination percentage of incoming waste.  A warning is
        issued ONLY when both this and ``contamination_threshold_pct`` are
        supplied and ``contamination_pct > contamination_threshold_pct``.
    contamination_threshold_pct:
        Site-specific contamination acceptance threshold (same units as
        ``contamination_pct``).

    Returns
    -------
    list[RuleWarning]
        May be empty.  Order: MISSING_INPUT first (if triggered), then the
        remaining rules in code order.
    """
    w: List[RuleWarning] = []

    # -- MISSING_INPUT (critical) ------------------------------------------
    missing = [
        k for k in _REQUIRED_KEYS
        if k not in result or result[k] is None
    ]
    if missing:
        w.append(RuleWarning(
            code="MISSING_INPUT",
            severity="critical",
            stage="all",
            message=(
                f"Required result keys are absent or None: {missing}. "
                "The simulation may not have completed successfully."
            ),
            basis="engine_rule",
        ))

    # -- NEG_NET -----------------------------------------------------------
    e_net = result.get("e_net_kwh_d")
    if e_net is not None and e_net <= 0:
        w.append(RuleWarning(
            code="NEG_NET",
            severity="warning",
            stage="electricity generation",
            message=(
                f"Net electricity output is {e_net:.3f} kWh/day (≤ 0). "
                "Auxiliary energy draws exceed gross CHP output under current parameters."
            ),
            basis="engine_rule",
        ))

    # -- BUSWELL_EXCEEDED --------------------------------------------------
    ch4_per_vs = result.get("ch4_nm3_per_kg_vs")
    bw_bound   = result.get("buswell_bound")
    if ch4_per_vs is not None and bw_bound is not None and ch4_per_vs > bw_bound:
        w.append(RuleWarning(
            code="BUSWELL_EXCEEDED",
            severity="critical",
            stage="digestion",
            message=(
                f"Modelled CH4 yield ({ch4_per_vs:.4f} Nm³/kg VS) exceeds the "
                f"theoretical Buswell ceiling ({bw_bound:.4f} Nm³/kg VS). "
                "This is physically impossible; review feedstock composition or yield assumption."
            ),
            basis="documented",
        ))

    # -- VS_DESTRUCTION ----------------------------------------------------
    vs_destruction = result.get("vs_destruction")
    if vs_destruction is not None and vs_destruction > _VS_LIMIT:
        w.append(RuleWarning(
            code="VS_DESTRUCTION",
            severity="warning",
            stage="digestion",
            message=(
                f"Implied volatile-solids destruction fraction is "
                f"{vs_destruction:.1%}, which exceeds the model assumption limit of "
                f"{_VS_LIMIT:.0%}. "
                "Verify biogas yield and feedstock VS content."
            ),
            basis="model_assumption",
        ))

    # -- HEAT_DEFICIT ------------------------------------------------------
    heat_deficit = result.get("heat_deficit")
    if heat_deficit is True:
        w.append(RuleWarning(
            code="HEAT_DEFICIT",
            severity="warning",
            stage="digestion",
            message=(
                "Available biogas energy is insufficient to maintain digester temperature "
                "even with the auxiliary boiler at full draw. "
                "The digester may cool below the target temperature under these parameters."
            ),
            basis="engine_rule",
        ))

    # -- OUT_OF_RANGE ------------------------------------------------------
    oor = result.get("out_of_range_inputs")
    if oor:
        w.append(RuleWarning(
            code="OUT_OF_RANGE",
            severity="info",
            stage="all",
            message=(
                f"One or more inputs are outside the supported model range: {oor}. "
                "Results are extrapolations and may have reduced accuracy."
            ),
            basis="model_assumption",
        ))

    # -- ML_EXTRAPOLATION --------------------------------------------------
    if extrapolation_flag:
        w.append(RuleWarning(
            code="ML_EXTRAPOLATION",
            severity="info",
            stage="all",
            message=(
                "The ML yield model signals that this input combination is outside "
                "its training domain. The biogas yield prediction may be less reliable."
            ),
            basis="model_assumption",
        ))

    # -- CONTAMINATION (only when both thresholds supplied) ----------------
    if contamination_pct is not None and contamination_threshold_pct is not None:
        if contamination_pct > contamination_threshold_pct:
            w.append(RuleWarning(
                code="CONTAMINATION",
                severity="warning",
                stage="reception",
                message=(
                    f"Measured contamination ({contamination_pct:.1f}%) exceeds the "
                    f"site threshold ({contamination_threshold_pct:.1f}%). "
                    "This may affect sorting efficiency and feedstock suitability. "
                    "This is a model-assumption-based flag, not a safety assessment."
                ),
                basis="model_assumption",
            ))

    return w
