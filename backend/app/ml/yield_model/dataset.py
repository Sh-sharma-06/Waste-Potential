"""Real-data loader and data quality auditor for BMP and plant yield datasets.

Loads candidate BMP tables (expected at data/processed/bmp_table.csv) and runs rigorous
scientific data quality audits. All conversions to standard volatile-solids basis
(Nm3 biogas / kg VS) are delegated strictly to yield_model/units.py.

No fake data is generated. If the data file is missing, a FileNotFoundError points
the user to docs/DATASETS.md for compilation instructions.
"""

from collections import defaultdict
from dataclasses import dataclass, field
import os
from typing import Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd

from app.ml.yield_model.units import convert_to_vs_yield
from app.ml.yield_model.feedstocks import normalise_feedstock, FEEDSTOCK_NAMES

# Columns that define duplicate observations (keeping first occurrence)
DUPLICATE_KEY_COLUMNS = [
    "study_id",
    "feedstock",
    "temperature_c",
    "hrt_days",
    "yield_value",
    "yield_basis",
]

# Required columns for every valid observation
REQUIRED_COLUMNS = [
    "study_id",
    "feedstock",
    "yield_value",
    "yield_basis",
    "hrt_days",
    "temperature_c",
]


@dataclass
class AuditReport:
    """Detailed audit report logging all rejected rows and quality findings."""
    total_input_rows: int = 0
    clean_rows: int = 0
    dropped_count: int = 0
    dropped_rows: Dict[int, List[str]] = field(default_factory=dict)
    category_counts: Dict[str, int] = field(default_factory=dict)
    missing_optional_features: Dict[str, int] = field(default_factory=dict)
    invalid_composition_nulled: List[int] = field(default_factory=list)
    source_type_counts: Dict[str, int] = field(default_factory=lambda: {"real": 0, "synthetic": 0, "unknown": 0})

    def summary(self) -> str:
        """Formats the audit report into a human-readable text summary."""
        lines = [
            "==================================================",
            "DATA QUALITY AUDIT REPORT: BMP YIELD TABLE",
            "==================================================",
            f"Total input rows   : {self.total_input_rows}",
            f"Clean valid rows   : {self.clean_rows}",
            f"Dropped rows       : {self.dropped_count}",
            f"Source Types       : real={self.source_type_counts.get('real', 0)}, "
            f"synthetic={self.source_type_counts.get('synthetic', 0)}, "
            f"unknown={self.source_type_counts.get('unknown', 0)}",
            f"Nulled Compositions: {len(self.invalid_composition_nulled)} rows",
            "Issues by Category :",
        ]
        for cat, cnt in sorted(self.category_counts.items()):
            lines.append(f"  - {cat:26s}: {cnt}")
        lines.append("Missing Optional Features in Clean Data:")
        for feat, cnt in sorted(self.missing_optional_features.items()):
            lines.append(f"  - {feat:26s}: {cnt}")
        if self.dropped_rows:
            lines.append("Dropped Row Details (Index -> Reasons):")
            for idx in sorted(self.dropped_rows.keys()):
                lines.append(f"  Row {idx:3d}: {'; '.join(self.dropped_rows[idx])}")
        lines.append("==================================================")
        return "\n".join(lines)


