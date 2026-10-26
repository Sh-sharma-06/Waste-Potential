import logging
import math
from contextlib import asynccontextmanager
from typing import Any, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from data_loader import DataLoader, norm_karnataka_district
from geo_processor import get_heatmap_geojson
from models import FilterOptions, RegionDetails

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("india_waste_heatmap.main")


def clean_coord(val: Any) -> Optional[float]:
    if val is None or val in ("", "NA", "N/A", "na"):
        return None
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, 6)
    except (ValueError, TypeError):
        return None


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting India Waste Heatmap API Server...")
    loader = DataLoader.get_instance()
    loader.load_all()
    yield
    logger.info("Shutting down India Waste Heatmap API Server...")


app = FastAPI(
    title="India Waste Heatmap API",
    description="Backend API for Standalone Interactive India Waste Heatmap with verified CPCB and Data.gov.in datasets.",
    version="1.0.0",
    lifespan=lifespan,
)

# Enable CORS for local dev and frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
async def health_check():
    loader = DataLoader.get_instance()
    return {
        "status": "healthy",
        "service": "India Waste Heatmap API",
        "version": "1.0.0",
        "datasets": {
            "solid_waste_statistics": {
                "loaded": len(loader.solid_waste_by_state) > 0,
                "states_covered": len(loader.solid_waste_by_state),
                "source": "CPCB Solid Waste Management in India",
            },
            "plastic_waste_statistics": {
                "loaded": len(loader.plastic_waste_by_state) > 0,
                "states_covered": len(loader.plastic_waste_by_state),
                "periods": "2018-19 to 2022-23",
                "source": "CPCB Plastic Waste Annual Report",
            },
            "pincode_directory": {
                "loaded": len(loader.pincode_directory) > 0,
                "records_count": len(loader.pincode_directory),
                "states_count": len(loader.states_list),
            },
            "pincode_boundaries": {
                "loaded": len(loader.pincode_features) > 0,
                "features_indexed": len(loader.pincode_features),
            },
            "state_boundaries": {
                "loaded": bool(loader.state_boundaries_fc),
                "states_count": len(loader.state_boundaries_fc.get("features", [])),
            },
            "cpcb_waste_composition": {
                "loaded": bool(loader.pdf_summary),
                "cities_studied": loader.pdf_summary.get("cities_studied", 59),
            },
        },
    }


@app.get("/api/heatmap")
async def get_heatmap(
    mode: str = Query("waste_generation", description="Heatmap mode: waste_generation, processing_gap, waste_to_energy, waste_composition"),
    view: str = Query("state", description="Granularity view: 'state' (choropleth) or 'pincode' (postal polygons)"),
    state: Optional[str] = Query(None, description="Filter by State name (e.g., 'Maharashtra', 'Delhi')"),
    district: Optional[str] = Query(None, description="Filter by District name"),
    pincode: Optional[str] = Query(None, description="Specific PIN code polygon to retrieve"),
    metric_type: str = Query("solid", description="For waste_generation: 'solid' or 'plastic'"),
    plastic_year: str = Query("2022-23", description="For plastic metric: reporting financial year"),
):
    valid_modes = ["waste_generation", "processing_gap", "waste_to_energy", "waste_composition"]
    if mode not in valid_modes:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode '{mode}'. Choose from: {', '.join(valid_modes)}",
        )

    geojson_data = get_heatmap_geojson(
        mode=mode,
        view=view,
        state=state,
        district=district,
        pincode=pincode,
        metric_type=metric_type,
        plastic_year=plastic_year,
    )
    return JSONResponse(content=geojson_data)


@app.get("/api/heatmap/details/{identifier}")
async def get_region_details(identifier: str):
    loader = DataLoader.get_instance()
    details = loader.get_region_details(identifier)
    if not details:
        raise HTTPException(
            status_code=404,
            detail=f"Region or PIN code '{identifier}' not found in database.",
        )
    return details


