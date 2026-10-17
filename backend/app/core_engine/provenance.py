"""Parameter provenance registry for the B1 Science Core.

Tracks the origin, status, and basis of every numeric constant and default used
across core_engine.  Pure module — no network or file I/O except to_csv().

Status vocabulary
-----------------
"illustrative_estimate"
    Value is a placeholder.  Source may be "TBD".
"sourced"
    Value taken from a named document or measurement.  Source must be non-empty
    and not equal to "TBD".
"derived"
    Value calculated from other quantities.  Notes must name the formula.
"validated"
    Value confirmed against independent real-plant or lab data.  Source required.
"""
from __future__ import annotations

import csv
import dataclasses
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Provenance dataclass
# ---------------------------------------------------------------------------

_VALID_STATUSES = frozenset(
    {"illustrative_estimate", "sourced", "derived", "validated"}
)


@dataclass(frozen=True)
class Provenance:
    """Provenance record for one parameter or constant.

    Attributes
    ----------
    name:
        Parameter identifier (matches the Python name where possible).
    value:
        Numeric value as a float or string (e.g. a tuple default becomes a str).
    unit:
        Physical unit string (empty string if dimensionless).
    status:
        One of "illustrative_estimate", "sourced", "derived", "validated".
    source:
        Citation or data origin.  "TBD" is allowed only for
        ``illustrative_estimate``.  Required (non-empty, non-"TBD") for
        ``sourced`` and ``validated``.
    basis:
        Mass basis description (e.g. "per kg wet feed", "per kg VS").
    applies_to:
        Pathway name or "all".
    notes:
        Free-text annotation.  Required to name the formula for ``derived``.
    """

    name: str
    value: Any
    unit: str
    status: str
    source: str
    basis: str
    applies_to: str
    notes: str = ""

    def __post_init__(self) -> None:
        if self.status not in _VALID_STATUSES:
            raise ValueError(
                f"Provenance.status must be one of {sorted(_VALID_STATUSES)}; "
                f"got {self.status!r} for parameter {self.name!r}"
            )
        if self.status in {"sourced", "validated"}:
            if not self.source or self.source.strip() == "TBD":
                raise ValueError(
                    f"Provenance status {self.status!r} requires a non-empty "
                    f"source not equal to 'TBD'; got {self.source!r} "
                    f"for parameter {self.name!r}"
                )
        if self.status == "derived":
            if not self.notes or not self.notes.strip():
                raise ValueError(
                    f"Provenance status 'derived' requires notes naming the "
                    f"formula; notes is empty for parameter {self.name!r}"
                )


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _p(
    name: str,
    value: Any,
    unit: str,
    status: str,
    source: str,
    basis: str,
    applies_to: str,
    notes: str = "",
) -> Provenance:
    """Convenience constructor."""
    return Provenance(
        name=name, value=value, unit=unit, status=status,
        source=source, basis=basis, applies_to=applies_to, notes=notes,
    )


# ---------------------------------------------------------------------------
# Build provenance list
# ---------------------------------------------------------------------------