def audit_bmp_dataframe(
    df: pd.DataFrame,
    buswell_ch4_ceiling: float = 0.551
) -> Tuple[pd.DataFrame, AuditReport]:
    """Audits raw BMP dataframe and converts valid yields to Nm3 biogas/kg VS.

    Audit Rules:
      1. study_id: Must be present and non-null (essential for GroupKFold).
      2. Required fields: feedstock, yield_value, yield_basis, hrt_days, temperature_c must not be null.
      3. Duplicates: Identifies duplicates based on DUPLICATE_KEY_COLUMNS, retains first, flags remainder.
      4. Temperature: Must be physically plausible for anaerobic digestion (10.0 C to 80.0 C).
      5. Physical ranges: yield_value > 0 and hrt_days > 0.
      6. Basis validity: yield_basis must be in {per_vs, per_ts, per_fresh}.
      7. Fractions: vs_of_ts required for per_ts; both ts_fraction and vs_of_ts required for per_fresh.
      8. CH4 fraction: If specified, must be in (0, 1.0].
      9. Buswell ceiling: Converted CH4 yield must not exceed buswell_ch4_ceiling (default 0.551).
      10. Optional features: olr and c_n are kept even if NaN, and tracked in missing_optional_features.

    Args:
        df: Raw pandas DataFrame.
        buswell_ch4_ceiling: Maximum theoretical methane yield (Nm3 CH4 / kg VS). Default 0.551.

    Returns:
        Tuple of (clean_df, audit_report).
    """
    report = AuditReport(total_input_rows=len(df))
    dropped_reasons: Dict[int, List[str]] = defaultdict(list)
    category_counts: Dict[str, int] = defaultdict(int)

    # Check for missing required columns in the dataframe schema itself
    missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing_cols:
        raise ValueError(f"BMP table is missing mandatory columns: {missing_cols}")

    # 1. Audit Duplicates (keeping first)
    avail_dup_cols = [c for c in DUPLICATE_KEY_COLUMNS if c in df.columns]
    dup_mask = df.duplicated(subset=avail_dup_cols, keep="first")
    for idx in df[dup_mask].index:
        dropped_reasons[int(idx)].append(f"duplicate_row (matches earlier row on {avail_dup_cols})")
        category_counts["duplicate_row"] += 1

    # Row-by-row audit
    valid_indices = []
    converted_biogas = []
    converted_ch4 = []
    clean_source_types = []
    clean_carbs = []
    clean_feedstocks = []
    clean_proteins = []
    clean_lipids = []

    for idx, row in df.iterrows():
        i = int(idx)
        # Validate feedstock label
        raw_feedstock = row.get("feedstock")
        try:
            norm_feedstock = normalise_feedstock(str(raw_feedstock))
            if norm_feedstock not in FEEDSTOCK_NAMES:
                raise ValueError

        except Exception:
            dropped_reasons[i].append(f"invalid_feedstock:{raw_feedstock}")
            category_counts["invalid_feedstock"] += 1
            continue

        # Check source_type (optional: real | synthetic | unknown)
        st_raw = row.get("source_type")
        if pd.isna(st_raw) or str(st_raw).strip() == "":
            st_clean = "unknown"
        else:
            st_str = str(st_raw).lower().strip()
            st_clean = st_str if st_str in ("real", "synthetic") else "unknown"
        report.source_type_counts[st_clean] += 1

        # Check composition (carb_share, protein_share, lipid_share)
        c_raw = row.get("carb_share")
        p_raw = row.get("protein_share")
        l_raw = row.get("lipid_share")
        has_c = pd.notna(c_raw)
        has_p = pd.notna(p_raw)
        has_l = pd.notna(l_raw)

        if has_c and has_p and has_l:
            try:
                cf, pf, lf = float(c_raw), float(p_raw), float(l_raw)
                if (0.0 <= cf <= 1.0) and (0.0 <= pf <= 1.0) and (0.0 <= lf <= 1.0) and abs(cf + pf + lf - 1.0) <= 0.02:
                    row_c, row_p, row_l = cf, pf, lf
                else:
                    # Sum or bounds invalid: keep row, set shares to NaN, report in audit
                    report.invalid_composition_nulled.append(i)
                    category_counts["invalid_composition_nulled"] += 1
                    row_c, row_p, row_l = np.nan, np.nan, np.nan
            except (ValueError, TypeError):
                report.invalid_composition_nulled.append(i)
                category_counts["invalid_composition_nulled"] += 1
                row_c, row_p, row_l = np.nan, np.nan, np.nan
        else:
            row_c = float(c_raw) if has_c else np.nan
            row_p = float(p_raw) if has_p else np.nan
            row_l = float(l_raw) if has_l else np.nan

        # Check study_id
        val_study = row.get("study_id")
        if pd.isna(val_study) or str(val_study).strip() == "":
            dropped_reasons[i].append("missing_or_null_study_id")
            category_counts["missing_or_null_study_id"] += 1

        # Check required fields
        for col in REQUIRED_COLUMNS:
            val = row.get(col)
            if col != "study_id" and (pd.isna(val) or (isinstance(val, str) and val.strip() == "")):
                dropped_reasons[i].append(f"missing_required_column_{col}")
                category_counts[f"missing_required_{col}"] += 1

        # If required columns are present, perform numeric & physical checks
        temp_c = row.get("temperature_c")
        if pd.notna(temp_c):
            try:
                t_val = float(temp_c)
                if not (10.0 <= t_val <= 80.0):
                    dropped_reasons[i].append(f"temperature_out_of_plausible_range_{t_val}C (expected 10-80 C)")
                    category_counts["temperature_out_of_range"] += 1
            except (ValueError, TypeError):
                dropped_reasons[i].append("invalid_temperature_numeric")
                category_counts["invalid_temperature"] += 1

        # Check physical positivity
        y_val = row.get("yield_value")
        if pd.notna(y_val):
            try:
                y_float = float(y_val)
                if y_float <= 0:
                    dropped_reasons[i].append(f"non_positive_yield_{y_float}")
                    category_counts["non_positive_yield"] += 1
            except (ValueError, TypeError):
                dropped_reasons[i].append("invalid_yield_numeric")
                category_counts["invalid_yield"] += 1

        hrt_val = row.get("hrt_days")
        if pd.notna(hrt_val):
            try:
                hrt_float = float(hrt_val)
                if hrt_float <= 0:
                    dropped_reasons[i].append(f"non_positive_hrt_{hrt_float}")
                    category_counts["non_positive_hrt"] += 1
            except (ValueError, TypeError):
                dropped_reasons[i].append("invalid_hrt_numeric")
                category_counts["invalid_hrt"] += 1

        # Optional OLR and C:N checks (only if present and non-null)
        olr_val = row.get("olr")
        if pd.notna(olr_val):
            try:
                if float(olr_val) <= 0:
                    dropped_reasons[i].append("non_positive_olr")
                    category_counts["non_positive_olr"] += 1
            except (ValueError, TypeError):
                dropped_reasons[i].append("invalid_olr_numeric")
                category_counts["invalid_olr"] += 1

        cn_val = row.get("c_n")
        if pd.notna(cn_val):
            try:
                if float(cn_val) <= 0:
                    dropped_reasons[i].append("non_positive_c_n")
                    category_counts["non_positive_c_n"] += 1
            except (ValueError, TypeError):
                dropped_reasons[i].append("invalid_c_n_numeric")
                category_counts["invalid_c_n"] += 1

        # Check CH4 fraction if provided
        ch4_frac_val = row.get("ch4_fraction")
        ch4_frac = 0.60
        if pd.notna(ch4_frac_val):
            try:
                ch4_frac = float(ch4_frac_val)
                if not (0.0 < ch4_frac <= 1.0):
                    dropped_reasons[i].append(f"invalid_ch4_fraction_{ch4_frac} (expected 0 < ch4 <= 1.0)")
                    category_counts["invalid_ch4_fraction"] += 1
            except (ValueError, TypeError):
                dropped_reasons[i].append("invalid_ch4_fraction_numeric")
                category_counts["invalid_ch4_fraction"] += 1

        # Check basis and required fractions
        basis = str(row.get("yield_basis", "")).lower().strip()
        allowed_bases = {"per_vs", "per_ts", "per_fresh", "vs", "ts", "fresh"}
        if basis not in allowed_bases:
            dropped_reasons[i].append(f"unknown_yield_basis_{basis}")
            category_counts["unknown_yield_basis"] += 1

        ts_frac = row.get("ts_fraction")
        vs_ts = row.get("vs_of_ts")
        ts_f_float = float(ts_frac) if pd.notna(ts_frac) else None
        vs_ts_float = float(vs_ts) if pd.notna(vs_ts) else None

        if basis in ("per_ts", "ts") and (vs_ts_float is None or not (0.0 < vs_ts_float <= 1.0)):
            dropped_reasons[i].append("missing_or_invalid_vs_of_ts_for_ts_basis")
            category_counts["missing_fractions"] += 1

        if basis in ("per_fresh", "fresh"):
            if ts_f_float is None or not (0.0 < ts_f_float <= 1.0):
                dropped_reasons[i].append("missing_or_invalid_ts_fraction_for_fresh_basis")
                category_counts["missing_fractions"] += 1
            if vs_ts_float is None or not (0.0 < vs_ts_float <= 1.0):
                dropped_reasons[i].append("missing_or_invalid_vs_of_ts_for_fresh_basis")
                category_counts["missing_fractions"] += 1

        # If no reasons yet, test yield conversion via units.py
        if i not in dropped_reasons:
            try:
                conv = convert_to_vs_yield(
                    yield_value=float(y_val),
                    from_basis=basis,
                    ts_fraction=ts_f_float,
                    vs_of_ts=vs_ts_float,
                    ch4_fraction=ch4_frac,
                    gas_type="biogas"
                )
                # Buswell bound check on methane yield
                if conv.y_ch4_nm3_per_kg_vs > buswell_ch4_ceiling:
                    dropped_reasons[i].append(
                        f"ch4_yield_{conv.y_ch4_nm3_per_kg_vs:.3f}_exceeds_buswell_bound_{buswell_ch4_ceiling:.3f}"
                    )
                    category_counts["buswell_ceiling_exceeded"] += 1
                else:
                    valid_indices.append(idx)
                    converted_biogas.append(conv.y_biogas_nm3_per_kg_vs)
                    converted_ch4.append(conv.y_ch4_nm3_per_kg_vs)
                    clean_source_types.append(st_clean)
                    clean_carbs.append(row_c)
                    clean_proteins.append(row_p)
                    clean_lipids.append(row_l)
                    clean_feedstocks.append(norm_feedstock)
            except Exception as e:
                dropped_reasons[i].append(f"conversion_failed_{str(e)}")
                category_counts["conversion_failed"] += 1

    # Assemble cleaned dataframe
    clean_df = df.loc[valid_indices].copy()
    clean_df["y_biogas_nm3_per_kg_vs"] = converted_biogas
    clean_df["y_ch4_nm3_per_kg_vs"] = converted_ch4
    clean_df["basis"] = "per kg VS"
    clean_df["source_type"] = clean_source_types

    clean_df["feedstock"] = clean_feedstocks