@app.get("/api/filters")
async def get_filters():
    loader = DataLoader.get_instance()
    return {
        "modes": [
            {
                "id": "waste_generation",
                "label": "Waste Generation",
                "description": "Solid waste generated (TPD) and Plastic waste (TPY) by State/UT.",
                "unit": "TPD / TPY",
                "icon": "Trash2",
            },
            {
                "id": "processing_gap",
                "label": "Unprocessed Waste / Processing Gap",
                "description": "Gap between generated waste and treated waste: (Generated - Treated).",
                "unit": "TPD / %",
                "icon": "AlertTriangle",
            },
            {
                "id": "waste_to_energy",
                "label": "Waste-to-Energy Potential",
                "description": "Theoretical electrical power generation capacity (MW) from MSW combustion.",
                "unit": "MW",
                "icon": "Zap",
            },
            {
                "id": "waste_composition",
                "label": "Waste Composition",
                "description": "Physical characterization (Compostable, Recyclables, Moisture, C:N) from CPCB 59-city study.",
                "unit": "%",
                "icon": "PieChart",
            },
        ],
        "views": [
            {"id": "state", "label": "State Overview (Official Reported Data)"},
            {"id": "pincode", "label": "PIN-Code Explorer (19,312 Postal Polygons)"},
        ],
        "states": sorted([s.title() for s in loader.states_list]),
        "districts_by_state": {
            st.title(): dists for st, dists in loader.districts_by_state.items()
        },
        "plastic_waste_years": ["2018-19", "2019-20", "2020-21", "2021-22", "2022-23"],
    }


@app.get("/api/sources")
async def get_sources():
    loader = DataLoader.get_instance()
    return {
        "datasets": [
            {
                "id": "solid_waste_statistics",
                "name": "Solid Waste Statistics (State/UT Level)",
                "publishing_body": "Central Pollution Control Board (CPCB), Ministry of Environment, Forest and Climate Change",
                "reporting_period": "2020-21",
                "metrics": [
                    "Solid Waste Generated (TPD)",
                    "Collected (TPD)",
                    "Treated (TPD)",
                ],
                "coverage": "35 States & Union Territories",
                "granularity": "State / Union Territory",
                "integrity_class": "Reported Official Figures",
                "file": "solid_waste_statistics.csv",
            },
            {
                "id": "plastic_waste_statistics",
                "name": "Plastic Waste Statistics (5-Year Historical)",
                "publishing_body": "Central Pollution Control Board (CPCB)",
                "reporting_period": "2018-19, 2019-20, 2020-21, 2021-22, 2022-23",
                "metrics": ["Annual Plastic Waste Generated (Tons Per Year - TPY)"],
                "coverage": "36 States & Union Territories",
                "granularity": "State / Union Territory",
                "integrity_class": "Reported Official Figures",
                "file": "plastic_waste_statistics.csv",
            },
            {
                "id": "cpcb_waste_composition_studies",
                "name": "Assessment of Status of MSW Management in Metro Cities and State Capitals",
                "publishing_body": "CPCB sponsored study executed by NEERI (National Environmental Engineering Research Institute)",
                "reporting_period": "Comprehensive City Baseline Study",
                "metrics": [
                    "Waste Generation Rate (0.12 - 0.60 kg/capita/day)",
                    "Compostable Matter (40 - 60%)",
                    "Recyclable Fraction (10 - 25%)",
                    "Moisture Content (30 - 60%)",
                    "C:N Ratio (20 - 40)",
                    "Compost Heavy Metal Concentrations (Pb, Ni, Cd, Hg)",
                ],
                "coverage": "59 Cities (35 Metro Cities and 24 State Capitals)",
                "granularity": "National 59-City Aggregate Baseline",
                "integrity_class": "Verified Research Publication",
                "file": "cpcb_waste_composition_studies.pdf",
            },
            {
                "id": "india_pincode_directory",
                "name": "All India Pincode Directory",
                "publishing_body": "Department of Posts, Ministry of Communications, Government of India (Data.gov.in)",
                "reporting_period": "Official Postal Master Directory",
                "metrics": [
                    "PIN Code",
                    "Post Office Name",
                    "District",
                    "State Name",
                    "Circle",
                    "Division",
                    "Latitude / Longitude",
                ],
                "coverage": "165,627 Post Offices across 19,586 unique PIN codes",
                "granularity": "Post Office / Postal PIN Code",
                "integrity_class": "Official Administrative Directory",
                "file": "india_pincode_directory.csv",
            },
            {
                "id": "pincode_boundaries",
                "name": "Data.gov.in Pincode Boundaries GeoJSON",
                "publishing_body": "Open Government Data (OGD) Platform India",
                "reporting_period": "National Spatial Boundary Dataset",
                "metrics": ["19,312 Postal Polygon Boundaries"],
                "coverage": "National coverage across 23 postal circles",
                "granularity": "Postal Delivery Area Polygons",
                "integrity_class": "Official Spatial Geometry",
                "file": "pincode_boundaries.geojson",
            },
        ],
    }


