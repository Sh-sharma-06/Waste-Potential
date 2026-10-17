"""Model training pipeline and model card generator for yield prediction.

Builds a reproducible ModelBundle from clean BMP DataFrame tables (from dataset.py).
Conducts grouped cross-validation (GroupKFold by study_id), prevents study leakage,
evaluates out-of-fold metrics, calibrates uncertainty spread, and produces an
audit-ready model card.
"""

import hashlib
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd
import scipy
import sklearn
from sklearn.model_selection import GroupKFold

from app.ml.registry.store import ModelBundle, save_bundle
from app.ml.yield_model.domain_guard import DomainGuard
from app.ml.yield_model.evaluate import calculate_metrics, assert_no_leakage
from app.ml.yield_model.kinetic import kinetic, fit_kinetic
from app.ml.yield_model.residual_gbr import ResidualGBR

# Minimum data requirements (placeholders; to be calibrated on real empirical datasets)
MIN_STUDIES: int = 5
MIN_ROWS_PER_FEEDSTOCK: int = 10
MIN_STUDIES_PER_FEEDSTOCK: int = 3

DEFAULT_BUSWELL_CH4_CEILING: float = 0.551  # Nm3 CH4 / kg VS
DEFAULT_CH4_FRACTION: float = 0.60


class InsufficientDataError(ValueError):
    """Raised when the clean dataset fails minimum study or observation requirements."""
    pass


def compute_table_hash(df: pd.DataFrame) -> str:
    """Computes a deterministic SHA-256 hash over sorted rows and columns."""
    sorted_cols = sorted(df.columns)
    df_sorted = df[sorted_cols].sort_values(by=sorted_cols).reset_index(drop=True)
    csv_bytes = df_sorted.to_csv(index=False).encode("utf-8")
    return hashlib.sha256(csv_bytes).hexdigest()


def _format_markdown_table(headers: List[str], rows: List[List[Any]]) -> str:
    """Formats a list of headers and row tuples into a markdown table string."""
    line_h = "| " + " | ".join(headers) + " |"
    line_s = "| " + " | ".join(["---"] * len(headers)) + " |"
    lines = [line_h, line_s]
    for r in rows:
        lines.append("| " + " | ".join(str(val) for val in r) + " |")
    return "\n".join(lines)


