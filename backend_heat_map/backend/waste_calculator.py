from typing import Any, Dict, Optional
import math
from models import (
    DataProvenance,
    SolidWasteStats,
    PlasticWasteStats,
    WasteToEnergyStats,
    WasteCompositionStats,
)

STATE_ALIASES = {
    "THE DADRA AND NAGAR HAVELI AND DAMAN AND DIU": "DADRA AND NAGAR HAVELI AND DAMAN AND DIU",
    "DAMAN": "DADRA AND NAGAR HAVELI AND DAMAN AND DIU",
    "ANDAMAN AND NICOBAR ISLAND": "ANDAMAN AND NICOBAR ISLANDS",
    "PONDICHERRY": "PUDUCHERRY",
    "ORISSA": "ODISHA",
    "TAMILNADU": "TAMIL NADU",
    "JAMMUKASHMIR": "JAMMU AND KASHMIR",
    "CHATTISGARH": "CHHATTISGARH",
    "TELENGANA": "TELANGANA",
}


def normalize_state(name: Optional[str]) -> str:
    if not name:
        return ""
    clean = str(name).strip().upper()
    return STATE_ALIASES.get(clean, clean)


# Standard MNRE (Ministry of New and Renewable Energy) / CPCB documented conversion parameters
MNRE_WTE_PARAMETERS = {
    "combustible_fraction": 0.20,  # 20% combustible dry fraction based on CPCB MSW characterization
    "ncv_kcal_kg": 1100.0,         # 1,100 kcal/kg Lower/Net Calorific Value for typical Indian MSW
    "plant_efficiency": 0.22,      # 22% electrical generation thermodynamic efficiency
    "kcal_per_kwh": 860.0,         # Standard energy conversion unit
    "hours_per_day": 24.0,
    "formula": "Power (MW) = (Waste_TPD * Combustible_Fraction * NCV_kcal_kg * Efficiency) / (24 * 860)"
}


def clean_float(val: Any) -> Optional[float]:
    if val is None or val in ("", "NA", "N/A", "na"):
        return None
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (ValueError, TypeError):
        return None


def compute_solid_waste_stats(row: Dict[str, Any], is_pincode: bool = False, state_name: str = "") -> SolidWasteStats:
    if is_pincode:
        # Data integrity rule: CPCB does not collect/report solid waste at PIN code level
        return SolidWasteStats(
            data_available=False,
            reason="CPCB does not report municipal solid waste statistics at postal PIN-code granularity. Direct measurement unavailable.",
            provenance=DataProvenance(
                source="Central Pollution Control Board (CPCB) Annual Report",
                reporting_period="2020-21",
                agency="Central Pollution Control Board / MoHUA",
                granularity="pincode",
                is_estimate=False,
                notes="State-level context is available; local PIN-code measurement is unavailable."
            )
        )

    gen_val = clean_float(row.get("Solid waste generated (TPD)")) or 0.0
    col_val = clean_float(row.get("Collected (TPD)")) or 0.0
    treated_val = clean_float(row.get("Treated (TPD)"))

    gap_tpd = None
    gap_pct = None
    treatment_eff = None
    if treated_val is not None:
        gap_tpd = round(gen_val - treated_val, 2)
        if gen_val > 0:
            gap_pct = round((gap_tpd / gen_val) * 100, 2)
            treatment_eff = round((treated_val / gen_val) * 100, 2)

    col_eff = round((col_val / gen_val) * 100, 2) if gen_val > 0 else None

    return SolidWasteStats(
        data_available=True,
        generated_tpd=round(gen_val, 2),
        collected_tpd=round(col_val, 2),
        treated_tpd=round(treated_val, 2) if treated_val is not None else None,
        processing_gap_tpd=gap_tpd,
        processing_gap_percentage=gap_pct,
        collection_efficiency_pct=col_eff,
        treatment_efficiency_pct=treatment_eff,
        reason="CPCB reported Treated as NA for this territory" if treated_val is None else None,
        provenance=DataProvenance(
            source="Central Pollution Control Board (CPCB) - Solid Waste Management in India",
            reporting_period="2020-21",
            agency="CPCB / State Pollution Control Boards (SPCBs)",
            granularity="state",
            is_estimate=False,
            notes="State-level reported municipal solid waste measurements. Processing gap calculated as (Generated - Treated)."
        )
    )