@app.get("/api/methodology")
async def get_methodology():
    return {
        "title": "Methodology, Calculation Parameters, and Data Integrity Standards",
        "data_integrity_principles": [
            "1. Zero Mock Data Policy: Every number presented originates from official CPCB reports or government spatial registries.",
            "2. No False Granularity: State-level waste statistics are never depicted as localized PIN-code measurements. Uniform spatial disaggregation is strictly prohibited.",
            "3. Explicit Provenance: Every data point is tagged as 'Reported Value', 'Calculated Estimate', or 'Data Unavailable'.",
            "4. Transparent Calculation: Conversion constants and equations are documented with academic and regulatory citations.",
        ],
        "calculations": {
            "unprocessed_waste_gap": {
                "formula": "Processing Gap (TPD) = Solid Waste Generated (TPD) - Treated (TPD)",
                "gap_percentage": "Processing Gap (%) = (Processing Gap / Solid Waste Generated) * 100",
                "collection_efficiency": "Collection Efficiency (%) = (Collected / Generated) * 100",
                "treatment_efficiency": "Treatment Efficiency (%) = (Treated / Generated) * 100",
                "null_handling": "Where CPCB records state 'NA' for Treated (e.g. Arunachal Pradesh, Bihar), the gap is explicitly returned as Unavailable with reasons documented.",
            },
            "waste_to_energy_potential": {
                "formula": "Power (MW) = (Waste_TPD * Combustible_Fraction * NCV_kcal_kg * Efficiency) / (24 * 860)",
                "regulatory_framework": "Ministry of New and Renewable Energy (MNRE) & CPCB Task Force on Waste to Energy",
                "parameters": {
                    "combustible_fraction": "0.20 (20% combustible dry fraction, matching CPCB 59-city study)",
                    "net_calorific_value_ncv": "1,100 kcal/kg (Documented typical range for Indian municipal solid waste: 1,000 - 1,200 kcal/kg)",
                    "plant_conversion_efficiency": "22% gross thermodynamic thermal-to-electric efficiency",
                    "energy_constant": "860 kcal per kWh",
                    "effective_multiplier": "0.002345 MW per Ton Per Day of MSW (~2.35 MW per 1,000 TPD)",
                },
                "pincode_restriction": "Waste-to-Energy potential is calculated only at State level where verified generation tonnages exist. PIN-code potential cannot be computed due to absence of local generation and calorific testing.",
            },
            "waste_composition": {
                "source": "CPCB / NEERI 59-City Field Investigation",
                "metrics": {
                    "compostable_organic": "40% - 60% (High moisture organic matter)",
                    "recyclables": "10% - 25% (Paper, plastics, glass, metals)",
                    "inert_matter": "25% - 40% (Street sweepings, construction dust, silt)",
                    "moisture_content": "30% - 60%",
                    "carbon_nitrogen_ratio": "20 - 40",
                },
                "limitation": "The dataset provides a national benchmark. PIN-code specific composition splits were not published in this CPCB dataset.",
            },
            "spatial_linkage": {
                "linkage_protocol": "Directory cross-referencing: 19,302 of 19,312 (99.95%) GeoJSON postal polygons match with post offices in india_pincode_directory.csv.",
                "boundary_simplification": "State boundaries were dissolved from postal boundaries and simplified with Shapely topology preservation (0.005 degree tolerance) to ensure fast 60fps rendering in web clients.",
            },
        },
        "limitations": [
            "Postal boundaries in GeoJSON represent postal delivery catchments rather than statutory municipal corporation wards.",
            "Reporting periods differ slightly across datasets: Solid waste is 2020-21, Plastic waste spans 2018-2023, and CPCB composition is from the 59-city baseline.",
            "Data gaps exist for newly formed Union Territories (e.g. Ladakh in solid waste) where historic reporting was integrated with parent states.",
        ],
    }


