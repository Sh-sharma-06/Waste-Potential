import json
import logging
import math
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd
import pypdf

from waste_calculator import (
    STATE_ALIASES,
    normalize_state,
    compute_solid_waste_stats,
    compute_plastic_waste_stats,
    compute_wte_potential,
    get_waste_composition_data,
)
from models import RegionDetails, FilterOptions

logger = logging.getLogger("india_waste_heatmap.data_loader")

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

def norm_karnataka_district(name: str) -> str:
    if not name:
        return ""
    c = re.sub(r'[^A-Za-z0-9]', '', str(name)).upper()
    aliases = {
        'BELLARY': 'BALLARI', 'BALLARI': 'BALLARI',
        'VIJAYNAGARA': 'VIJAYNAGAR', 'VIJAYNAGAR': 'VIJAYNAGAR',
        'DAVANAGERE': 'DAVANGERE', 'DAVANGERE': 'DAVANGERE',
        'BENGALURURURAL': 'BENGALURURURAL', 'BENGALURUR': 'BENGALURURURAL',
        'BENGALURUURBAN': 'BENGALURUURBAN', 'BENGALURUU': 'BENGALURUURBAN',
        'BANGALOREURBAN': 'BENGALURUURBAN', 'BANGALORERURAL': 'BENGALURURURAL',
        'BANGALORE': 'BENGALURUURBAN', 'BENGALURU': 'BENGALURUURBAN',
        'BBMP': 'BENGALURUURBAN',
        'VIJAYPURA': 'VIJAYAPURA', 'VIJAYAPURA': 'VIJAYAPURA', 'BIJAPUR': 'VIJAYAPURA',
        'BAGALKOTE': 'BAGALKOT', 'BAGALKOT': 'BAGALKOT',
        'UTTARAKANNDA': 'UTTARAKANNADA', 'UTTARAKANNADA': 'UTTARAKANNADA',
        'DAKSHINAKANNDA': 'DAKSHINAKANNADA', 'DAKSHINAKANNADA': 'DAKSHINAKANNADA',
        'KOPPALA': 'KOPPAL', 'KOPPAL': 'KOPPAL',
        'HASSANA': 'HASSAN', 'HASSAN': 'HASSAN',
        'TUMKURU': 'TUMAKURU', 'TUMAKURU': 'TUMAKURU', 'TUMKUR': 'TUMAKURU',
        'BELGAUM': 'BELAGAVI', 'BELAGAVI': 'BELAGAVI',
        'GULBARGA': 'KALABURAGI', 'KALABURAGI': 'KALABURAGI',
        'MYSORE': 'MYSURU', 'MYSURU': 'MYSURU',
        'SHIMOGA': 'SHIVAMOGGA', 'SHIVAMOGGA': 'SHIVAMOGGA',
        'CHIKMAGALUR': 'CHIKKAMAGALURU', 'CHIKKAMAGALURU': 'CHIKKAMAGALURU'
    }
    return aliases.get(c, c)


BASE_DIR = Path(__file__).resolve().parent.parent
DATASETS_DIR = BASE_DIR / "datasets" if (BASE_DIR / "datasets").exists() else BASE_DIR / "Datasets"
CACHE_DIR = BASE_DIR / "backend" / "cache"

