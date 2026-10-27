"""Process-specific GHG accounting for the audit report.

Method (GHG Protocol for Project Accounting, IPCC 2006 Guidelines + 2019 Refinement):

    baseline  = suitable organic waste sent to an unmanaged dumpsite (IPCC FOD-derived factor)
    proposed  = project emissions (transport, process energy, fugitive / non-CO2 combustion gases)
                - displaced fossil energy - durable carbon removals (biochar)
    delta     = baseline - proposed

Biogenic CO2 from the organic feedstock is excluded (IPCC: reported as a memo item, not counted).
Every process treats the same suitable organic stream, so baselines are comparable across branches.
All units: kg/d, kWh/d, kgCO2e/d.
"""
import json
from pathlib import Path

from app.core_engine.engine import RHO_CH4, simulate
from app.core_engine.pathways.composting import CompostingParams, simulate_composting
from app.core_engine.pathways.feedstock import Feedstock
from app.core_engine.pathways.gasification import simulate_gasification
from app.core_engine.pathways.pyrolysis import _LHV_CHAR_MJ_KG, simulate_pyrolysis

ANAEROBIC_DIGESTION = "anaerobic_digestion"
PYROLYSIS = "pyrolysis"
GASIFICATION = "gasification"
COMPOSTING = "composting"
PROCESSES = (ANAEROBIC_DIGESTION, PYROLYSIS, GASIFICATION, COMPOSTING)

C_TO_CO2 = 44.0 / 12.0


def load_factors(path=None):
    if path is None:
        p = Path(__file__).resolve().parents[2] / "data" / "emission_factors.json"
        path = p if p.exists() else "data/emission_factors.json"
    f = json.load(open(path))
    bad = [k for k, v in f.items()
           if v.get("value") is None or not v.get("source")
           or v.get("status") not in ("sourced", "assumed", "actual", "verified")]
    if bad:
        raise ValueError(f"Fix value/source/status for: {bad}")
    return f


def normalize_process(process):
    """Map a free-form process label ("Fast Pyrolysis", "anaerobic-digestion", "biogas") to a
    canonical id. None/blank -> anaerobic_digestion. Raises ValueError for unsupported processes."""
    s = (process or "").strip().lower().replace("-", "_").replace(" ", "_")
    if not s:
        return ANAEROBIC_DIGESTION
    if s in PROCESSES:
        return s
    if "pyro" in s:
        return PYROLYSIS
    if "gasif" in s:
        return GASIFICATION
    if "compost" in s:
        return COMPOSTING
    if "anaerobic" in s or "digest" in s or "biogas" in s:
        return ANAEROBIC_DIGESTION
    raise ValueError(
        f"Unsupported process '{process}' for GHG audit; supported: {', '.join(PROCESSES)}"
    )


def _organic_feedstock(p, suitable_kg_d, f):
    """The suitable organic stream expressed as a pathway-model Feedstock."""
    return Feedstock(
        total_mass_kg_d=suitable_kg_d,
        organic_fraction=1.0, plastic_fraction=0.0, paper_fraction=0.0, other_fraction=0.0,
        moisture_fraction=1.0 - p.ts_fraction,
        ash_fraction_dry=1.0 - p.vs_of_ts,
        lhv_dry_mj_per_kg=f["organic_lhv_dry_mj_per_kg"]["value"],
        contamination_pct=0.0,
    )


def simulate_process(p, process, f):
    """Run the mass/energy model for `process`. Always returns organic/suitable/rejected kg/d,
    plus `warnings` and `status`, alongside the process-specific outputs."""
    if process == ANAEROBIC_DIGESTION:
        return simulate(p)

    organic = p.total_mass_kg_d * p.organic_fraction
    suitable = organic * p.suitable_fraction
    fs = _organic_feedstock(p, suitable, f)
    if process == PYROLYSIS:
        r = simulate_pyrolysis(fs)
    elif process == GASIFICATION:
        r = simulate_gasification(fs)
    elif process == COMPOSTING:
        r = simulate_composting(fs, CompostingParams(
            ch4_kg_per_t=f["composting_ch4_kg_per_t_wet"]["value"],
            n2o_kg_per_t=f["composting_n2o_kg_per_t_wet"]["value"],
        ))
    else:
        raise ValueError(f"Unsupported process: {process}")
    return {"organic_kg_d": organic, "suitable_kg_d": suitable,
            "rejected_kg_d": organic - suitable, **r}


def _grid_terms(e_net_kwh_d, f):
    """Net electricity -> (import emissions, displaced-grid credit), both >= 0.
    A net deficit is Scope 2 import; a surplus displaces grid electricity."""
    grid = f["grid_kgco2e_per_kwh"]["value"]
    return max(-e_net_kwh_d, 0) * grid, max(e_net_kwh_d, 0) * grid


