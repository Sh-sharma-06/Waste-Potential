"""Unit tests for yield_model/train.py (training pipeline & model cards)."""

import math
from pathlib import Path
import pytest
import numpy as np
import pandas as pd

from app.ml.registry.store import load_bundle
from app.ml.yield_model.predict import estimate
from app.ml.yield_model.train import (
    train_from_table,
    InsufficientDataError,
    compute_table_hash,
    MIN_STUDIES,
    MIN_ROWS_PER_FEEDSTOCK
)


def _generate_synthetic_clean_table(n_studies: int = 10, rows_per_study: int = 15) -> pd.DataFrame:
    """Helper creating a synthetic clean DataFrame adhering to dataset.py output format."""
    rng = np.random.default_rng(123)
    feedstocks = ["food", "manure", "crop", "mixed"]

    rows = []
    for s_idx in range(n_studies):
        study_id = f"study_{s_idx:02d}"
        for _ in range(rows_per_study):
            fs = str(rng.choice(feedstocks))
            hrt = float(rng.uniform(15.0, 50.0))
            temp = float(rng.choice([35.0, 37.0, 55.0]))
            olr = float(rng.uniform(1.5, 6.0))
            cn = float(rng.uniform(10.0, 30.0))

            # Approximate yield formula
            y0 = {"food": 0.85, "manure": 0.35, "crop": 0.50, "mixed": 0.65}[fs]
            y_val = y0 * (1.0 - 0.8 / (hrt * 0.4 - 1.0 + 0.8)) * float(rng.lognormal(0, 0.05))
            y_val = min(y_val, 0.551 / 0.60)

            rows.append({
                "study_id": study_id,
                "feedstock": fs,
                "y_biogas_nm3_per_kg_vs": y_val,
                "y_ch4_nm3_per_kg_vs": y_val * 0.60,
                "hrt_days": hrt,
                "temperature_c": temp,
                "olr": olr,
                "c_n": cn,
                "basis": "per kg VS",
                "method": "Batch",
                "source": "SyntheticTestGen"
            })

    return pd.DataFrame(rows)


def test_too_few_studies_raises_insufficient_data_error(tmp_path: Path):
    """Refuses to train if distinct study_ids are below MIN_STUDIES."""
    df_small = _generate_synthetic_clean_table(n_studies=MIN_STUDIES - 1, rows_per_study=15)
    with pytest.raises(InsufficientDataError) as ctx:
        train_from_table(
            df_small,
            output_bundle_dir=tmp_path / "bundles",
            output_model_cards_dir=tmp_path / "cards"
        )
    assert f"Fewer than MIN_STUDIES ({MIN_STUDIES})" in str(ctx.value)


def test_low_count_feedstock_excluded_and_reported(tmp_path: Path):
    """Feedstocks with fewer observations than MIN_ROWS_PER_FEEDSTOCK are excluded and logged."""
    df = _generate_synthetic_clean_table(n_studies=8, rows_per_study=12)

    # Inject a rare feedstock with only 3 observations (< MIN_ROWS_PER_FEEDSTOCK = 10)
    rare_rows = pd.DataFrame([
        {
            "study_id": "study_00",
            "feedstock": "rare_algae",
            "y_biogas_nm3_per_kg_vs": 0.40,
            "y_ch4_nm3_per_kg_vs": 0.24,
            "hrt_days": 25.0,
            "temperature_c": 37.0,
            "olr": 2.5,
            "c_n": 15.0,
            "basis": "per kg VS"
        }
        for _ in range(3)
    ])
    df_with_rare = pd.concat([df, rare_rows], ignore_index=True)

    bundle, bundle_path, card_path = train_from_table(
        df_with_rare,
        output_bundle_dir=tmp_path / "bundles",
        output_model_cards_dir=tmp_path / "cards",
        synthetic=True
    )

    # rare_algae must NOT be in feedstocks_seen
    assert "rare_algae" not in bundle.feedstocks_seen
    # Must be logged in metadata excluded_feedstocks
    assert "rare_algae" in bundle.metadata["excluded_feedstocks"]
    assert "insufficient observations" in bundle.metadata["excluded_feedstocks"]["rare_algae"]


