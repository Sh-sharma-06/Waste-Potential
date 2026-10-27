import json
from dataclasses import asdict

from app.core_engine.engine import ENGINE_VERSION
from app.audit_report.ghg import ANAEROBIC_DIGESTION, load_factors, compute_ghg, simulate_process

from pathlib import Path

DEFAULT_PARAMETER_STATUS = "illustrative, unverified"


def build_audit_payload(p, location, transport_km, process=ANAEROBIC_DIGESTION,
                        parameter_status=DEFAULT_PARAMETER_STATUS):
    f = load_factors()
    r = simulate_process(p, process, f)
    mc_path = Path(__file__).resolve().parents[2] / "data" / "monte_carlo_results.json"
    if not mc_path.exists():
        mc_path = Path("data/monte_carlo_results.json")
    mc = json.load(open(mc_path))
    return {
        "status": r["status"],
        "location": location,
        "process": process,
        "engine_version": ENGINE_VERSION,
        "inputs_and_parameters": asdict(p),
        "parameter_status": parameter_status or DEFAULT_PARAMETER_STATUS,
        "engine_results": {k: v for k, v in r.items() if k != "warnings"},
        "ghg": compute_ghg(p, r, f, transport_km, process),
        "emission_factors": f,
        "uncertainty": {**mc, "applies_to": mc["scenario"]},
        "warnings": r["warnings"],
    }
