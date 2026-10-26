import json

from app.core_engine.engine import RHO_CH4

def load_factors(path="data/emission_factors.json"):
    f = json.load(open(path))
    bad = [k for k, v in f.items()
           if v.get("value") is None or not v.get("source")
           or v.get("status") not in ("sourced", "assumed")]
    if bad:
        raise ValueError(f"Fix value/source/status for: {bad}")
    return f

def compute_ghg(p, r, f, transport_km):
    baseline = r["suitable_kg_d"] * f["landfill_kgco2e_per_kg_organic"]["value"]
    leakage = r["ch4_nm3_d"] * p.ch4_slip * RHO_CH4 * f["gwp_ch4"]["value"]
    transport = (p.total_mass_kg_d / 1000) * transport_km * f["truck_kgco2e_per_tkm"]["value"]
    displaced = max(r["e_net_kwh_d"], 0) * f["grid_kgco2e_per_kwh"]["value"]
    proposed = leakage + transport - displaced
    return {
        "baseline_kgco2e_d": baseline,
        "proposed_kgco2e_d": proposed,
        "delta_kgco2e_d": baseline - proposed,
        "components": {"methane_leakage": leakage, "transport": transport,
                       "displaced_grid_electricity": -displaced},
        "boundary_notes": "Simplified boundary: rejected material, digestate handling and gas treatment emissions are not included.",
    }