# Only include composition columns if they were present in input or populated
    if ("carb_share" in df.columns) or any(pd.notna(clean_carbs)):
        clean_df["carb_share"] = clean_carbs
        clean_df["protein_share"] = clean_proteins
        clean_df["lipid_share"] = clean_lipids

    # Report details
    report.clean_rows = len(clean_df)
    report.dropped_count = len(dropped_reasons)
    report.dropped_rows = dict(dropped_reasons)
    report.category_counts = dict(category_counts)

    # Track missing optional features in clean valid rows
    if "olr" in clean_df.columns:
        report.missing_optional_features["olr"] = int(clean_df["olr"].isna().sum())
    if "c_n" in clean_df.columns:
        report.missing_optional_features["c_n"] = int(clean_df["c_n"].isna().sum())

    return clean_df, report


def load_bmp_dataset(
    path: str = "data/processed/bmp_table.csv",
    buswell_ch4_ceiling: float = 0.551
) -> Tuple[pd.DataFrame, AuditReport]:
    """Loads a BMP dataset from CSV and runs the data quality audit.

    Args:
        path: Filepath to CSV file.
        buswell_ch4_ceiling: Buswell theoretical ceiling in Nm3 CH4 / kg VS.

    Returns:
        Tuple of (clean_df, audit_report).

    Raises:
        FileNotFoundError: If the file does not exist, citing docs/DATASETS.md.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"BMP dataset file not found at '{path}'. "
            f"Real BMP literature data must be compiled per docs/DATASETS.md."
        )

    # Skip comment lines beginning with '#'
    df = pd.read_csv(path, comment="#")
    return audit_bmp_dataframe(df, buswell_ch4_ceiling=buswell_ch4_ceiling)
