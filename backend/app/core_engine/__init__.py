"""Waste-Potential — Science Core public API (Part B1).

Exports
-------
Params           frozen dataclass — simulation inputs (22 fields, unit-suffixed names).
                 Key fields: total_mass_kg_d (kg/d fresh mass), organic_fraction (0-1),
                 suitable_fraction (0-1), y_biogas_nm3_per_kg_vs (Nm³/kg VS at 0 °C).
simulate(p)      Params → dict — mass & energy balance; gas in Nm³ at 0 °C, 1 atm;
                 energy in kWh/d; mass basis = fresh mass in, VS fraction of TS.
                 Always includes "warnings": list[str].
run_mc(p, ...)   Params → dict — Monte Carlo over simulate; returns median, percentiles,
                 Spearman sensitivity; all numbers are plain Python floats.
Dist             frozen dataclass — one uncertain input distribution (kind, args, clip).
default_dists()  () → Dict[str, Dist] — 9 default distributions over Params fields.
get(name)        str → ParameterEntry — registry lookup by Params field name.
defaults_used(p) Params → list[str] — field names still at their illustrative defaults.
stage_risks()    () → list[dict] — static catalogue of AD stage risk factors.
rule_warnings(r) dict → list[RuleWarning] — structured warnings from simulate() output.
router           FastAPI APIRouter — REST endpoints for parameters, simulation, validation.
"""

from app.core_engine.params import Params
from app.core_engine.engine import simulate
from app.core_engine.montecarlo import run_mc, Dist, default_dists
from app.core_engine.registry import get, defaults_used
from app.core_engine.risk_rules import stage_risks, rule_warnings
from app.core_engine import router

__all__ = [
    "Params",
    "simulate",
    "run_mc",
    "Dist",
    "default_dists",
    "get",
    "defaults_used",
    "stage_risks",
    "rule_warnings",
    "router",
]
