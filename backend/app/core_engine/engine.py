"""
Waste-Potential: anaerobic-digestion mass & energy engine (v0.2).
All default parameter VALUES are ILLUSTRATIVE, not validated data.
Units: kg/d, Nm3 (0 C), kWh/d. Yield is per kg volatile solids (VS), never per fresh kg.
"""
from .params import Params  # re-exported: `from engine import Params` keeps working
from . import guardrails as _gr
from .thermal import heat_demand_kwh as _heat_demand_kwh, split_chp_boiler as _split_chp_boiler

LHV_CH4_KWH_NM3 = 9.94            # lower heating value, 0 C, 1 atm (35.8 MJ/Nm3 / 3.6)
RHO_CH4, RHO_CO2 = 0.717, 1.977   # kg/Nm3 at 0 C
BUSWELL = {"carb": 0.415, "protein": 0.496, "lipid": 1.014}  # Nm3 CH4 / kg VS


def condition_water(m_feed, x_initial, x_target):
    """kg water to ADD (+) or REMOVE (-) so wet-basis moisture becomes x_target.
    Solids conserved: M*(1-xi) = M_new*(1-xt)  ->  dW = M*(xt-xi)/(1-xt)."""
    if not (0 <= x_initial < 1 and 0 <= x_target < 1):
        raise ValueError("moisture must be in [0,1)")
    return m_feed * (x_target - x_initial) / (1 - x_target)


def buswell_bound(comp):
    c, p, l = comp
    if abs(c + p + l - 1) > 1e-6:
        raise ValueError("composition must sum to 1")
    return c * BUSWELL["carb"] + p * BUSWELL["protein"] + l * BUSWELL["lipid"]


def simulate(p: Params):
    from dataclasses import asdict
    for name, v in asdict(p).items():
        if name not in ("composition", "ambient_temp_c", "digester_temp_c") and v < 0:
            raise ValueError(f"{name} must be >= 0")
    w = []
    organic = p.total_mass_kg_d * p.organic_fraction
    suitable = organic * p.suitable_fraction
    rejected = organic - suitable
    solids = suitable * p.ts_fraction
    vs = solids * p.vs_of_ts
    water_delta = condition_water(suitable, 1 - p.ts_fraction, 1 - p.target_ts)
    feed = suitable + water_delta
    v_dig = (feed / 1000.0) * p.hrt_days
    biogas = vs * p.y_biogas_nm3_per_kg_vs
    ch4 = biogas * p.ch4_fraction
    ch4_per_vs = p.y_biogas_nm3_per_kg_vs * p.ch4_fraction

    # --- Buswell ceiling check (via guardrails) ---
    bound = buswell_bound(p.composition)
    _buswell_warn = _gr.check_methane_yield(ch4_per_vs, bound)
    if _buswell_warn:
        # keep the original message format that tests look for ("Buswell" substring)
        w.append(f"CH4 yield {ch4_per_vs:.3f} exceeds Buswell bound {bound:.3f} "
                 f"Nm3/kg VS: physically impossible")

    rho_bg = p.ch4_fraction * RHO_CH4 + (1 - p.ch4_fraction) * RHO_CO2
    biogas_kg = biogas * rho_bg
    vs_destruction = biogas_kg / vs if vs > 0 else 0.0

    # --- VS destruction check (via guardrails) ---
    _vs_warn = _gr.check_vs_destruction(biogas_kg, vs)
    if _vs_warn:
        w.append(f"implied VS destruction {vs_destruction:.0%} > 85%: check yield")

    digestate = feed - biogas_kg                      # mass closure
    mass_residual = feed - biogas_kg - digestate

    ch4_avail = ch4 * (1 - p.ch4_slip)
    c_chem = ch4_avail * LHV_CH4_KWH_NM3 * p.availability
    flared = ch4_avail * LHV_CH4_KWH_NM3 * (1 - p.availability)

    # --- Heat demand (via thermal) ---
    dT = p.digester_temp_c - p.ambient_temp_c
    _hd = _heat_demand_kwh(feed, dT, v_dig, p.cp_kj_kg_k, p.u_wall_w_m2k)
    q_feed   = _hd.feed_heating_kwh_d
    q_loss   = _hd.wall_loss_kwh_d
    q_demand = _hd.total_kwh_d

    # --- CHP / boiler split (via thermal) ---
    _hs = _split_chp_boiler(c_chem, q_demand, p.eta_th, p.eta_boiler)
    boiler   = _hs.boiler_fuel_kwh_d
    chp_in   = _hs.chp_fuel_kwh_d
    if _hs.heat_deficit:
        w.append("heat demand cannot be met from biogas: digester cannot be held at temperature")

    e_gross = chp_in * p.eta_el
    heat_surplus = chp_in * p.eta_th + boiler * p.eta_boiler - q_demand
    aux = (p.aux_mix_kwh_m3_d * v_dig + p.aux_sort_kwh_t * p.total_mass_kg_d / 1000.0
           + p.aux_gas_kwh_nm3 * biogas)
    e_net = e_gross - aux
    if e_net <= 0:
        w.append("net electricity <= 0: auxiliary demand exceeds gross output")

    # --- Input range check (via guardrails) ---
    _oor = _gr.check_input_ranges(p)
    out_of_range_fields = [item[0] for item in _oor]
    for field in out_of_range_fields:
        w.append(f"input '{field}' is outside the supported model range: extrapolation")
    status = "extrapolation" if out_of_range_fields else "illustrative_estimate"

    return {
        "organic_kg_d": organic, "suitable_kg_d": suitable, "rejected_kg_d": rejected,
        "water_added_kg_d": water_delta, "feed_kg_d": feed, "digester_m3": v_dig,
        "vs_kg_d": vs, "biogas_nm3_d": biogas, "ch4_nm3_d": ch4,
        "ch4_nm3_per_kg_vs": ch4_per_vs, "buswell_bound": bound,
        "vs_destruction": vs_destruction, "biogas_kg_d": biogas_kg,
        "digestate_kg_d": digestate, "mass_residual_kg": mass_residual,
        "e_chem_kwh_d": ch4_avail * LHV_CH4_KWH_NM3, "flared_kwh_d": flared,
        "q_demand_kwh_d": q_demand, "boiler_chem_kwh_d": boiler,
        "e_gross_kwh_d": e_gross, "aux_kwh_d": aux, "e_net_kwh_d": e_net,
        "heat_surplus_kwh_d": heat_surplus, "warnings": w,
        # additive keys
        "q_feed_kwh_d": q_feed, "q_loss_kwh_d": q_loss,
        "chp_chem_kwh_d": chp_in, "heat_deficit": _hs.heat_deficit,
        "out_of_range_inputs": out_of_range_fields,
        "status": status,
    }


def cost_per_kwh(annual_cost, e_net_kwh_d):
    """Undefined (None) when net electricity <= 0."""
    return None if e_net_kwh_d <= 0 else annual_cost / (e_net_kwh_d * 365)