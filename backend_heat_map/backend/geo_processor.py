from typing import Any, Dict, List, Optional
import copy
from data_loader import DataLoader, norm_karnataka_district
from waste_calculator import (
    compute_solid_waste_stats,
    compute_plastic_waste_stats,
    compute_wte_potential,
    normalize_state,
)


def get_heatmap_geojson(
    mode: str = "waste_generation",
    view: str = "state",
    state: Optional[str] = None,
    district: Optional[str] = None,
    pincode: Optional[str] = None,
    metric_type: str = "solid",  # 'solid' or 'plastic'
    plastic_year: str = "2022-23",
) -> Dict[str, Any]:
    loader = DataLoader.get_instance()
    mode = mode.lower().strip()
    view = view.lower().strip()

    # If pincode query is explicitly passed
    if pincode:
        pin_feat = loader.pincode_features.get(pincode.strip())
        if pin_feat:
            features = [_enrich_pincode_feature(pin_feat, mode, loader)]
            return {
                "type": "FeatureCollection",
                "metadata": {
                    "mode": mode,
                    "view": "pincode",
                    "pincode": pincode,
                    "total_features": len(features),
                    "granularity": "PIN-code boundary (Data Unavailable for local measurement - State context applied)"
                },
                "features": features
            }

    # If view is pincode with a state/district filter
    if view == "pincode":
        st_norm = normalize_state(state) if state else ""
        pin_list = []
        if st_norm and district:
            key = (st_norm, district.strip().title())
            pin_list = loader.pincodes_by_district.get(key, [])
        elif st_norm:
            pin_list = loader.pincodes_by_state.get(st_norm, [])
        else:
            # Default to Delhi or top sample if no state selected, to avoid overwhelming browser with 19,312 features
            pin_list = loader.pincodes_by_state.get("DELHI", [])[:100]

        # Deduplicate pin_list while preserving order
        unique_pins = list(dict.fromkeys(pin_list))

        features = []
        for pin in unique_pins:
            feat = loader.pincode_features.get(pin)
            if feat:
                features.append(_enrich_pincode_feature(feat, mode, loader))

        return {
            "type": "FeatureCollection",
            "metadata": {
                "mode": mode,
                "view": "pincode",
                "state": st_norm or "DELHI",
                "district": district or "ALL",
                "total_features": len(features),
                "granularity": "PIN-code postal polygons",
                "integrity_notice": "Karnataka postal polygons reflect verified district statistics from DMA Karnataka. Non-Karnataka postal measurements are not published by CPCB."
            },
            "features": features
        }

    # Default: State-level choropleth view
    raw_fc = loader.state_boundaries_fc
    raw_features = raw_fc.get("features", [])
    enriched_features = []

    for feat in raw_features:
        st_name = feat.get("properties", {}).get("state", "")
        st_norm = normalize_state(st_name)

        solid_row = loader.solid_waste_by_state.get(st_norm, {})
        plastic_row = loader.plastic_waste_by_state.get(st_norm, {})

        solid_stats = compute_solid_waste_stats(solid_row, is_pincode=False)
        plastic_stats = compute_plastic_waste_stats(plastic_row, is_pincode=False)
        wte_stats = compute_wte_potential(solid_stats.generated_tpd, solid_stats.treated_tpd, is_pincode=False)

        feat_copy = {
            "type": "Feature",
            "id": st_norm,
            "geometry": feat.get("geometry"),
            "properties": {
                "state": st_norm,
                "name": st_name.title(),
                "mode": mode,
                "pincode_count": feat.get("properties", {}).get("pincode_count", 0),
            }
        }

        # Attach mode-specific values & provenance
        if mode == "waste_generation":
            if metric_type == "plastic":
                val = plastic_stats.historical_tpy.get(plastic_year)
                feat_copy["properties"].update({
                    "metric_label": f"Plastic Waste ({plastic_year})",
                    "value": val,
                    "unit": "TPY",
                    "data_available": val is not None,
                    "is_estimate": False,
                    "provenance_source": "CPCB Plastic Waste Annual Report",
                    "provenance_period": plastic_year,
                })
            else:
                val = solid_stats.generated_tpd
                feat_copy["properties"].update({
                    "metric_label": "Solid Waste Generated",
                    "value": val,
                    "unit": "TPD",
                    "data_available": val is not None and val > 0,
                    "is_estimate": False,
                    "provenance_source": "CPCB Solid Waste Statistics",
                    "provenance_period": "2020-21",
                })
        elif mode == "processing_gap":
            val = solid_stats.processing_gap_tpd
            val_pct = solid_stats.processing_gap_percentage
            feat_copy["properties"].update({
                "metric_label": "Unprocessed Waste Gap",
                "value": val,
                "value_percentage": val_pct,
                "unit": "TPD",
                "data_available": val is not None,
                "is_estimate": True,
                "calculation_formula": "Processing Gap = Generated (TPD) - Treated (TPD)",
                "provenance_source": "Calculated from CPCB Solid Waste Report",
                "provenance_period": "2020-21",
                "reason": solid_stats.reason,
            })
        elif mode == "waste_to_energy":
            val = wte_stats.theoretical_power_mw
            treated_mw = wte_stats.treated_power_mw
            feat_copy["properties"].update({
                "metric_label": "Waste-to-Energy Potential",
                "value": val,
                "treated_wte_mw": treated_mw,
                "unit": "MW",
                "data_available": val is not None,
                "is_estimate": True,
                "calculation_formula": wte_stats.conversion_parameters.get("formula", ""),
                "provenance_source": "MNRE / CPCB Combustion Benchmark Model",
                "provenance_period": "2020-21",
            })
        elif mode == "waste_composition":
            feat_copy["properties"].update({
                "metric_label": "Compostable Matter Range",
                "value": 50.0,  # Midpoint of 40-60%
                "range_text": "40% - 60%",
                "unit": "%",
                "data_available": True,
                "is_estimate": False,
                "provenance_source": "CPCB / NEERI 59-City Waste Characterization Study",
                "provenance_period": "National Baseline",
                "notice": "National 59-city study baseline. State-specific and PIN-code specific composition is not published in this CPCB dataset."
            })

        # Summary figures for tooltips
        feat_copy["properties"]["summary"] = {
            "solid_generated_tpd": solid_stats.generated_tpd,
            "solid_treated_tpd": solid_stats.treated_tpd,
            "processing_gap_tpd": solid_stats.processing_gap_tpd,
            "processing_gap_pct": solid_stats.processing_gap_percentage,
            "wte_mw": wte_stats.theoretical_power_mw,
            "plastic_latest_tpy": plastic_stats.latest_tpy,
        }

        enriched_features.append(feat_copy)

    return {
        "type": "FeatureCollection",
        "metadata": {
            "mode": mode,
            "view": "state",
            "total_features": len(enriched_features),
            "granularity": "State / Union Territory",
            "data_level": "Official Reported Government Statistics"
        },
        "features": enriched_features
    }