def build_provenance() -> List[Provenance]:  # noqa: C901 – complexity is intentional
    """Collect provenance records from imports and introspection.

    Sources collected, in order:
    (a) AD Params defaults (22 fields) via params.Params — status illustrative_estimate.
    (b) Module-level physics constants in engine.py and guardrails.py:
        LHV of CH4, gas densities, Buswell coefficients (derived from stoichiometry),
        VS-destruction limit.
    (c) Default dataclass fields of every pathway params class in pathways/:
        composting, incineration, gasification, pyrolysis, htc, torrefaction.
    (d) Economic defaults in pathways/compare.py (_DEFAULT_COSTS).
    (e) GWP emission constants in pathways/adapter.py.
    (f) Emission factors from app/decision/emission_factors.py if importable;
        skipped with a note otherwise.

    Returns
    -------
    list[Provenance]
        Ordered list, no duplicate (applies_to, name) pairs.
    """
    records: List[Provenance] = []
    seen: set = set()

    def _add(p: Provenance) -> None:
        key = (p.applies_to, p.name)
        if key not in seen:
            seen.add(key)
            records.append(p)

    # -----------------------------------------------------------------------
    # (a) AD Params defaults — 22 fields
    # -----------------------------------------------------------------------
    from app.core_engine.params import Params
    _PARAMS_UNITS: Dict[str, str] = {
        "total_mass_kg_d":        "kg/d",
        "organic_fraction":       "fraction",
        "suitable_fraction":      "fraction",
        "ts_fraction":            "kg TS/kg wet",
        "vs_of_ts":               "kg VS/kg TS",
        "target_ts":              "fraction",
        "y_biogas_nm3_per_kg_vs": "Nm³/kg VS",
        "ch4_fraction":           "fraction",
        "ch4_slip":               "fraction",
        "availability":           "fraction",
        "eta_el":                 "fraction",
        "eta_th":                 "fraction",
        "eta_boiler":             "fraction",
        "digester_temp_c":        "°C",
        "ambient_temp_c":         "°C",
        "hrt_days":               "days",
        "cp_kj_kg_k":             "kJ/kg·K",
        "u_wall_w_m2k":           "W/m²·K",
        "aux_mix_kwh_m3_d":       "kWh/m³/day",
        "aux_sort_kwh_t":         "kWh/t",
        "aux_gas_kwh_nm3":        "kWh/Nm³",
        "composition":            "fraction tuple",
    }
    _defaults = Params()
    for f in dataclasses.fields(_defaults):
        val = getattr(_defaults, f.name)
        unit = _PARAMS_UNITS.get(f.name, "")
        _add(_p(
            name=f.name,
            value=str(val) if isinstance(val, tuple) else val,
            unit=unit,
            status="illustrative_estimate",
            source="TBD",
            basis="per kg wet waste feed",
            applies_to="anaerobic_digestion",
            notes="AD Params default; blueprint catalog (unvalidated)",
        ))

    # -----------------------------------------------------------------------
    # (b) engine.py and guardrails.py physics constants
    # -----------------------------------------------------------------------
    # engine.py
    import app.core_engine.engine as _eng
    _add(_p("LHV_CH4_KWH_NM3", _eng.LHV_CH4_KWH_NM3, "kWh/Nm³",
            "sourced", "Lide (CRC Handbook, 2007): 35.8 MJ/Nm³ / 3.6",
            "per Nm³ CH4 at 0°C 1 atm", "all",
            notes="Lower heating value of methane; 35.8 MJ/Nm³ ÷ 3.6"))
    _add(_p("RHO_CH4", _eng.RHO_CH4, "kg/Nm³",
            "sourced", "Lide (CRC Handbook, 2007): ideal gas density at 0°C 1 atm",
            "per Nm³ at 0°C 1 atm", "all"))
    _add(_p("RHO_CO2", _eng.RHO_CO2, "kg/Nm³",
            "sourced", "Lide (CRC Handbook, 2007): ideal gas density at 0°C 1 atm",
            "per Nm³ at 0°C 1 atm", "all"))
    # Buswell dict in engine.py
    _buswell_note = (
        "Reproduced from Buswell stoichiometric equation: "
        "CnHaOb → (n/2 + a/8 − b/4) CH4 + (n/2 − a/8 + b/4) CO2; "
        "carbohydrate=C6H10O5, protein=C5H7NO2, lipid=C57H104O6"
    )
    _buswell_source = "Buswell & Mueller (1952); Angelidaki & Sanders (2004)"
    for _k, _v in _eng.BUSWELL.items():
        _add(_p(f"BUSWELL_{_k}", _v, "Nm³ CH4/kg VS",
                "derived", _buswell_source,
                "per kg VS", "anaerobic_digestion",
                notes=_buswell_note))

    # guardrails.py
    import app.core_engine.guardrails as _gr
    _add(_p("_BUSWELL_CARB", _gr._BUSWELL_CARB, "Nm³ CH4/kg VS",
            "derived", _buswell_source, "per kg VS", "anaerobic_digestion",
            notes=_buswell_note))
    _add(_p("_BUSWELL_PROT", _gr._BUSWELL_PROT, "Nm³ CH4/kg VS",
            "derived", _buswell_source, "per kg VS", "anaerobic_digestion",
            notes=_buswell_note))
    _add(_p("_BUSWELL_LIP", _gr._BUSWELL_LIP, "Nm³ CH4/kg VS",
            "derived", _buswell_source, "per kg VS", "anaerobic_digestion",
            notes=_buswell_note))
    _add(_p("_VS_DESTRUCTION_LIMIT", _gr._VS_DESTRUCTION_LIMIT, "fraction",
            "illustrative_estimate", "TBD",
            "fraction of VS destroyed", "anaerobic_digestion",
            notes="MODEL ASSUMPTION: mesophilic AD max VS destruction; literature range 0.60–0.90"))
    _add(_p("_NM3_PER_MOL", _gr._NM3_PER_MOL, "Nm³/mol",
            "sourced", "Ideal gas law at 0°C, 1 atm (22.414 L/mol)",
            "per mol ideal gas", "all"))

    # params.py module-level constants
    import app.core_engine.params as _pm
    _add(_p("LHV_CH4", _pm.LHV_CH4, "kWh/Nm³",
            "sourced", "Lide (CRC Handbook, 2007): 35.8 MJ/Nm³ / 3.6",
            "per Nm³ CH4 at 0°C 1 atm", "all",
            notes="Same physical constant as engine.LHV_CH4_KWH_NM3"))
    _add(_p("BUSWELL_CARB", _pm.BUSWELL_CARB, "Nm³ CH4/kg VS",
            "derived", _buswell_source, "per kg VS", "anaerobic_digestion",
            notes=_buswell_note))
    _add(_p("BUSWELL_PROT", _pm.BUSWELL_PROT, "Nm³ CH4/kg VS",
            "derived", _buswell_source, "per kg VS", "anaerobic_digestion",
            notes=_buswell_note))
    _add(_p("BUSWELL_LIP", _pm.BUSWELL_LIP, "Nm³ CH4/kg VS",
            "derived", _buswell_source, "per kg VS", "anaerobic_digestion",
            notes=_buswell_note))

    # -----------------------------------------------------------------------
    # (c) Pathway params dataclass defaults
    # -----------------------------------------------------------------------
    _pathway_params: List[Tuple[str, Any]] = []
    try:
        from app.core_engine.pathways.composting import CompostingParams
        _pathway_params.append(("composting", CompostingParams()))
    except ImportError:
        pass
    try:
        from app.core_engine.pathways.incineration import IncinerationParams
        _pathway_params.append(("incineration", IncinerationParams()))
    except ImportError:
        pass
    try:
        from app.core_engine.pathways.gasification import GasificationParams
        _pathway_params.append(("gasification", GasificationParams()))
    except ImportError:
        pass
    try:
        from app.core_engine.pathways.pyrolysis import PyrolysisParams
        _pathway_params.append(("pyrolysis", PyrolysisParams()))
    except ImportError:
        pass
    try:
        from app.core_engine.pathways.htc import HTCParams
        _pathway_params.append(("htc", HTCParams()))
    except ImportError:
        pass
    try:
        from app.core_engine.pathways.torrefaction import TorrefactionParams
        _pathway_params.append(("torrefaction", TorrefactionParams()))
    except ImportError:
        pass

    for pathway_name, params_instance in _pathway_params:
        for f in dataclasses.fields(params_instance):
            val = getattr(params_instance, f.name)
            _add(_p(
                name=f.name,
                value=str(val) if isinstance(val, tuple) else val,
                unit="",
                status="illustrative_estimate",
                source="TBD",
                basis="per kg wet feed",
                applies_to=pathway_name,
                notes=f"Default field of {type(params_instance).__name__}; "
                      "blueprint catalog (unvalidated)",
            ))

    # -----------------------------------------------------------------------
    # (d) Economic defaults in compare.py
    # -----------------------------------------------------------------------
    _econ_units: Dict[str, str] = {
        "capex_inr":      "INR",
        "opex_inr_per_t": "INR/t/y",
        "life_years":     "years",
        "discount_rate":  "fraction",
    }
    try:
        from app.core_engine.pathways.compare import _DEFAULT_COSTS
        for pw, cost_dict in _DEFAULT_COSTS.items():
            for cost_key, cost_val in cost_dict.items():
                _add(_p(
                    name=cost_key,
                    value=cost_val,
                    unit=_econ_units.get(cost_key, ""),
                    status="illustrative_estimate",
                    source="TBD",
                    basis="project-level",
                    applies_to=pw,
                    notes=f"Economic default from compare._DEFAULT_COSTS; "
                          "blueprint catalog (unvalidated)",
                ))
    except ImportError:
        pass

    # -----------------------------------------------------------------------
    # (e) GWP emission constants in adapter.py
    # -----------------------------------------------------------------------
    try:
        import app.core_engine.pathways.adapter as _adp
        _add(_p("_GWP_CH4", _adp._GWP_CH4, "kg CO2-eq/kg CH4",
                "illustrative_estimate", "TBD",
                "per kg CH4 emitted", "all",
                notes="GWP-100 for CH4; IPCC AR5 value cited in adapter.py but source listed as TBD"))
        _add(_p("_GWP_N2O", _adp._GWP_N2O, "kg CO2-eq/kg N2O",
                "illustrative_estimate", "TBD",
                "per kg N2O emitted", "all",
                notes="GWP-100 for N2O; IPCC AR5 value cited in adapter.py but source listed as TBD"))
    except ImportError:
        pass

    # -----------------------------------------------------------------------
    # (f) app/decision/emission_factors.py — import if available
    # -----------------------------------------------------------------------
    try:
        import app.decision.emission_factors as _ef  # type: ignore[import]
        for attr in dir(_ef):
            if attr.startswith("_"):
                continue
            val = getattr(_ef, attr)
            if isinstance(val, (int, float)):
                _add(_p(
                    name=attr,
                    value=val,
                    unit="",
                    status="illustrative_estimate",
                    source="TBD",
                    basis="",
                    applies_to="all",
                    notes="Emission factor from app/decision/emission_factors.py",
                ))
    except ImportError:
        # Module not present — skip with no error
        pass

    return records


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------