@app.get("/api/search")
async def search_regions(
    q: str = Query(..., min_length=1, description="Search query"),
    type: Optional[str] = Query(None, description="Search type: 'pincode', 'city', 'district', or 'all'"),
):
    loader = DataLoader.get_instance()
    query = q.strip().upper()
    search_type = (type or "all").lower().strip()
    results = []
    error_msg = None

    # --- 1. PIN CODE SEARCH ---
    if search_type in ("pincode", "all"):
        if search_type == "pincode" and (not query.isdigit() or len(query) != 6):
            if not query.isdigit():
                error_msg = "PIN code must be numeric (e.g. 110001)."
            else:
                error_msg = f"PIN code must be exactly 6 digits (you entered {len(query)} digits)."
        else:
            # Look up exact 6-digit match first
            if query in loader.pincode_directory:
                info = loader.pincode_directory[query]
                results.append({
                    "type": "pincode",
                    "id": f"pincode:{query}",
                    "title": f"PIN {query} - {info.get('officename', 'Post Office')}",
                    "subtitle": f"{info.get('district', '')}, {info.get('statename', '').title()}",
                    "state": info.get("statename", "").title(),
                    "district": info.get("district", ""),
                    "pincode": query,
                    "lat": clean_coord(info.get("latitude")),
                    "lon": clean_coord(info.get("longitude")),
                })
            elif search_type == "pincode":
                error_msg = f"PIN code {query} was not found in the India Post directory."

        # If prefix search in 'all' mode
        if search_type == "all" and not results:
            matched_pins = 0
            for pin, info in loader.pincode_directory.items():
                if query in pin or (len(query) >= 3 and query in info.get("officename", "").upper()):
                    results.append({
                        "type": "pincode",
                        "id": f"pincode:{pin}",
                        "title": f"PIN {pin} - {info.get('officename', '')}",
                        "subtitle": f"{info.get('district', '')}, {info.get('statename', '').title()}",
                        "state": info.get("statename", "").title(),
                        "district": info.get("district", ""),
                        "pincode": pin,
                        "lat": clean_coord(info.get("latitude")),
                        "lon": clean_coord(info.get("longitude")),
                    })
                    matched_pins += 1
                    if matched_pins >= 12:
                        break

    # --- 2. CITY SEARCH ---
    if search_type in ("city", "all"):
        matched_cities = 0
        seen_city_keys = set()

        # Check exact or partial city matches
        for c_upper, entries in loader.cities_by_name.items():
            if query == c_upper or (len(query) >= 3 and query in c_upper):
                for entry in entries:
                    unique_k = (entry["city"], entry["state"])
                    if unique_k in seen_city_keys:
                        continue
                    seen_city_keys.add(unique_k)
                    
                    is_59 = entry.get("is_cpcb_59_city", False)
                    badge_note = " • CPCB 59-City Study" if is_59 else ""
                    results.append({
                        "type": "city",
                        "id": entry["id"],
                        "title": f"{entry['city']} (City)",
                        "subtitle": f"District: {entry['district']}, State: {entry['state'].title()}{badge_note}",
                        "state": entry["state"].title(),
                        "district": entry["district"],
                        "city": entry["city"],
                        "pincode": entry["pincodes"][0] if entry.get("pincodes") else None,
                        "pincode_count": entry.get("pincode_count", 0),
                        "lat": clean_coord(entry.get("latitude")),
                        "lon": clean_coord(entry.get("longitude")),
                        "is_cpcb_studied": is_59,
                    })
                    matched_cities += 1
                    if matched_cities >= 15:
                        break
            if matched_cities >= 15:
                break

        if search_type == "city" and not results:
            error_msg = f"No matching city found for '{q}'."

    # --- 3. DISTRICT SEARCH ---
    if search_type in ("district", "all"):
        matched_dists = 0
        seen_dist_keys = set()

        q_terms = [query]
        norm_k = norm_karnataka_district(query)
        if norm_k and norm_k not in q_terms:
            q_terms.append(norm_k)

        for d_upper, entries in loader.districts_by_name.items():
            matches = False
            for qt in q_terms:
                if qt == d_upper or (len(qt) >= 3 and qt in d_upper) or (len(d_upper) >= 3 and d_upper in qt):
                    matches = True
                    break
            if matches:
                for entry in entries:
                    unique_k = (entry["district"], entry["state"])
                    if unique_k in seen_dist_keys:
                        continue
                    seen_dist_keys.add(unique_k)

                    results.append({
                        "type": "district",
                        "id": entry["id"],
                        "title": f"{entry['district']} District",
                        "subtitle": f"State: {entry['state'].title()} ({entry['pincode_count']} PIN areas)",
                        "state": entry["state"].title(),
                        "district": entry["district"],
                        "pincode": entry["pincodes"][0] if entry.get("pincodes") else None,
                        "pincode_count": entry["pincode_count"],
                        "lat": clean_coord(entry.get("latitude")),
                        "lon": clean_coord(entry.get("longitude")),
                    })
                    matched_dists += 1
                    if matched_dists >= 12:
                        break
            if matched_dists >= 12:
                break

        if search_type == "district" and not results:
            error_msg = f"No matching district found for '{q}'."

    # --- 4. STATE SEARCH (for 'all' mode) ---
    if search_type == "all":
        for st in loader.states_list:
            if query in st:
                results.append({
                    "type": "state",
                    "id": f"state:{st.lower()}",
                    "title": st.title(),
                    "subtitle": "State / Union Territory",
                    "state": st.title(),
                    "district": None,
                    "pincode": None,
                    "lat": None,
                    "lon": None,
                })

    return {
        "query": q,
        "type": search_type,
        "count": len(results),
        "results": results[:25],
        "error": error_msg,
    }
