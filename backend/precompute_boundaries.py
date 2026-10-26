import json
import os
import sys
import time
from pathlib import Path
import pandas as pd
from shapely.geometry import shape, mapping
from shapely.ops import unary_union
from shapely.validation import make_valid

BASE_DIR = Path(__file__).resolve().parent.parent
DATASETS_DIR = BASE_DIR / "datasets" if (BASE_DIR / "datasets").exists() else BASE_DIR / "Datasets"
CACHE_DIR = BASE_DIR / "backend" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

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

def normalize_state(name: str) -> str:
    if not name:
        return ""
    clean = str(name).strip().upper()
    return STATE_ALIASES.get(clean, clean)

def main():
    pin_dir_file = DATASETS_DIR / "india_pincode_directory.csv"
    geojson_file = DATASETS_DIR / "Datagov_Pincode_Boundaries.geojson"
    if not geojson_file.exists():
        geojson_file = DATASETS_DIR / "pincode_boundaries.geojson"

    out_file = CACHE_DIR / "state_boundaries.geojson"
    # Remove existing cache to rebuild clean
    if out_file.exists():
        out_file.unlink()

    print("Reading pincode directory...")
    df_pin = pd.read_csv(pin_dir_file, low_memory=False)
    pin_to_state = {}
    for _, row in df_pin.dropna(subset=['pincode', 'statename']).iterrows():
        p = str(row['pincode']).strip()
        if p not in pin_to_state:
            pin_to_state[p] = normalize_state(row['statename'])

    print(f"Mapped {len(pin_to_state)} pincodes.")

    print(f"Loading GeoJSON: {geojson_file}...")
    t0 = time.time()
    with open(geojson_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    print(f"Loaded {len(data['features'])} features in {time.time()-t0:.2f}s")

    # Group polygons by state
    shapes_by_state = {}
    for feat in data['features']:
        p = str(feat['properties'].get('Pincode', '')).strip()
        st = pin_to_state.get(p)
        if not st:
            circle = feat['properties'].get('Circle', '').strip().upper()
            st = normalize_state(circle)
        if not st or st == "NORTH EASTERN":
            # If North Eastern circle, check region or division
            div = str(feat['properties'].get('Division', '')).strip().upper()
            if "MEGHALAYA" in div or "SHILLONG" in div:
                st = "MEGHALAYA"
            elif "MIZORAM" in div or "AIZAWL" in div:
                st = "MIZORAM"
            elif "NAGALAND" in div or "KOHIMA" in div:
                st = "NAGALAND"
            elif "TRIPURA" in div or "AGARTALA" in div:
                st = "TRIPURA"
            elif "MANIPUR" in div or "IMPHAL" in div:
                st = "MANIPUR"
            elif "ARUNACHAL" in div or "ITANAGAR" in div:
                st = "ARUNACHAL PRADESH"
            else:
                st = "ASSAM"

        geom_data = feat.get('geometry')
        if not geom_data:
            continue
        try:
            geom = shape(geom_data)
            if not geom.is_valid:
                geom = make_valid(geom)
            if st not in shapes_by_state:
                shapes_by_state[st] = []
            shapes_by_state[st].append(geom)
        except Exception:
            continue

    print(f"Dissolving {len(shapes_by_state)} states...")
    t0 = time.time()
    state_features = []
    
    for st, geom_list in sorted(shapes_by_state.items()):
        st_t0 = time.time()
        try:
            dissolved = unary_union(geom_list)
            simplified = dissolved.simplify(0.005, preserve_topology=True)
            state_features.append({
                "type": "Feature",
                "id": st,
                "properties": {
                    "state": st,
                    "name": st.title(),
                    "pincode_count": len(geom_list)
                },
                "geometry": mapping(simplified)
            })
            print(f"  {st:40s} ({len(geom_list):4d} pins) -> {time.time()-st_t0:.2f}s")
        except Exception as err:
            print(f"  ERROR dissolving {st}: {err}")

    fc = {
        "type": "FeatureCollection",
        "features": state_features
    }

    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(fc, f)

    print(f"Saved {len(state_features)} state polygons to {out_file} ({out_file.stat().st_size / 1024 / 1024:.2f} MB) in {time.time()-t0:.2f}s")

if __name__ == "__main__":
    main()