def registry_gaps(records: Optional[List[Provenance]] = None) -> List[str]:
    """Return names whose status is still ``"illustrative_estimate"``.

    Parameters
    ----------
    records:
        Output of :func:`build_provenance`.  If ``None``, calls
        :func:`build_provenance` fresh.
    """
    if records is None:
        records = build_provenance()
    return [r.name for r in records if r.status == "illustrative_estimate"]


def coverage_summary(
    records: Optional[List[Provenance]] = None,
) -> Dict[str, Any]:
    """Return count breakdowns by status and by applies_to.

    Parameters
    ----------
    records:
        Output of :func:`build_provenance`.  If ``None``, calls
        :func:`build_provenance` fresh.

    Returns
    -------
    dict
        ``{"total": int, "by_status": {status: int, ...},
           "by_applies_to": {pathway: int, ...}}``
    """
    if records is None:
        records = build_provenance()

    by_status: Dict[str, int] = {}
    by_applies_to: Dict[str, int] = {}
    for r in records:
        by_status[r.status] = by_status.get(r.status, 0) + 1
        by_applies_to[r.applies_to] = by_applies_to.get(r.applies_to, 0) + 1

    return {
        "total": len(records),
        "by_status": by_status,
        "by_applies_to": by_applies_to,
    }


def to_csv(path: str | Path, records: Optional[List[Provenance]] = None) -> Path:
    """Write the provenance registry to a CSV file.

    Parameters
    ----------
    path:
        File path for the CSV output.  Parent directories are created if they
        do not exist.
    records:
        Output of :func:`build_provenance`.  If ``None``, calls
        :func:`build_provenance` fresh.

    Returns
    -------
    Path
        Resolved path to the written file.
    """
    if records is None:
        records = build_provenance()

    out = Path(path).expanduser().resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    _fields = [f.name for f in dataclasses.fields(Provenance)]
    with out.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_fields)
        writer.writeheader()
        for r in records:
            writer.writerow(dataclasses.asdict(r))

    return out