def train_from_table(
    df: pd.DataFrame,
    model_version: str = "yield-v0.2",
    synthetic: bool = False,
    output_bundle_dir: Optional[Union[str, Path]] = None,
    output_model_cards_dir: Optional[Union[str, Path]] = None,
    seed: int = 42,
    buswell_ch4_ceiling: float = DEFAULT_BUSWELL_CH4_CEILING,
    ch4_fraction: float = DEFAULT_CH4_FRACTION
) -> Tuple[ModelBundle, Path, Path]:
    """Trains L0, L1, and L2 yield models from clean data, saves bundle, and generates model card.

    Args:
        df: Cleaned DataFrame from dataset.py.
        model_version: Semantic version tag for this model run.
        synthetic: Boolean flag indicating if training data is synthetic.
        output_bundle_dir: Destination directory for ModelBundle.
        output_model_cards_dir: Destination directory for Markdown model card.
        seed: Random seed for model training and reproducibility.
        buswell_ch4_ceiling: Theoretical stoichiometric ceiling (Nm3 CH4 / kg VS).
        ch4_fraction: Volumetric CH4 fraction in biogas.

    Returns:
        Tuple of (ModelBundle, bundle_path, model_card_path).

    Raises:
        InsufficientDataError: If minimum studies or feedstock observation thresholds are not met.
    """
    ceiling_biogas = buswell_ch4_ceiling / ch4_fraction

    # 1. Deterministic Data Hashing
    data_hash = compute_table_hash(df)

    # 2. Check source_type when training production models (synthetic=False)
    if not synthetic:
        if "source_type" in df.columns:
            synth_count = int((df["source_type"].astype(str).str.lower().str.strip() == "synthetic").sum())
            unk_count = int((df["source_type"].isna() | df["source_type"].astype(str).str.lower().str.strip().isin(["unknown", ""])).sum())
        else:
            synth_count = 0
            unk_count = len(df)
        if synth_count > 0 or unk_count > 0:
            raise InsufficientDataError(
                f"Cannot train production model (synthetic=False): dataset contains {synth_count} synthetic rows "
                f"and {unk_count} unknown rows. Real training requires verified empirical data (source_type='real'). "
                f"Fix: add a 'source_type' column with 'real' or 'synthetic' to every row."
            )

    # 3. Feedstock filtering and minimum data checks
    excluded_feedstocks: Dict[str, str] = {}
    retained_feedstocks: List[str] = []

    for fs, group in df.groupby("feedstock"):
        n_rows = len(group)
        n_studies = group["study_id"].nunique()
        if n_rows < MIN_ROWS_PER_FEEDSTOCK:
            excluded_feedstocks[str(fs)] = (
                f"insufficient observations ({n_rows} rows < {MIN_ROWS_PER_FEEDSTOCK})"
            )
        elif n_studies < MIN_STUDIES_PER_FEEDSTOCK:
            excluded_feedstocks[str(fs)] = (
                f"insufficient studies ({n_studies} studies < {MIN_STUDIES_PER_FEEDSTOCK})"
            )
        else:
            retained_feedstocks.append(str(fs))

    retained_feedstocks.sort()
    df_filtered = df[df["feedstock"].isin(retained_feedstocks)].copy()

    if len(retained_feedstocks) == 0:
        raise InsufficientDataError(
            f"No feedstocks met minimum criteria (min {MIN_ROWS_PER_FEEDSTOCK} rows and "
            f"{MIN_STUDIES_PER_FEEDSTOCK} studies). Excluded: {excluded_feedstocks}"
        )

    distinct_studies = df_filtered["study_id"].unique()
    n_distinct_studies = len(distinct_studies)
    if n_distinct_studies < MIN_STUDIES:
        raise InsufficientDataError(
            f"Fewer than MIN_STUDIES ({MIN_STUDIES}) distinct studies after feedstock filtering: "
            f"got {n_distinct_studies} studies across retained feedstocks {retained_feedstocks}. "
            f"Excluded feedstocks: {excluded_feedstocks}"
        )

    # 3. Missing continuous features policy for L2
    # L0 and L1 train on all rows; L2 requires complete features (temp, hrt, olr, c_n)
    complete_mask = df_filtered["olr"].notna() & df_filtered["c_n"].notna()
    n_complete_rows = int(complete_mask.sum())
    complete_studies = df_filtered.loc[complete_mask, "study_id"].nunique()

    can_train_l2 = (n_complete_rows >= MIN_STUDIES * 2) and (complete_studies >= MIN_STUDIES)
    l2_skipped = not can_train_l2

    # 4. Grouped Cross-Validation (Out-of-Fold Evaluation)
    n_splits = min(5, n_distinct_studies)
    gkf = GroupKFold(n_splits=n_splits)

    n_total = len(df_filtered)
    oof_pred_l0 = np.full(n_total, np.nan)
    oof_pred_l1 = np.full(n_total, np.nan)
    oof_pred_l2 = np.full(n_total, np.nan)
    oof_evaluated_mask = np.zeros(n_total, dtype=bool)

    y_true_all = df_filtered["y_biogas_nm3_per_kg_vs"].values
    study_groups = df_filtered["study_id"].values
    feedstocks_all = df_filtered["feedstock"].values
    indices = np.arange(n_total)

    excluded_test_rows_count = 0

    for fold, (tr_idx, te_idx) in enumerate(gkf.split(indices, groups=study_groups)):
        assert_no_leakage(study_groups[tr_idx], study_groups[te_idx])

        tr_df = df_filtered.iloc[tr_idx]
        te_df = df_filtered.iloc[te_idx]

        # Check if any feedstock in test set is absent from training fold
        train_fs = set(tr_df["feedstock"].unique())
        valid_te_local_mask = te_df["feedstock"].isin(train_fs).values
        excluded_test_rows_count += int((~valid_te_local_mask).sum())

        valid_te_idx = te_idx[valid_te_local_mask]
        if len(valid_te_idx) == 0:
            continue

        oof_evaluated_mask[valid_te_idx] = True
        v_te_df = df_filtered.iloc[valid_te_idx]

        # Fit L0 on training fold
        l0_dict = {fs: float(tr_df[tr_df["feedstock"] == fs]["y_biogas_nm3_per_kg_vs"].median()) for fs in train_fs}
        oof_pred_l0[valid_te_idx] = [l0_dict[fs] for fs in v_te_df["feedstock"]]

        # Fit L1 on training fold
        tr_fs_idx = np.array([retained_feedstocks.index(fs) for fs in tr_df["feedstock"]])
        k_params = fit_kinetic(tr_fs_idx, tr_df["hrt_days"].values, tr_df["y_biogas_nm3_per_kg_vs"].values, n_fs=len(retained_feedstocks))

        te_fs_idx = np.array([retained_feedstocks.index(fs) for fs in v_te_df["feedstock"]])
        pred_l1_te = kinetic(k_params, te_fs_idx, v_te_df["hrt_days"].values)
        oof_pred_l1[valid_te_idx] = pred_l1_te

        # Fit L2 on training fold (only on complete-feature rows)
        if can_train_l2:
            tr_comp = tr_df[tr_df["olr"].notna() & tr_df["c_n"].notna()]
            v_te_comp = v_te_df[v_te_df["olr"].notna() & v_te_df["c_n"].notna()]

            if len(tr_comp) >= MIN_STUDIES and len(v_te_comp) > 0:
                tr_comp_fs_idx = np.array([retained_feedstocks.index(fs) for fs in tr_comp["feedstock"]])
                pk_tr_comp = kinetic(k_params, tr_comp_fs_idx, tr_comp["hrt_days"].values)

                # Feature matrix: one-hot feedstock + continuous [temp, hrt, olr, c_n]
                oh_tr = np.eye(len(retained_feedstocks))[tr_comp_fs_idx]
                X_tr = np.column_stack([
                    oh_tr,
                    tr_comp["temperature_c"].values,
                    tr_comp["hrt_days"].values,
                    tr_comp["olr"].values,
                    tr_comp["c_n"].values
                ])

                gbr = ResidualGBR(random_state=seed)
                gbr.fit(X_tr, tr_comp["y_biogas_nm3_per_kg_vs"].values, pk_tr_comp)

                te_comp_idx = v_te_comp.index.values
                te_comp_fs_idx = np.array([retained_feedstocks.index(fs) for fs in v_te_comp["feedstock"]])
                pk_te_comp = kinetic(k_params, te_comp_fs_idx, v_te_comp["hrt_days"].values)

                oh_te = np.eye(len(retained_feedstocks))[te_comp_fs_idx]
                X_te = np.column_stack([
                    oh_te,
                    v_te_comp["temperature_c"].values,
                    v_te_comp["hrt_days"].values,
                    v_te_comp["olr"].values,
                    v_te_comp["c_n"].values
                ])
                pred_l2_te, _ = gbr.predict_hybrid(X_te, pk_te_comp, buswell_ch4_bound=buswell_ch4_ceiling, ch4_fraction=ch4_fraction, guarded=False)
                oof_pred_l2[te_comp_idx] = pred_l2_te

    # 5. Apply Buswell ceiling to all OOF predictions before metrics calculation
    oof_pred_l0 = np.minimum(oof_pred_l0, ceiling_biogas)
    oof_pred_l1 = np.minimum(oof_pred_l1, ceiling_biogas)
    oof_pred_l2 = np.minimum(oof_pred_l2, ceiling_biogas)

    # 6. Evaluate metrics on identical subsets
    # Evaluate L2 vs L1 on the EXACT SAME complete-feature subset
    eval_mask_l1 = oof_evaluated_mask & (~np.isnan(oof_pred_l1))
    eval_mask_l2 = eval_mask_l1 & (~np.isnan(oof_pred_l2))

    metrics_dict: Dict[str, Any] = {
        "l2_skipped": bool(l2_skipped),
        "complete_feature_rows": n_complete_rows,
        "total_training_rows": n_total,
        "n_studies": n_distinct_studies,
        "excluded_test_rows_due_to_unseen_feedstock": excluded_test_rows_count,
    }

    # Overall metrics
    metrics_dict["l0_overall"] = calculate_metrics(y_true_all[eval_mask_l1], oof_pred_l0[eval_mask_l1])
    metrics_dict["l1_overall"] = calculate_metrics(y_true_all[eval_mask_l1], oof_pred_l1[eval_mask_l1])

    if can_train_l2 and eval_mask_l2.sum() > 0:
        m_l1_on_complete = calculate_metrics(y_true_all[eval_mask_l2], oof_pred_l1[eval_mask_l2])
        m_l2_on_complete = calculate_metrics(y_true_all[eval_mask_l2], oof_pred_l2[eval_mask_l2])
        metrics_dict["l1_complete_subset"] = m_l1_on_complete
        metrics_dict["l2_complete_subset"] = m_l2_on_complete

        # L2 beats L1 only if out-of-fold MAPE is strictly lower on identical rows
        l2_beats_l1 = bool(m_l2_on_complete["MAPE"] < m_l1_on_complete["MAPE"])
        metrics_dict["l2_beats_l1"] = l2_beats_l1
        metrics_dict["l2_comparison_rows"] = int(eval_mask_l2.sum())
    else:
        l2_beats_l1 = False
        metrics_dict["l2_beats_l1"] = False
        metrics_dict["l2_comparison_rows"] = 0

    # 7. Compute cv_residual_std_log from out-of-fold residuals of the primary model
    if l2_beats_l1:
        primary_pred = oof_pred_l2[eval_mask_l2]
        primary_actual = y_true_all[eval_mask_l2]
    else:
        primary_pred = oof_pred_l1[eval_mask_l1]
        primary_actual = y_true_all[eval_mask_l1]

    log_residuals = np.log(primary_actual / np.clip(primary_pred, 1e-6, None))
    cv_std = float(np.std(log_residuals, ddof=1)) if len(log_residuals) > 1 else 0.15
    metrics_dict["cv_residual_std_log"] = cv_std

    # Per-feedstock out-of-fold metrics
    per_fs_metrics: Dict[str, Dict[str, Any]] = {}
    for fs in retained_feedstocks:
        fs_mask = eval_mask_l1 & (feedstocks_all == fs)
        fs_count = int(fs_mask.sum())
        if fs_count > 0:
            per_fs_metrics[fs] = {
                "n": fs_count,
                "l0": calculate_metrics(y_true_all[fs_mask], oof_pred_l0[fs_mask]),
                "l1": calculate_metrics(y_true_all[fs_mask], oof_pred_l1[fs_mask]),
            }
            fs_l2_mask = eval_mask_l2 & (feedstocks_all == fs)
            if fs_l2_mask.sum() > 0:
                per_fs_metrics[fs]["l2"] = calculate_metrics(y_true_all[fs_l2_mask], oof_pred_l2[fs_l2_mask])
                per_fs_metrics[fs]["n_l2"] = int(fs_l2_mask.sum())

    metrics_dict["per_feedstock"] = per_fs_metrics

    # 8. Final Model Calibration on Full Clean Table
    all_fs_idx = np.array([retained_feedstocks.index(fs) for fs in df_filtered["feedstock"]])
    final_kinetic_params = fit_kinetic(all_fs_idx, df_filtered["hrt_days"].values, df_filtered["y_biogas_nm3_per_kg_vs"].values, n_fs=len(retained_feedstocks))

    y0_map = {fs: float(final_kinetic_params[i]) for i, fs in enumerate(retained_feedstocks)}
    kp_bundle = {
        "y0": y0_map,
        "mu": float(final_kinetic_params[len(retained_feedstocks)]),
        "k": float(final_kinetic_params[len(retained_feedstocks) + 1]),
    }

    final_gbr = None
    if can_train_l2:
        df_comp = df_filtered[complete_mask]
        comp_fs_idx = np.array([retained_feedstocks.index(fs) for fs in df_comp["feedstock"]])
        comp_pk = kinetic(final_kinetic_params, comp_fs_idx, df_comp["hrt_days"].values)
        oh_comp = np.eye(len(retained_feedstocks))[comp_fs_idx]
        X_comp = np.column_stack([
            oh_comp,
            df_comp["temperature_c"].values,
            df_comp["hrt_days"].values,
            df_comp["olr"].values,
            df_comp["c_n"].values
        ])
        final_gbr = ResidualGBR(random_state=seed)
        final_gbr.fit(X_comp, df_comp["y_biogas_nm3_per_kg_vs"].values, comp_pk)
        final_guard = DomainGuard(X_comp, feedstocks_seen=retained_feedstocks)
    else:
        # Fallback domain guard on available continuous features
        oh_all = np.eye(len(retained_feedstocks))[all_fs_idx]
        X_all = np.column_stack([
            oh_all,
            df_filtered["temperature_c"].values,
            df_filtered["hrt_days"].values,
            df_filtered["olr"].fillna(0.0).values,
            df_filtered["c_n"].fillna(0.0).values
        ])
        final_guard = DomainGuard(X_all, feedstocks_seen=retained_feedstocks)

    # 9. Assemble Model Bundle
    env_metadata = {
        "random_seed": seed,
        "numpy_version": np.__version__,
        "scipy_version": scipy.__version__,
        "sklearn_version": sklearn.__version__,
        "pandas_version": pd.__version__,
        "excluded_feedstocks": excluded_feedstocks,
    }

    bundle = ModelBundle(
        model_version=model_version,
        feedstocks_seen=retained_feedstocks,
        kinetic_params=kp_bundle,
        residual_model=final_gbr,
        domain_guard=final_guard,
        metrics=metrics_dict,
        training_data_hash=data_hash,
        synthetic=synthetic,
        feature_names=["feedstock_onehot", "temperature_c", "hrt_days", "olr", "c_n"],
        metadata=env_metadata
    )

    # 10. Save Bundle
    bundle_filename = f"yield_bundle_{model_version}_{data_hash[:8]}.joblib"
    saved_bundle_path = save_bundle(bundle, target_dir=output_bundle_dir, filename=bundle_filename)

    # 11. Write Model Card
    card_dir = Path(output_model_cards_dir) if output_model_cards_dir else (
        Path(__file__).resolve().parent.parent.parent.parent.parent / "docs" / "model_cards"
    )
    card_dir.mkdir(parents=True, exist_ok=True)
    card_filename = f"model_card_{model_version}_{data_hash[:8]}.md"
    card_path = card_dir / card_filename

    card_content = generate_model_card(bundle, data_hash, excluded_feedstocks)
    with open(card_path, "w", encoding="utf-8") as f:
        f.write(card_content)

    return bundle, saved_bundle_path, card_path