def test_bundle_saved_and_loadable_with_estimate(tmp_path: Path):
    """Bundle is saved, loadable, and estimate() computes valid predictions."""
    df = _generate_synthetic_clean_table(n_studies=6, rows_per_study=15)
    bundle_dir = tmp_path / "models"
    card_dir = tmp_path / "cards"

    bundle, bundle_path, card_path = train_from_table(
        df,
        model_version="test-pipe-v1.0",
        synthetic=True,
        output_bundle_dir=bundle_dir,
        output_model_cards_dir=card_dir
    )

    assert bundle_path.exists()
    assert card_path.exists()

    loaded_bundle = load_bundle(model_dir=bundle_dir, filename=bundle_path.name)
    assert loaded_bundle.model_version == "test-pipe-v1.0"
    assert loaded_bundle.synthetic is True

    # Test estimate() using the trained bundle
    op = {"hrt_days": 30.0, "temperature_c": 37.0, "olr": 3.0, "c_n": 20.0}
    est = estimate("food", op, bundle=loaded_bundle)
    assert est.basis == "per kg VS"
    assert est.y_biogas_nm3_per_kg_vs > 0.0
    assert "SYNTHETIC" in est.model_version


def test_cv_residual_std_log_exists_and_positive(tmp_path: Path):
    """Ensures out-of-fold cv_residual_std_log exists and is positive."""
    df = _generate_synthetic_clean_table(n_studies=6, rows_per_study=15)
    bundle, _, _ = train_from_table(
        df,
        output_bundle_dir=tmp_path / "models",
        output_model_cards_dir=tmp_path / "cards",
        synthetic=True
    )

    cv_std = bundle.metrics.get("cv_residual_std_log")
    assert cv_std is not None
    assert isinstance(cv_std, float)
    assert cv_std > 0.0


def test_synthetic_warning_in_model_card(tmp_path: Path):
    """When synthetic=True, model card displays bold synthetic warning and model_version reflects it."""
    df = _generate_synthetic_clean_table(n_studies=6, rows_per_study=15)
    bundle, _, card_path = train_from_table(
        df,
        model_version="demo-synth-v0.2",
        synthetic=True,
        output_bundle_dir=tmp_path / "models",
        output_model_cards_dir=tmp_path / "cards"
    )

    card_text = card_path.read_text(encoding="utf-8")
    assert "**SYNTHETIC DATA WARNING:**" in card_text
    assert "**Synthetic Flag:** `True`" in card_text

    est = estimate("food", {"hrt_days": 30.0, "temperature_c": 37.0, "olr": 3.0, "c_n": 20.0}, bundle=bundle)
    assert "demo-synth-v0.2-SYNTHETIC" == est.model_version


def test_l2_beats_l1_false_returns_l1_as_primary(tmp_path: Path):
    """When l2_beats_l1 is False, predict.py strictly serves L1 as the primary prediction."""
    df = _generate_synthetic_clean_table(n_studies=6, rows_per_study=15)
    bundle, _, _ = train_from_table(
        df,
        output_bundle_dir=tmp_path / "models",
        output_model_cards_dir=tmp_path / "cards",
        synthetic=True
    )

    # Manually override bundle metrics to simulate L2 failing to beat L1
    bundle.metrics["l2_beats_l1"] = False

    op = {"hrt_days": 30.0, "temperature_c": 37.0, "olr": 3.0, "c_n": 20.0}
    res = estimate("food", op, bundle=bundle)

    # In-domain, but primary prediction MUST equal kinetic L1
    assert res.extrapolation_flag is False
    assert math.isclose(res.y_biogas_nm3_per_kg_vs, res.y_kinetic_nm3_per_kg_vs, rel_tol=1e-7)


def test_deterministic_table_hash():
    """Table hash is deterministic regardless of row/column shuffling."""
    df1 = pd.DataFrame({
        "study_id": ["s1", "s2"],
        "feedstock": ["food", "manure"],
        "y_biogas_nm3_per_kg_vs": [0.55, 0.35]
    })
    # Reverse rows and columns
    df2 = pd.DataFrame({
        "y_biogas_nm3_per_kg_vs": [0.35, 0.55],
        "study_id": ["s2", "s1"],
        "feedstock": ["manure", "food"]
    })
    assert compute_table_hash(df1) == compute_table_hash(df2)
