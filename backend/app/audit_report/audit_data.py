import json
from dataclasses import asdict

from app.core_engine.engine import simulate, ENGINE_VERSION
from app.audit_report.ghg import load_factors, compute_ghg

def build_audit_payload(p, location, transport_km):
    r = simulate(p)
    f = load_factors()
    mc = json.load(open("data/monte_carlo_results.json"))
    return {
        "status": r["status"],
        "location": location,
        "engine_version": ENGINE_VERSION,
        "inputs_and_parameters": asdict(p),
        "parameter_status": "illustrative, not validated",
        "engine_results": {k: v for k, v in r.items() if k != "warnings"},
        "ghg": compute_ghg(p, r, f, transport_km),
        "emission_factors": f,
        "uncertainty": {**mc, "applies_to": mc["scenario"]},
        "warnings": r["warnings"],
    }