def generate_model_card(
    bundle: ModelBundle,
    data_hash: str,
    excluded_feedstocks: Dict[str, str]
) -> str:
    """Generates an audit-ready Markdown Model Card from bundle metadata and out-of-fold metrics."""
    m = bundle.metrics
    lines = []

    if bundle.synthetic:
        lines.append("> [!WARNING]")
        lines.append("> **SYNTHETIC DATA WARNING:** This model was trained on synthetic benchmark data generated for software pipeline verification. It reflects NO empirical real-world validation.")
        lines.append("")

    lines.append(f"# Model Card: {bundle.model_version}")
    lines.append("")
    lines.append(f"**Data SHA-256 Hash:** `{data_hash}`  ")
    lines.append(f"**Synthetic Flag:** `{bundle.synthetic}`  ")
    lines.append(f"**Number of Training Observations:** {m.get('total_training_rows', 0)}  ")
    lines.append(f"**Number of Distinct Studies:** {m.get('n_studies', 0)}  ")
    lines.append(f"**Complete-Feature Rows (for L2):** {m.get('complete_feature_rows', 0)}  ")
    lines.append(f"**L2 Evaluated:** `{not m.get('l2_skipped', True)}`  ")
    lines.append(f"**L2 Beats L1 on Out-of-Fold MAPE:** `{m.get('l2_beats_l1', False)}`  ")
    lines.append(f"**Out-of-Fold Residual Spread (sigma_log):** `{m.get('cv_residual_std_log', 0.0):.4f}`  ")
    lines.append("")

    lines.append("## Validated Feedstocks")
    lines.append(f"- Retained feedstocks: {', '.join(bundle.feedstocks_seen)}")
    if excluded_feedstocks:
        lines.append("- Excluded feedstocks (below threshold):")
        for fs, reason in excluded_feedstocks.items():
            lines.append(f"  - `{fs}`: {reason}")
    lines.append("")

    lines.append("## Out-of-Fold Cross-Validation Performance")
    lines.append("*All error metrics are evaluated exclusively out-of-fold across unseen studies using GroupKFold. Training set metrics are strictly omitted.*")
    lines.append("")

    # Overall metrics table
    headers = ["Model Level", "MAE (Nm3/kg VS)", "RMSE (Nm3/kg VS)", "Bias (Nm3/kg VS)", "MAPE (%)"]
    rows = []
    if "l0_overall" in m:
        l0 = m["l0_overall"]
        rows.append(["L0 (Static Median)", f"{l0['MAE']:.3f}", f"{l0['RMSE']:.3f}", f"{l0['bias']:.3f}", f"{l0['MAPE']:.1f}%"])
    if "l1_overall" in m:
        l1 = m["l1_overall"]
        rows.append(["L1 (Kinetic Chen-Hashimoto)", f"{l1['MAE']:.3f}", f"{l1['RMSE']:.3f}", f"{l1['bias']:.3f}", f"{l1['MAPE']:.1f}%"])
    if "l2_complete_subset" in m:
        l2 = m["l2_complete_subset"]
        rows.append(["L2 (Kinetic + GBR Residual)", f"{l2['MAE']:.3f}", f"{l2['RMSE']:.3f}", f"{l2['bias']:.3f}", f"{l2['MAPE']:.1f}%"])
    lines.append(_format_markdown_table(headers, rows))
    lines.append("")

    # Per-feedstock table
    if "per_feedstock" in m and m["per_feedstock"]:
        lines.append("### Per-Feedstock Out-of-Fold Breakdown")
        fs_headers = ["Feedstock", "Sample Count", "L0 MAPE (%)", "L1 MAPE (%)", "L2 MAPE (%)"]
        fs_rows = []
        for fs, data in m["per_feedstock"].items():
            l0_mape = f"{data['l0']['MAPE']:.1f}%"
            l1_mape = f"{data['l1']['MAPE']:.1f}%"
            l2_mape = f"{data['l2']['MAPE']:.1f}%" if "l2" in data else "N/A"
            fs_rows.append([fs, data["n"], l0_mape, l1_mape, l2_mape])
        lines.append(_format_markdown_table(fs_headers, fs_rows))
        lines.append("")

    lines.append("## Training Domain Bounds (DomainGuard)")
    lines.append("Inputs exceeding these feature bounds trigger the extrapolation guardrail and fall back to L1 physics:")
    lines.append(f"- Feedstocks seen: `[{', '.join(bundle.feedstocks_seen)}]`")
    if bundle.domain_guard is not None and len(bundle.domain_guard.lo) > 0:
        n_fs = len(bundle.feedstocks_seen)
        lo = bundle.domain_guard.lo
        hi = bundle.domain_guard.hi
        if len(lo) >= n_fs + 4:
            lines.append(f"- `temperature_c`: {lo[n_fs]:.1f} C to {hi[n_fs]:.1f} C")
            lines.append(f"- `hrt_days`: {lo[n_fs + 1]:.1f} days to {hi[n_fs + 1]:.1f} days")
            lines.append(f"- `olr`: {lo[n_fs + 2]:.2f} to {hi[n_fs + 2]:.2f} kg VS/(m3*d)")
            lines.append(f"- `c_n`: {lo[n_fs + 3]:.1f} to {hi[n_fs + 3]:.1f}")
        elif len(lo) >= n_fs + 2:
            lines.append(f"- `temperature_c`: {lo[n_fs]:.1f} C to {hi[n_fs]:.1f} C")
            lines.append(f"- `hrt_days`: {lo[n_fs + 1]:.1f} days to {hi[n_fs + 1]:.1f} days")
    lines.append("")

    lines.append("## Known Limitations & Architectural Invariants")
    lines.append("1. **No Free-Form Generation:** Yield values are bounded strictly by stoichiometric Buswell limits ($0.551 / 0.60\\text{ Nm}^3/\\text{kg VS}$).")
    lines.append("2. **Grouped Partitions:** All cross-validation enforces zero leakage across distinct study/plant identifiers.")
    lines.append("3. **Extrapolation Fallback:** If input features extrapolate outside training bounds or if optional features are omitted, the engine strictly defaults to L1 kinetics.")
    lines.append("4. **Uncertainty Interval:** The prediction interval is derived from out-of-fold log residual variance and is widened by 2.5x under extrapolation. It is an empirical spread indicator, NOT a statistical confidence guarantee.")

    return "\n".join(lines)