def _combustion_non_co2(fuel_kwh_d, f):
    """CH4 + N2O from burning biogenic syngas / pyrolysis fuels (biogenic CO2 excluded)."""
    return fuel_kwh_d * (
        f["stationary_combustion_ch4_kg_per_kwh"]["value"] * f["gwp_ch4"]["value"]
        + f["stationary_combustion_n2o_kg_per_kwh"]["value"] * f["gwp_n2o"]["value"]
    )


def _anaerobic_digestion(p, r, f):
    leakage = r["ch4_nm3_d"] * p.ch4_slip * RHO_CH4 * f["gwp_ch4"]["value"]
    grid_import, displaced = _grid_terms(r["e_net_kwh_d"], f)
    components = {"methane_leakage": leakage, "grid_electricity_import": grid_import,
                  "displaced_grid_electricity": -displaced}
    notes = ("Digestate handling, gas upgrading and flare emissions are not included; "
             "CH4 slip is applied to all biogas produced.")
    return components, notes


def _pyrolysis(p, r, f):
    # Char is retained as biochar, so only oil + gas energy is available as fuel.
    fuel_kwh = r["product_energy_kwh_d"] - r["char_kg_d"] * _LHV_CHAR_MJ_KG / 3.6
    # The pathway model counts pre-drying as electric; reactor sensible heat comes from the fuel.
    sensible_heat_kwh = r["process_heat_kwh_d"] - r["drying_kwh_d"]
    surplus_heat_kwh = fuel_kwh - sensible_heat_kwh
    fossil_heat = f["fossil_heat_kgco2_per_kwh"]["value"]
    sequestered = (r["char_kg_d"] * f["biochar_carbon_fraction"]["value"]
                   * f["biochar_permanence_fraction"]["value"] * C_TO_CO2)
    components = {
        "process_electricity_drying": r["drying_kwh_d"] * f["grid_kgco2e_per_kwh"]["value"],
        "supplemental_fossil_heat": max(-surplus_heat_kwh, 0) * fossil_heat,
        "combustion_ch4_n2o": _combustion_non_co2(fuel_kwh, f),
        "displaced_fossil_heat": -max(surplus_heat_kwh, 0) * fossil_heat,
        "biochar_sequestration": -sequestered,
    }
    notes = ("Biochar credit assumes soil application with 100-year permanence (IPCC 2019 F_perm) and "
             "is void if the char is burned. Surplus oil/gas heat is assumed to displace furnace oil. "
             "Pre-drying is modelled as grid electricity; waste-heat drying would lower emissions.")
    return components, notes


def _gasification(p, r, f):
    grid_import, displaced = _grid_terms(r["e_net_kwh_d"], f)
    components = {
        "combustion_ch4_n2o": _combustion_non_co2(r["syngas_energy_kwh_d"], f),
        "grid_electricity_import": grid_import,
        "displaced_grid_electricity": -displaced,
    }
    notes = ("Net electricity already deducts parasitic load and electric pre-drying. Gasifier char is "
             "ash-dominated and receives no sequestration credit. Tar/syngas clean-up residues are not included.")
    return components, notes


def _composting(p, r, f):
    grid_import, _ = _grid_terms(r["e_net_kwh_d"], f)
    components = {
        "composting_ch4": r["ch4_kg_d"] * f["gwp_ch4"]["value"],
        "composting_n2o": r["n2o_kg_d"] * f["gwp_n2o"]["value"],
        "process_electricity_aeration": grid_import,
    }
    notes = ("Uses IPCC 2006 default composting CH4/N2O factors (wet basis). "
             "No credit is taken for fertiliser displacement or soil carbon from compost.")
    return components, notes


_BRANCHES = {
    ANAEROBIC_DIGESTION: _anaerobic_digestion,
    PYROLYSIS: _pyrolysis,
    GASIFICATION: _gasification,
    COMPOSTING: _composting,
}


def compute_ghg(p, r, f, transport_km, process=ANAEROBIC_DIGESTION):
    baseline = r["suitable_kg_d"] * f["landfill_kgco2e_per_kg_organic"]["value"]
    transport = (p.total_mass_kg_d / 1000) * transport_km * f["truck_kgco2e_per_tkm"]["value"]
    process_components, process_notes = _BRANCHES[process](p, r, f)
    components = {"transport": transport, **process_components}
    proposed = sum(components.values())
    return {
        "process": process,
        "baseline_kgco2e_d": baseline,
        "proposed_kgco2e_d": proposed,
        "delta_kgco2e_d": baseline - proposed,
        "components": components,
        "boundary_notes": ("Project-level accounting (GHG Protocol for Project Accounting); avoided "
                           "emissions and removals are netted into the proposed scenario. Biogenic CO2 "
                           "excluded. Rejected material is outside the boundary. " + process_notes),
    }