# CPCB 59 Cities & State Capitals studied by NEERI
CPCB_59_CITIES: Dict[str, Dict[str, Any]] = {
    "NAGPUR": {
        "city": "Nagpur",
        "state": "MAHARASHTRA",
        "district": "Nagpur",
        "specific_notes": "CPCB/NEERI Landfill Gas Study at Bhandewadi disposal site: LFG flux measured at 0.57 to 16.5 mg/m2/sec. Per-capita waste generation rate: 0.12 - 0.60 kg/day.",
        "landfill_site": "Bhandewadi disposal site",
        "lfg_flux_mg_m2_sec": "0.57 to 16.5",
        "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day",
    },
    "AMRAVATI": {
        "city": "Amravati",
        "state": "MAHARASHTRA",
        "district": "Amravati",
        "specific_notes": "CPCB Landfill Gas Study at Sukhali landfill site (population 6.0 lakhs): LFG emission flux measured at 0.67 to 0.88 mg/m2/sec. Per-capita waste generation rate: 0.12 - 0.60 kg/day.",
        "landfill_site": "Sukhali landfill site",
        "lfg_flux_mg_m2_sec": "0.67 to 0.88",
        "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day",
    },
    "KOLKATA": {
        "city": "Kolkata",
        "state": "WEST BENGAL",
        "district": "Kolkata",
        "specific_notes": "CPCB Health Status Study through Chittaranjan Cancer Research Institute: Clinical examination of 732 individuals (376 conservancy staff of Kolkata Municipal Corporation, 151 ragpickers, 205 controls). Found high upper/lower respiratory infection rates and elevated PM10 exposure.",
        "health_study_institution": "Chittaranjan Cancer Research Institute",
        "study_participants": 732,
        "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day",
    },
    "CHENNAI": {
        "city": "Chennai",
        "state": "TAMIL NADU",
        "district": "Chennai",
        "specific_notes": "CPCB Health Status Study of municipal conservancy staff conducted with Sri Ramchandra Medical College. Evaluated occupational exposure and clinical biomarkers.",
        "health_study_institution": "Sri Ramchandra Medical College",
        "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day",
    },
    "DELHI": {"city": "Delhi", "state": "DELHI", "district": "New Delhi", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "MUMBAI": {"city": "Mumbai", "state": "MAHARASHTRA", "district": "Mumbai", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "PUNE": {"city": "Pune", "state": "MAHARASHTRA", "district": "Pune", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "AHMEDABAD": {"city": "Ahmedabad", "state": "GUJARAT", "district": "Ahmedabad", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "BENGALURU": {"city": "Bengaluru", "state": "KARNATAKA", "district": "Bengaluru Urban", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "HYDERABAD": {"city": "Hyderabad", "state": "TELANGANA", "district": "Hyderabad", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "JAIPUR": {"city": "Jaipur", "state": "RAJASTHAN", "district": "Jaipur", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "LUCKNOW": {"city": "Lucknow", "state": "UTTAR PRADESH", "district": "Lucknow", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "KANPUR": {"city": "Kanpur", "state": "UTTAR PRADESH", "district": "Kanpur Nagar", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "SURAT": {"city": "Surat", "state": "GUJARAT", "district": "Surat", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "PATNA": {"city": "Patna", "state": "BIHAR", "district": "Patna", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "BHOPAL": {"city": "Bhopal", "state": "MADHYA PRADESH", "district": "Bhopal", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "INDORE": {"city": "Indore", "state": "MADHYA PRADESH", "district": "Indore", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "LUDHIANA": {"city": "Ludhiana", "state": "PUNJAB", "district": "Ludhiana", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "AGRA": {"city": "Agra", "state": "UTTAR PRADESH", "district": "Agra", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "NASHIK": {"city": "Nashik", "state": "MAHARASHTRA", "district": "Nashik", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "VADODARA": {"city": "Vadodara", "state": "GUJARAT", "district": "Vadodara", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "FARIDABAD": {"city": "Faridabad", "state": "HARYANA", "district": "Faridabad", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "MEERUT": {"city": "Meerut", "state": "UTTAR PRADESH", "district": "Meerut", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "RAJKOT": {"city": "Rajkot", "state": "GUJARAT", "district": "Rajkot", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "VARANASI": {"city": "Varanasi", "state": "UTTAR PRADESH", "district": "Varanasi", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "SRINAGAR": {"city": "Srinagar", "state": "JAMMU AND KASHMIR", "district": "Srinagar", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "DHANBAD": {"city": "Dhanbad", "state": "JHARKHAND", "district": "Dhanbad", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "JODHPUR": {"city": "Jodhpur", "state": "RAJASTHAN", "district": "Jodhpur", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "AMRITSAR": {"city": "Amritsar", "state": "PUNJAB", "district": "Amritsar", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "RAIPUR": {"city": "Raipur", "state": "CHHATTISGARH", "district": "Raipur", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "ALLAHABAD": {"city": "Prayagraj (Allahabad)", "state": "UTTAR PRADESH", "district": "Prayagraj", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "COIMBATORE": {"city": "Coimbatore", "state": "TAMIL NADU", "district": "Coimbatore", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "JABALPUR": {"city": "Jabalpur", "state": "MADHYA PRADESH", "district": "Jabalpur", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "GWALIOR": {"city": "Gwalior", "state": "MADHYA PRADESH", "district": "Gwalior", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "VIJAYAWADA": {"city": "Vijayawada", "state": "ANDHRA PRADESH", "district": "NTR", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "MADURAI": {"city": "Madurai", "state": "TAMIL NADU", "district": "Madurai", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "GUWAHATI": {"city": "Guwahati", "state": "ASSAM", "district": "Kamrup Metropolitan", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "CHANDIGARH": {"city": "Chandigarh", "state": "CHANDIGARH", "district": "Chandigarh", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "SOLAPUR": {"city": "Solapur", "state": "MAHARASHTRA", "district": "Solapur", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "HUBLI": {"city": "Hubli-Dharwad", "state": "KARNATAKA", "district": "Dharwad", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "BAREILLY": {"city": "Bareilly", "state": "UTTAR PRADESH", "district": "Bareilly", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "MORADABAD": {"city": "Moradabad", "state": "UTTAR PRADESH", "district": "Moradabad", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "MYSORE": {"city": "Mysuru (Mysore)", "state": "KARNATAKA", "district": "Mysuru", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "GURGAON": {"city": "Gurugram (Gurgaon)", "state": "HARYANA", "district": "Gurugram", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "ALIGARH": {"city": "Aligarh", "state": "UTTAR PRADESH", "district": "Aligarh", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "JALANDHAR": {"city": "Jalandhar", "state": "PUNJAB", "district": "Jalandhar", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "TIRUCHIRAPPALLI": {"city": "Tiruchirappalli", "state": "TAMIL NADU", "district": "Tiruchirappalli", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "BHUBANESWAR": {"city": "Bhubaneswar", "state": "ODISHA", "district": "Khurda", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "SALEM": {"city": "Salem", "state": "TAMIL NADU", "district": "Salem", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "WARANGAL": {"city": "Warangal", "state": "TELANGANA", "district": "Warangal", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "THIRUVANANTHAPURAM": {"city": "Thiruvananthapuram", "state": "KERALA", "district": "Thiruvananthapuram", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "BHIWANDI": {"city": "Bhiwandi", "state": "MAHARASHTRA", "district": "Thane", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "SAHARANPUR": {"city": "Saharanpur", "state": "UTTAR PRADESH", "district": "Saharanpur", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "GUNTUR": {"city": "Guntur", "state": "ANDHRA PRADESH", "district": "Guntur", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "BIKANER": {"city": "Bikaner", "state": "RAJASTHAN", "district": "Bikaner", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "NOIDA": {"city": "Noida", "state": "UTTAR PRADESH", "district": "Gautam Buddha Nagar", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "JAMSHEDPUR": {"city": "Jamshedpur", "state": "JHARKHAND", "district": "East Singhbhum", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "CUTTACK": {"city": "Cuttack", "state": "ODISHA", "district": "Cuttack", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "FIROZABAD": {"city": "Firozabad", "state": "UTTAR PRADESH", "district": "Firozabad", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "KOCHI": {"city": "Kochi", "state": "KERALA", "district": "Ernakulam", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "DEHRADUN": {"city": "Dehradun", "state": "UTTARAKHAND", "district": "Dehradun", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "SHIMLA": {"city": "Shimla", "state": "HIMACHAL PRADESH", "district": "Shimla", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "PANAJI": {"city": "Panaji", "state": "GOA", "district": "North Goa", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "GANGTOK": {"city": "Gangtok", "state": "SIKKIM", "district": "East Sikkim", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "ITANAGAR": {"city": "Itanagar", "state": "ARUNACHAL PRADESH", "district": "Papum Pare", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "KOHIMA": {"city": "Kohima", "state": "NAGALAND", "district": "Kohima", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "SHILLONG": {"city": "Shillong", "state": "MEGHALAYA", "district": "East Khasi Hills", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "AIZAWL": {"city": "Aizawl", "state": "MIZORAM", "district": "Aizawl", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "AGARTALA": {"city": "Agartala", "state": "TRIPURA", "district": "West Tripura", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"},
    "IMPHAL": {"city": "Imphal", "state": "MANIPUR", "district": "Imphal West", "waste_rate_kg_day": "0.12 - 0.60 kg/capita/day"}
}


class DataLoader:
    _instance: Optional["DataLoader"] = None

    def __init__(self):
        self.solid_waste_by_state: Dict[str, Dict[str, Any]] = {}
        self.plastic_waste_by_state: Dict[str, Dict[str, Any]] = {}
        self.pincode_directory: Dict[str, Dict[str, Any]] = {}
        self.pincode_features: Dict[str, Dict[str, Any]] = {}  # pincode -> raw GeoJSON feature
        self.state_boundaries_fc: Dict[str, Any] = {}
        self.states_list: List[str] = []
        self.districts_by_state: Dict[str, List[str]] = {}
        self.pincodes_by_state: Dict[str, List[str]] = {}
        self.pincodes_by_district: Dict[Tuple[str, str], List[str]] = {}
        
        # Extended regional directories
        self.districts_directory: Dict[str, Dict[str, Any]] = {}  # id -> dict
        self.districts_by_name: Dict[str, List[Dict[str, Any]]] = {}  # district_upper -> list of dicts
        self.cities_directory: Dict[str, Dict[str, Any]] = {}  # id -> dict
        self.cities_by_name: Dict[str, List[Dict[str, Any]]] = {}  # city_upper -> list of dicts
        self.karnataka_district_stats: Dict[str, Dict[str, Any]] = {}  # norm_district -> dict

        self.pdf_summary: Dict[str, Any] = {}
        self.is_loaded = False

    @classmethod
    def get_instance(cls) -> "DataLoader":
        if cls._instance is None:
            cls._instance = DataLoader()
        return cls._instance

    def load_all(self):
        if self.is_loaded:
            return

        logger.info("Initializing DataLoader...")
        self._load_solid_waste()
        self._load_plastic_waste()
        self._load_pincode_directory()
        self._load_karnataka_district_data()
        self._load_pincode_features()
        self._load_state_boundaries()
        self._load_pdf()
        self.is_loaded = True
        logger.info("DataLoader initialization complete!")

    def _load_solid_waste(self):
        file_path = DATASETS_DIR / "solid_waste_statistics.csv"
        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return

        df = pd.read_csv(file_path)
        for _, row in df.iterrows():
            st_raw = str(row.get("State/UT", "")).strip()
            if not st_raw or st_raw.lower() == "total":
                continue
            st_norm = normalize_state(st_raw)
            self.solid_waste_by_state[st_norm] = {
                "State/UT": st_norm,
                "Solid waste generated (TPD)": row.get("Solid waste generated (TPD)"),
                "Collected (TPD)": row.get("Collected (TPD)"),
                "Treated (TPD)": row.get("Treated (TPD)"),
            }
        logger.info(f"Loaded solid waste stats for {len(self.solid_waste_by_state)} states.")

    def _load_plastic_waste(self):
        file_path = DATASETS_DIR / "plastic_waste_statistics.csv"
        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return

        df = pd.read_csv(file_path)
        for _, row in df.iterrows():
            st_raw = str(row.get("State/UT", "")).strip()
            if not st_raw or st_raw.lower() == "total":
                continue
            st_norm = normalize_state(st_raw)
            self.plastic_waste_by_state[st_norm] = {
                "State/UT": st_norm,
                "2018-19": row.get("2018-19"),
                "2019-20": row.get("2019-20"),
                "2020-21": row.get("2020-21"),
                "2021-22": row.get("2021-22"),
                "2022-23": row.get("2022-23"),
            }
        logger.info(f"Loaded plastic waste stats for {len(self.plastic_waste_by_state)} states.")

    def _load_pincode_directory(self):
        file_path = DATASETS_DIR / "india_pincode_directory.csv"
        if not file_path.exists():
            logger.warning(f"File not found: {file_path}")
            return

        df = pd.read_csv(file_path, low_memory=False)
        dist_set: Dict[str, set] = {}
        dist_acc: Dict[Tuple[str, str], Dict[str, Any]] = {}
        city_acc: Dict[Tuple[str, str], Dict[str, Any]] = {}

        for _, row in df.dropna(subset=["pincode"]).iterrows():
            pin_str = str(row["pincode"]).strip()
            st_raw = str(row.get("statename", "")).strip()
            st_norm = normalize_state(st_raw)
            district = str(row.get("district", "")).strip().title()
            office = str(row.get("officename", "")).strip()

            lat = clean_coord(row.get("latitude"))
            lon = clean_coord(row.get("longitude"))

            if pin_str not in self.pincode_directory:
                self.pincode_directory[pin_str] = {
                    "pincode": pin_str,
                    "officename": office,
                    "district": district,
                    "statename": st_norm,
                    "circle": str(row.get("circlename", "")).strip(),
                    "division": str(row.get("divisionname", "")).strip(),
                    "latitude": lat,
                    "longitude": lon,
                }

            if st_norm:
                if st_norm not in dist_set:
                    dist_set[st_norm] = set()
                if district:
                    dist_set[st_norm].add(district)

                if st_norm not in self.pincodes_by_state:
                    self.pincodes_by_state[st_norm] = []
                self.pincodes_by_state[st_norm].append(pin_str)

                if district:
                    key = (st_norm, district)
                    if key not in self.pincodes_by_district:
                        self.pincodes_by_district[key] = []
                    self.pincodes_by_district[key].append(pin_str)

                    # Accumulate district data
                    dist_key = (district.upper(), st_norm)
                    if dist_key not in dist_acc:
                        dist_acc[dist_key] = {
                            "district": district,
                            "state": st_norm,
                            "pincodes": set(),
                            "lat_sum": 0.0,
                            "lon_sum": 0.0,
                            "coord_count": 0,
                            "first_lat": lat,
                            "first_lon": lon,
                        }
                    elif dist_acc[dist_key]["first_lat"] is None and lat is not None:
                        dist_acc[dist_key]["first_lat"] = lat
                        dist_acc[dist_key]["first_lon"] = lon

                    dist_acc[dist_key]["pincodes"].add(pin_str)
                    if lat is not None and lon is not None:
                        dist_acc[dist_key]["lat_sum"] += lat
                        dist_acc[dist_key]["lon_sum"] += lon
                        dist_acc[dist_key]["coord_count"] += 1

            # Extract city / town candidates
            # 1. District itself is often the principal city
            if district and st_norm:
                city_key = (district.upper(), st_norm)
                if city_key not in city_acc:
                    city_acc[city_key] = {
                        "city": district,
                        "district": district,
                        "state": st_norm,
                        "pincodes": set(),
                        "lat": lat,
                        "lon": lon,
                    }
                elif city_acc[city_key]["lat"] is None and lat is not None:
                    city_acc[city_key]["lat"] = lat
                    city_acc[city_key]["lon"] = lon
                city_acc[city_key]["pincodes"].add(pin_str)

            # 2. Extract city/town from office name (if office is H.O or G.P.O or City)
            if office and st_norm:
                clean_office = re.sub(r'\s+(B\.O|S\.O|H\.O|G\.P\.O|BO|SO|HO|GPO)$', '', office, flags=re.I).strip()
                if clean_office and len(clean_office) > 3 and clean_office.upper() != district.upper():
                    # Only index significant post offices as local areas
                    clean_key = (clean_office.upper(), st_norm)
                    if clean_key not in city_acc:
                        city_acc[clean_key] = {
                            "city": clean_office.title(),
                            "district": district,
                            "state": st_norm,
                            "pincodes": set(),
                            "lat": lat,
                            "lon": lon,
                        }
                    elif city_acc[clean_key]["lat"] is None and lat is not None:
                        city_acc[clean_key]["lat"] = lat
                        city_acc[clean_key]["lon"] = lon
                    city_acc[clean_key]["pincodes"].add(pin_str)

        # Finalize districts directory
        for (dist_upper, st_norm), val in dist_acc.items():
            rep_lat = (val["lat_sum"] / val["coord_count"]) if val["coord_count"] > 0 else val["first_lat"]
            rep_lon = (val["lon_sum"] / val["coord_count"]) if val["coord_count"] > 0 else val["first_lon"]
            rep_lat = clean_coord(rep_lat)
            rep_lon = clean_coord(rep_lon)
            d_id = f"district:{val['district'].lower().replace(' ', '_')}_{st_norm.lower().replace(' ', '_')}"
            entry = {
                "id": d_id,
                "district": val["district"],
                "state": st_norm,
                "pincodes": sorted(list(val["pincodes"])),
                "pincode_count": len(val["pincodes"]),
                "latitude": rep_lat,
                "longitude": rep_lon,
            }
            self.districts_directory[d_id] = entry
            self.districts_directory[f"district:{val['district'].lower().replace(' ', '_')}"] = entry
            
            if dist_upper not in self.districts_by_name:
                self.districts_by_name[dist_upper] = []
            self.districts_by_name[dist_upper].append(entry)

        # Inject known CPCB 59 cities with rich metadata
        for city_upper, meta in CPCB_59_CITIES.items():
            st_norm = meta["state"]
            dist = meta.get("district", meta["city"])
            c_id = f"city:{meta['city'].lower().replace(' ', '_')}_{st_norm.lower().replace(' ', '_')}"
            
            # Find associated pincodes from directory
            pins = self.pincodes_by_district.get((st_norm, dist.title()), [])
            rep_lat = None
            rep_lon = None
            if pins:
                for p in pins[:5]:
                    p_info = self.pincode_directory.get(p)
                    if p_info and p_info.get("latitude"):
                        rep_lat = clean_coord(p_info["latitude"])
                        rep_lon = clean_coord(p_info["longitude"])
                        if rep_lat is not None and rep_lon is not None:
                            break

            entry = {
                "id": c_id,
                "city": meta["city"],
                "district": dist.title(),
                "state": st_norm,
                "pincodes": pins,
                "pincode_count": len(pins),
                "latitude": rep_lat,
                "longitude": rep_lon,
                "is_cpcb_59_city": True,
                "cpcb_meta": meta,
            }
            self.cities_directory[c_id] = entry
            self.cities_directory[f"city:{meta['city'].lower().replace(' ', '_')}"] = entry

            if city_upper not in self.cities_by_name:
                self.cities_by_name[city_upper] = []
            # Prepend CPCB 59 cities to top of matches
            self.cities_by_name[city_upper].insert(0, entry)

        # Also populate general cities
        for (c_upper, st_norm), val in city_acc.items():
            if c_upper in CPCB_59_CITIES:
                continue
            c_id = f"city:{val['city'].lower().replace(' ', '_')}_{st_norm.lower().replace(' ', '_')}"
            entry = {
                "id": c_id,
                "city": val["city"],
                "district": val["district"],
                "state": st_norm,
                "pincodes": sorted(list(val["pincodes"])),
                "pincode_count": len(val["pincodes"]),
                "latitude": clean_coord(val["lat"]),
                "longitude": clean_coord(val["lon"]),
                "is_cpcb_59_city": False,
                "cpcb_meta": None,
            }
            if c_id not in self.cities_directory:
                self.cities_directory[c_id] = entry
            if f"city:{val['city'].lower().replace(' ', '_')}" not in self.cities_directory:
                self.cities_directory[f"city:{val['city'].lower().replace(' ', '_')}"] = entry

            if c_upper not in self.cities_by_name:
                self.cities_by_name[c_upper] = []
            self.cities_by_name[c_upper].append(entry)

        self.states_list = sorted([s for s in dist_set.keys() if s])
        self.districts_by_state = {st: sorted(list(dists)) for st, dists in dist_set.items()}
        logger.info(f"Loaded {len(self.pincode_directory)} pincodes across {len(self.states_list)} states, {len(self.districts_by_name)} districts, and {len(self.cities_by_name)} cities.")

    def _load_karnataka_district_data(self):
        file_path = DATASETS_DIR / "karnataka_latest_district_data.csv"
        if not file_path.exists():
            file_path = DATASETS_DIR / "karnata_latest_district_data.csv"
        if not file_path.exists():
            logger.warning(f"Karnataka district dataset not found in {DATASETS_DIR}")
            return

        df = pd.read_csv(file_path)
        for _, row in df.iterrows():
            dist_raw = str(row.get("District", "")).strip()
            if not dist_raw or dist_raw.upper() in ("TOTAL", "DETAILS OF BBMP", "NAN"):
                continue

            def parse_num(val):
                try:
                    f = float(val)
                    return None if math.isnan(f) or math.isinf(f) else round(f, 2)
                except (ValueError, TypeError):
                    return None

            wet_gen = parse_num(row.get("Waste Gen - Wet Waste (TPD)"))
            dry_gen = parse_num(row.get("Waste Gen - Dry Waste (TPD)"))
            drain_silt = parse_num(row.get("Waste Gen - Drain Silt & Other Inert"))
            total_msw = parse_num(row.get("Total Municipal Solid Waste (TPD)"))
            cd_waste = parse_num(row.get("Construction & Debris Waste Gen (TPD)"))
            wet_proc = parse_num(row.get("Waste Processed - Wet Waste (TPD)"))
            dry_proc = parse_num(row.get("Waste Processed - Dry Waste (TPD)"))
            compost = parse_num(row.get("City Compost Generated (TPD)"))

            total_proc = None
            if wet_proc is not None or dry_proc is not None:
                total_proc = round((wet_proc or 0.0) + (dry_proc or 0.0), 2)

            gap_tpd = None
            gap_pct = None
            eff_pct = None
            if total_msw is not None and total_msw > 0:
                if total_proc is not None:
                    gap_tpd = round(max(0.0, total_msw - total_proc), 2)
                    eff_pct = round((total_proc / total_msw) * 100.0, 2)
                    gap_pct = round((gap_tpd / total_msw) * 100.0, 2)

            entry = {
                "has_district_data": True,
                "district_name": dist_raw,
                "state": "Karnataka",
                "reporting_period": "Latest SWM Profile (Economic Survey of Karnataka)",
                "source": "Directorate of Municipal Administration (DMA) / Urban Development Department, Government of Karnataka",
                "geographic_level": "District Administrative Area",
                "metrics_unit": "Tonnes Per Day (TPD)",
                "total_municipal_solid_waste_tpd": total_msw,
                "wet_waste_generated_tpd": wet_gen,
                "dry_waste_generated_tpd": dry_gen,
                "drain_silt_inert_tpd": drain_silt,
                "construction_debris_tpd": cd_waste,
                "wet_waste_processed_tpd": wet_proc,
                "dry_waste_processed_tpd": dry_proc,
                "total_waste_processed_tpd": total_proc,
                "city_compost_generated_tpd": compost,
                "processing_gap_tpd": gap_tpd,
                "processing_gap_percentage": gap_pct,
                "processing_efficiency_pct": eff_pct,
            }

            norm_k = norm_karnataka_district(dist_raw)
            self.karnataka_district_stats[norm_k] = entry
            self.karnataka_district_stats[dist_raw.upper()] = entry
            self.karnataka_district_stats[dist_raw.title()] = entry

            if dist_raw.upper() == "BBMP":
                bbmp_id = "district:bbmp_karnataka"
                bbmp_entry = {
                    "id": bbmp_id,
                    "district": "BBMP (Bruhat Bengaluru Mahanagara Palike)",
                    "state": "KARNATAKA",
                    "pincodes": self.pincodes_by_district.get(("KARNATAKA", "Bengaluru Urban"), []),
                    "pincode_count": len(self.pincodes_by_district.get(("KARNATAKA", "Bengaluru Urban"), [])),
                    "latitude": 12.9716,
                    "longitude": 77.5946,
                }
                self.districts_directory[bbmp_id] = bbmp_entry
                self.districts_by_name["BBMP"] = [bbmp_entry]

        logger.info(f"Loaded Karnataka district stats for {len(self.karnataka_district_stats)} district keys.")

    def _load_pincode_features(self):
        geojson_file = DATASETS_DIR / "Datagov_Pincode_Boundaries.geojson"
        if not geojson_file.exists():
            geojson_file = DATASETS_DIR / "pincode_boundaries.geojson"

        if not geojson_file.exists():
            logger.warning(f"GeoJSON file not found: {geojson_file}")
            return

        with open(geojson_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        for feat in data.get("features", []):
            pin = str(feat.get("properties", {}).get("Pincode", "")).strip()
            if pin:
                self.pincode_features[pin] = feat

        logger.info(f"Indexed {len(self.pincode_features)} GeoJSON pincode features.")

    def _load_state_boundaries(self):
        cache_file = CACHE_DIR / "state_boundaries.geojson"
        if cache_file.exists():
            with open(cache_file, "r", encoding="utf-8") as f:
                self.state_boundaries_fc = json.load(f)
            logger.info(f"Loaded {len(self.state_boundaries_fc.get('features', []))} cached state boundaries.")
        else:
            logger.warning("Cached state boundaries not found! Run precompute_boundaries.py first.")

    def _load_pdf(self):
        pdf_file = DATASETS_DIR / "CPCB_waste_composition.pdf"
        if not pdf_file.exists():
            pdf_file = DATASETS_DIR / "cpcb_waste_composition_studies.pdf"

        if not pdf_file.exists():
            logger.warning(f"PDF file not found: {pdf_file}")
            return

        try:
            reader = pypdf.PdfReader(str(pdf_file))
            text_pages = [page.extract_text() for page in reader.pages]
            self.pdf_summary = {
                "pages": len(reader.pages),
                "title": "Assessment of Status of Municipal Solid Wastes Management in Metro Cities and State Capitals",
                "cities_studied": 59,
                "metro_cities": 35,
                "state_capitals": 24,
                "per_capita_waste_kg_day": "0.12 - 0.60 kg",
                "compostable_matter_pct": "40 - 60%",
                "recyclable_fraction_pct": "10 - 25%",
                "moisture_content_pct": "30 - 60%",
                "cn_ratio": "20 - 40",
                "heavy_metals": {
                    "Lead": "47 - 185 mg/kg",
                    "Nickel": "36 - 63 mg/kg",
                    "Cadmium": "1.5 - 6.5 mg/kg",
                    "Mercury": "0.01 - 0.23 mg/kg"
                },
                "health_study_cities": ["Kolkata", "Chennai"],
                "lfg_study_cities": ["Nagpur", "Amravati"]
            }
            logger.info("Loaded CPCB composition study PDF summary.")
        except Exception as e:
            logger.error(f"Error parsing PDF: {e}")

    def _build_state_context(self, st_norm: str) -> Dict[str, Any]:
        """Build verified state statistics context for parent states."""
        solid_row = self.solid_waste_by_state.get(st_norm, {})
        plastic_row = self.plastic_waste_by_state.get(st_norm, {})
        solid_stats = compute_solid_waste_stats(solid_row, is_pincode=False)
        plastic_stats = compute_plastic_waste_stats(plastic_row, is_pincode=False)
        wte_stats = compute_wte_potential(solid_stats.generated_tpd, solid_stats.treated_tpd, is_pincode=False)

        return {
            "state_name": st_norm.title() if st_norm else "India",
            "solid_waste": solid_stats.model_dump(),
            "plastic_waste": plastic_stats.model_dump(),
            "waste_to_energy": wte_stats.model_dump(),
        }

    def get_region_details(self, identifier: str) -> Optional[RegionDetails]:
        ident = identifier.strip()

        # 1. PIN Code: starts with 'pincode:' or 6 digits
        is_pin = False
        pin_code = None
        if ident.startswith("pincode:"):
            is_pin = True
            pin_code = ident.split(":", 1)[1].strip()
        elif ident.isdigit() and len(ident) == 6:
            is_pin = True
            pin_code = ident
        elif ident in self.pincode_directory or ident in self.pincode_features:
            is_pin = True
            pin_code = ident

        if is_pin and pin_code:
            pin_info = self.pincode_directory.get(pin_code, {})
            feat = self.pincode_features.get(pin_code, {})
            props = feat.get("properties", {})

            st_norm = pin_info.get("statename") or normalize_state(props.get("Circle", ""))
            district = pin_info.get("district") or props.get("Division", "")
            office = pin_info.get("officename") or props.get("Office_Name", "")

            solid_row = self.solid_waste_by_state.get(st_norm, {})
            plastic_row = self.plastic_waste_by_state.get(st_norm, {})

            pin_solid = compute_solid_waste_stats(solid_row, is_pincode=True, state_name=st_norm)
            pin_plastic = compute_plastic_waste_stats(plastic_row, is_pincode=True)
            pin_wte = compute_wte_potential(None, is_pincode=True)
            composition = get_waste_composition_data()
            state_ctx = self._build_state_context(st_norm)

            # Check if this PIN belongs to a city studied by CPCB
            city_study = None
            for c_upper, c_meta in CPCB_59_CITIES.items():
                if (district and c_upper in district.upper()) or (office and c_upper in office.upper()):
                    city_study = {
                        "is_in_59_cities": True,
                        "city_name": c_meta["city"],
                        "waste_generation_rate": c_meta.get("waste_rate_kg_day", "0.12 - 0.60 kg/capita/day"),
                        "specific_notes": c_meta.get("specific_notes", "Studied under CPCB/NEERI 59-City Waste Characterization Project."),
                    }
                    break

            # Check if this PIN belongs to Karnataka and has district-level measurements
            karnataka_dist = None
            if st_norm and st_norm.upper() == "KARNATAKA" and district:
                nk = norm_karnataka_district(district)
                karnataka_dist = self.karnataka_district_stats.get(nk) or self.karnataka_district_stats.get(district.upper())

            if karnataka_dist:
                notice = (
                    f"Data Integrity Notice: PIN code {pin_code} ({office or district}) does not have direct postal-level "
                    f"waste generation measurements reported by CPCB. Verified district-level measurements for {karnataka_dist['district_name']} "
                    f"({karnataka_dist['total_municipal_solid_waste_tpd']} TPD total MSW, {karnataka_dist['total_waste_processed_tpd']} TPD processed) "
                    f"published by the Directorate of Municipal Administration (DMA), Government of Karnataka, are provided below. "
                    f"District statistics are never distributed equally across individual PIN codes."
                )
            else:
                notice = (
                    f"Data Integrity Notice: PIN code {pin_code} does not have direct postal-level waste generation "
                    f"or composition measurements reported by CPCB. Official data is collected and reported at the State/UT "
                    f"level ({st_norm.title() if st_norm else 'India'}). State-level context is presented below for reference "
                    f"and is never distributed equally across PIN codes."
                )

            return RegionDetails(
                identifier=f"pincode:{pin_code}",
                name=f"PIN {pin_code} - {office or district or 'Post Office'}",
                region_type="pincode",
                geographic_level="Postal PIN Code Area",
                pincode=pin_code,
                office_name=office,
                district=district,
                state=st_norm.title() if st_norm else "India",
                circle=pin_info.get("circle") or props.get("Circle"),
                division=pin_info.get("division") or props.get("Division"),
                latitude=clean_coord(pin_info.get("latitude")),
                longitude=clean_coord(pin_info.get("longitude")),
                pincode_count=1,
                data_integrity_notice=notice,
                solid_waste=pin_solid,
                plastic_waste=pin_plastic,
                waste_to_energy=pin_wte,
                waste_composition=composition,
                state_context=state_ctx,
                city_study=city_study,
                district_waste_stats=karnataka_dist,
            )

        # 2. City: starts with 'city:' or matches city in cities_directory
        city_match = None
        if ident.startswith("city:"):
            c_slug = ident.split(":", 1)[1].strip()
            city_match = self.cities_directory.get(ident) or self.cities_directory.get(f"city:{c_slug.lower()}")
            if not city_match:
                # Try finding in cities_by_name
                clean_name = c_slug.replace("_", " ").upper()
                for k, entries in self.cities_by_name.items():
                    if k in clean_name or clean_name in k:
                        city_match = entries[0]
                        break
        elif ident.upper() in self.cities_by_name:
            city_match = self.cities_by_name[ident.upper()][0]

        if city_match:
            city_name = city_match["city"]
            st_norm = city_match["state"]
            dist_name = city_match.get("district", city_name)
            pins = city_match.get("pincodes", [])

            state_ctx = self._build_state_context(st_norm)
            solid_row = self.solid_waste_by_state.get(st_norm, {})
            plastic_row = self.plastic_waste_by_state.get(st_norm, {})

            # State-level stats for display with explicit labeling
            state_solid = compute_solid_waste_stats(solid_row, is_pincode=False)
            state_plastic = compute_plastic_waste_stats(plastic_row, is_pincode=False)
            state_wte = compute_wte_potential(state_solid.generated_tpd, state_solid.treated_tpd, is_pincode=False)
            composition = get_waste_composition_data()

            # City study findings
            cpcb_meta = city_match.get("cpcb_meta") or CPCB_59_CITIES.get(city_name.upper())
            city_study = {
                "is_in_59_cities": True if cpcb_meta else False,
                "city_name": city_name,
                "waste_generation_rate": cpcb_meta.get("waste_rate_kg_day", "0.12 - 0.60 kg/capita/day") if cpcb_meta else "0.12 - 0.60 kg/capita/day (National 59-City Range)",
                "specific_notes": cpcb_meta.get("specific_notes", "Part of CPCB/NEERI National Waste Characterization Metro Studies.") if cpcb_meta else "City within parent state jurisdiction. Composition reflects CPCB 59-city baseline.",
                "landfill_site": cpcb_meta.get("landfill_site") if cpcb_meta else None,
                "lfg_flux_mg_m2_sec": cpcb_meta.get("lfg_flux_mg_m2_sec") if cpcb_meta else None,
            }

            # Check if this city is in Karnataka and has district-level measurements
            karnataka_dist = None
            if st_norm and st_norm.upper() == "KARNATAKA":
                nk = norm_karnataka_district(dist_name) or norm_karnataka_district(city_name)
                karnataka_dist = self.karnataka_district_stats.get(nk) or self.karnataka_district_stats.get(dist_name.upper())

            notice = (
                f"City-Level Intelligence: {city_name} is located in {dist_name} District, {st_norm.title()}. "
                f"Direct municipal solid waste characterization (0.12 - 0.60 kg/capita/day, 40-60% compostables) reflects "
                f"CPCB/NEERI studies. Macro waste totals shown below represent official State-level measurements for {st_norm.title()}."
            )

            return RegionDetails(
                identifier=f"city:{city_name.lower().replace(' ', '_')}_{st_norm.lower().replace(' ', '_')}",
                name=f"{city_name} (City)",
                region_type="city",
                geographic_level="City / Urban Area",
                city=city_name,
                district=dist_name,
                state=st_norm.title(),
                latitude=clean_coord(city_match.get("latitude")),
                longitude=clean_coord(city_match.get("longitude")),
                pincode_count=len(pins),
                data_integrity_notice=notice,
                solid_waste=state_solid,
                plastic_waste=state_plastic,
                waste_to_energy=state_wte,
                waste_composition=composition,
                state_context=state_ctx,
                city_study=city_study,
                district_waste_stats=karnataka_dist,
            )

        # 3. District: starts with 'district:' or matches district in districts_directory
        dist_match = None
        if ident.startswith("district:"):
            d_slug = ident.split(":", 1)[1].strip()
            dist_match = self.districts_directory.get(ident) or self.districts_directory.get(f"district:{d_slug.lower()}")
            if not dist_match:
                clean_name = d_slug.replace("_", " ").upper()
                for k, entries in self.districts_by_name.items():
                    if k in clean_name or clean_name in k:
                        dist_match = entries[0]
                        break
        elif ident.upper() in self.districts_by_name:
            dist_match = self.districts_by_name[ident.upper()][0]

        if dist_match:
            dist_name = dist_match["district"]
            st_norm = dist_match["state"]
            pins = dist_match.get("pincodes", [])

            state_ctx = self._build_state_context(st_norm)
            solid_row = self.solid_waste_by_state.get(st_norm, {})
            plastic_row = self.plastic_waste_by_state.get(st_norm, {})

            state_solid = compute_solid_waste_stats(solid_row, is_pincode=False)
            state_plastic = compute_plastic_waste_stats(plastic_row, is_pincode=False)
            state_wte = compute_wte_potential(state_solid.generated_tpd, state_solid.treated_tpd, is_pincode=False)
            composition = get_waste_composition_data()

            # Check if this district is in Karnataka and has verified DMA stats
            karnataka_dist = None
            if st_norm and st_norm.upper() == "KARNATAKA":
                nk = norm_karnataka_district(dist_name)
                karnataka_dist = self.karnataka_district_stats.get(nk) or self.karnataka_district_stats.get(dist_name.upper())

            if karnataka_dist:
                notice = (
                    f"District-Level Intelligence: {dist_name} District comprises {len(pins)} postal delivery areas in Karnataka. "
                    f"Official district-level solid waste generation and processing measurements ({karnataka_dist['total_municipal_solid_waste_tpd']} TPD total MSW, "
                    f"{karnataka_dist['total_waste_processed_tpd']} TPD processed) published by the Directorate of Municipal Administration (DMA), Government of Karnataka, "
                    f"are presented below. Macro Karnataka state totals are provided for reference."
                )
            else:
                notice = (
                    f"District-Level Overview: {dist_name} District comprises {len(pins)} postal delivery areas in {st_norm.title()}. "
                    f"Official CPCB solid and plastic waste statistics are published at the State/UT level. "
                    f"Parent state ({st_norm.title()}) statistics are provided below as verified context and are never distributed uniformly across districts."
                )

            return RegionDetails(
                identifier=f"district:{dist_name.lower().replace(' ', '_')}_{st_norm.lower().replace(' ', '_')}",
                name=f"{dist_name} (District)",
                region_type="district",
                geographic_level="District Administrative Area",
                district=dist_name,
                state=st_norm.title(),
                latitude=clean_coord(dist_match.get("latitude")),
                longitude=clean_coord(dist_match.get("longitude")),
                pincode_count=len(pins),
                data_integrity_notice=notice,
                solid_waste=state_solid,
                plastic_waste=state_plastic,
                waste_to_energy=state_wte,
                waste_composition=composition,
                state_context=state_ctx,
                city_study=None,
                district_waste_stats=karnataka_dist,
            )

        # 4. State / UT: starts with 'state:' or matches state name
        st_clean = ident.replace("state:", "").strip()
        st_norm = normalize_state(st_clean)
        if st_norm in self.solid_waste_by_state or st_norm in self.states_list or st_norm in self.plastic_waste_by_state:
            solid_row = self.solid_waste_by_state.get(st_norm, {})
            plastic_row = self.plastic_waste_by_state.get(st_norm, {})

            solid_stats = compute_solid_waste_stats(solid_row, is_pincode=False)
            plastic_stats = compute_plastic_waste_stats(plastic_row, is_pincode=False)
            wte_stats = compute_wte_potential(solid_stats.generated_tpd, solid_stats.treated_tpd, is_pincode=False)
            composition = get_waste_composition_data()

            notice = (
                f"Official State-Level Measurements: Solid waste and plastic waste statistics for {st_norm.title()} "
                f"are published directly by CPCB. Waste-to-Energy potential is an engineering estimate derived using "
                f"MNRE conversion parameters. Waste composition reflects the verified CPCB 59-City national baseline."
            )

            return RegionDetails(
                identifier=f"state:{st_norm.lower()}",
                name=st_norm.title(),
                region_type="state",
                geographic_level="State / Union Territory",
                pincode=None,
                office_name=None,
                district=None,
                state=st_norm.title(),
                circle=None,
                division=None,
                latitude=None,
                longitude=None,
                pincode_count=len(self.pincodes_by_state.get(st_norm, [])),
                data_integrity_notice=notice,
                solid_waste=solid_stats,
                plastic_waste=plastic_stats,
                waste_to_energy=wte_stats,
                waste_composition=composition,
                state_context=None,  # This IS the state
                city_study=None,
            )

        return None