def _enrich_pincode_feature(raw_feat: Dict[str, Any], mode: str, loader: DataLoader) -> Dict[str, Any]:
    props = raw_feat.get("properties", {})
    pin = str(props.get("Pincode", "")).strip()
    pin_info = loader.pincode_directory.get(pin, {})

    st_norm = pin_info.get("statename") or normalize_state(props.get("Circle", ""))
    district = pin_info.get("district") or props.get("Division", "")
    office = pin_info.get("officename") or props.get("Office_Name", "")

    # Check for Karnataka district data
    karnataka_dist = None
    if st_norm and st_norm.upper() == "KARNATAKA":
        nk = norm_karnataka_district(district)
        karnataka_dist = loader.karnataka_district_stats.get(nk) or loader.karnataka_district_stats.get(district.upper())

    val = None
    data_avail = False
    status = "Local Data Unavailable"
    unit = ""
    metric_label = "Value"
    notice = "CPCB does not publish waste measurements at PIN-code resolution."
    is_district_level = False

    if karnataka_dist:
        # Populate valid district-level values for supported heatmap modes only
        if mode == "waste_generation":
            msw = karnataka_dist.get("total_municipal_solid_waste_tpd")
            if msw is not None:
                val = msw
                data_avail = True
                status = f"Reported ({karnataka_dist['district_name']} District)"
                unit = "TPD"
                metric_label = f"District MSW ({karnataka_dist['district_name']})"
                notice = f"District-level statistic ({karnataka_dist['district_name']}) displayed on PIN boundary."
                is_district_level = True
        elif mode == "processing_gap":
            gap = karnataka_dist.get("processing_gap_tpd")
            if gap is not None:
                val = gap
                data_avail = True
                status = f"Reported Gap ({karnataka_dist['district_name']} District)"
                unit = "TPD"
                metric_label = f"District Processing Gap ({karnataka_dist['district_name']})"
                notice = f"District-level processing gap ({karnataka_dist['district_name']}) displayed on PIN boundary."
                is_district_level = True
        elif mode == "waste_to_energy":
            msw = karnataka_dist.get("total_municipal_solid_waste_tpd")
            proc = karnataka_dist.get("total_waste_processed_tpd")
            if msw is not None:
                wte = compute_wte_potential(msw, proc, is_pincode=False)
                val = wte.theoretical_power_mw
                data_avail = True
                status = f"Estimated ({karnataka_dist['district_name']} District)"
                unit = "MW"
                metric_label = f"District WtE Potential ({karnataka_dist['district_name']})"
                notice = f"District-level WtE potential ({karnataka_dist['district_name']}) displayed on PIN boundary."
                is_district_level = True
        elif mode == "waste_composition":
            # National baseline applies
            val = None
            data_avail = False
            status = "National Baseline (59-City Study)"
            notice = "Composition reflects national 59-city baseline."

    # Parent state values for contextual comparison
    solid_row = loader.solid_waste_by_state.get(st_norm, {})
    solid_stats = compute_solid_waste_stats(solid_row, is_pincode=False)
    wte_stats = compute_wte_potential(solid_stats.generated_tpd, solid_stats.treated_tpd, is_pincode=False)

    return {
        "type": "Feature",
        "id": pin,
        "geometry": raw_feat.get("geometry"),
        "properties": {
            "pincode": pin,
            "office_name": office,
            "district": district,
            "state": st_norm.title() if st_norm else "India",
            "circle": pin_info.get("circle") or props.get("Circle"),
            "division": pin_info.get("division") or props.get("Division"),
            "mode": mode,
            "value": val,
            "data_available": data_avail,
            "status": status,
            "unit": unit,
            "metric_label": metric_label,
            "is_district_level_stat": is_district_level,
            "district_name": karnataka_dist["district_name"] if karnataka_dist else None,
            "district_waste_stats": karnataka_dist,
            "integrity_notice": notice,
            "parent_state_stats": {
                "state_name": st_norm.title(),
                "solid_generated_tpd": solid_stats.generated_tpd,
                "solid_treated_tpd": solid_stats.treated_tpd,
                "processing_gap_tpd": solid_stats.processing_gap_tpd,
                "wte_potential_mw": wte_stats.theoretical_power_mw,
            }
        }
    }