def compute_plastic_waste_stats(row: Dict[str, Any], is_pincode: bool = False) -> PlasticWasteStats:
    if is_pincode:
        return PlasticWasteStats(
            data_available=False,
            reason="Plastic waste generation is reported by CPCB at State/UT level only. Postal PIN-code measurements are not compiled.",
            provenance=DataProvenance(
                source="CPCB Annual Report on Implementation of Plastic Waste Management Rules",
                reporting_period="2018-19 to 2022-23",
                agency="Central Pollution Control Board",
                granularity="pincode",
                is_estimate=False,
                notes="State-level time series available; PIN-code level data unavailable."
            )
        )

    years = ["2018-19", "2019-20", "2020-21", "2021-22", "2022-23"]
    history = {}
    latest_val = None
    latest_year = None

    for yr in years:
        val = clean_float(row.get(yr))
        if val is not None:
            num = round(val, 2)
            history[yr] = num
            latest_val = num
            latest_year = yr
        else:
            history[yr] = None

    # Calculate 5-year trend if endpoints exist
    trend_desc = "Stable"
    val_first = history.get("2018-19")
    if val_first and latest_val and val_first > 0:
        pct_change = round(((latest_val - val_first) / val_first) * 100, 1)
        if pct_change > 10:
            trend_desc = f"+{pct_change}% increase over 5 years"
        elif pct_change < -10:
            trend_desc = f"{pct_change}% decrease over 5 years"
        else:
            trend_desc = f"{pct_change}% over 5 years (stable)"

    return PlasticWasteStats(
        data_available=bool(history),
        historical_tpy=history,
        latest_tpy=latest_val,
        latest_period=latest_year,
        trend=trend_desc,
        provenance=DataProvenance(
            source="CPCB Annual Report on Implementation of Plastic Waste Management Rules",
            reporting_period="2018-19 to 2022-23",
            agency="CPCB / SPCBs / PCCs",
            granularity="state",
            is_estimate=False,
            notes="State-wise plastic waste generation in Tons Per Year (TPY)."
        )
    )


def compute_wte_potential(generated_tpd: Optional[float], treated_tpd: Optional[float] = None, is_pincode: bool = False) -> WasteToEnergyStats:
    if is_pincode or generated_tpd is None or generated_tpd <= 0:
        return WasteToEnergyStats(
            data_available=False,
            reason="Cannot calculate Waste-to-Energy potential at PIN-code level: Missing localized municipal waste generation volume and Net Calorific Value (NCV) measurements.",
            theoretical_power_mw=None,
            treated_power_mw=None,
            conversion_parameters=MNRE_WTE_PARAMETERS,
            methodology="MNRE Combustion Potential Model: P(MW) = (Waste_TPD * Combustible_Fraction * NCV * Efficiency) / (24 * 860).",
            is_estimate=True,
            provenance=DataProvenance(
                source="MNRE / CPCB Waste-to-Energy Task Force Guidelines",
                reporting_period="2020-21 baseline",
                agency="Ministry of New and Renewable Energy / CPCB",
                granularity="pincode",
                is_estimate=True,
                notes="PIN-code calculation withheld due to lack of local combustible fraction & LCV inputs."
            )
        )

    # Conversion factor = (0.20 * 1100 * 0.22) / (24 * 860) = 48.4 / 20640 ≈ 0.00234496 MW per TPD
    conversion_factor = (
        MNRE_WTE_PARAMETERS["combustible_fraction"]
        * MNRE_WTE_PARAMETERS["ncv_kcal_kg"]
        * MNRE_WTE_PARAMETERS["plant_efficiency"]
    ) / (MNRE_WTE_PARAMETERS["hours_per_day"] * MNRE_WTE_PARAMETERS["kcal_per_kwh"])

    theo_mw = round(generated_tpd * conversion_factor, 2)
    treated_mw = round(treated_tpd * conversion_factor, 2) if (treated_tpd is not None and treated_tpd > 0) else None

    return WasteToEnergyStats(
        data_available=True,
        theoretical_power_mw=theo_mw,
        treated_power_mw=treated_mw,
        conversion_parameters=MNRE_WTE_PARAMETERS,
        methodology="Derived using standard MNRE combustion parameters: 20% combustible fraction, 1,100 kcal/kg NCV, 22% electrical generation efficiency.",
        is_estimate=True,
        provenance=DataProvenance(
            source="Ministry of New and Renewable Energy (MNRE) / CPCB Guidelines",
            reporting_period="2020-21 baseline",
            agency="MNRE / CPCB",
            granularity="state",
            is_estimate=True,
            notes="State-level calculated theoretical estimate based on reported solid waste generation tonnage."
        )
    )


def get_waste_composition_data() -> WasteCompositionStats:
    return WasteCompositionStats(
        data_available=True,
        granularity="national_59_city_study",
        compostable_range_pct=[40.0, 60.0],
        recyclable_range_pct=[10.0, 25.0],
        inert_range_pct=[25.0, 40.0],
        moisture_range_pct=[30.0, 60.0],
        cn_ratio_range=[20.0, 40.0],
        per_capita_generation_kg_day=[0.12, 0.60],
        heavy_metals_mg_kg={
            "Lead (Pb)": "47 - 185 mg/kg",
            "Nickel (Ni)": "36 - 63 mg/kg",
            "Cadmium (Cd)": "1.5 - 6.5 mg/kg",
            "Mercury (Hg)": "0.01 - 0.23 mg/kg"
        },
        limitations="CPCB/NEERI study evaluated 59 metro cities and state capitals. State-specific and PIN-code-specific composition tables were not published in this dataset; national benchmark ranges are provided.",
        provenance=DataProvenance(
            source="CPCB sponsored NEERI study: 'Assessment of Status of Municipal Solid Wastes Management in Metro Cities and State Capitals'",
            reporting_period="National Baseline Study",
            agency="Central Pollution Control Board (CPCB) & NEERI",
            granularity="national_study",
            is_estimate=False,
            notes="Field studies for 59 metro cities and state capitals."
        )
    )
