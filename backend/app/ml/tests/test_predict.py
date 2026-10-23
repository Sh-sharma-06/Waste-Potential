"""Unit tests for yield_model/predict.py and registry/store.py."""

import math
from pathlib import Path
import pytest
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor
from app.schemas.ml import YieldEstimate

from app.ml.registry.store import ModelBundle, NoTrainedModelError, save_bundle
from app.ml.yield_model.domain_guard import DomainGuard
from app.ml.yield_model.predict import (
    UnknownFeedstockError,
    INTERVAL_WIDENING_EXTRAPOLATION,
    DEFAULT_BUSWELL_CH4_BOUND,
)
from app.ml.tests._predict_compat import (
    estimate,
    estimate_illustrative_l1,
    TEST_CH4_FRACTION as DEFAULT_CH4_FRACTION,
)


@pytest.fixture
def synthetic_bundle(tmp_path: Path) -> tuple[ModelBundle, Path]:
    """Creates a tiny synthetic test bundle saved into tmp_path."""
    feedstocks = ["food", "manure", "crop", "mixed"]
    y0_map = {"food": 0.85, "manure": 0.35, "crop": 0.50, "mixed": 0.65}
    kinetic_params = {"y0": y0_map, "mu": 0.4, "k": 0.8}

    # Training feature bounds for 8 features: 4 one-hot, temp (30-40), hrt (15-45), olr (2-5), cn (10-30)
    lo = np.array([0.0, 0.0, 0.0, 0.0, 30.0, 15.0, 2.0, 10.0])
    hi = np.array([1.0, 1.0, 1.0, 1.0, 40.0, 45.0, 5.0, 30.0])
    guard = DomainGuard(bounds=(lo, hi), feedstocks_seen=feedstocks)

    # Simple fitted GBR model predicting a fixed small positive log residual
    X_dummy = np.vstack([lo, hi, (lo + hi) / 2])
    y_log_res = np.array([0.05, 0.10, 0.08])
    gbr = GradientBoostingRegressor(n_estimators=10, random_state=42)
    gbr.fit(X_dummy, y_log_res)

    bundle = ModelBundle(
        model_version="test-v0.2",
        feedstocks_seen=feedstocks,
        kinetic_params=kinetic_params,
        residual_model=gbr,
        domain_guard=guard,
        metrics={"cv_residual_std_log": 0.12},
        training_data_hash="dummy_hash_12345",
        synthetic=True,
    )
    save_bundle(bundle, target_dir=tmp_path)
    return bundle, tmp_path


def test_no_bundle_raises_no_trained_model_error(tmp_path: Path):
    """Calling estimate with an empty directory raises NoTrainedModelError."""
    empty_dir = tmp_path / "empty_models"
    empty_dir.mkdir()
    with pytest.raises(NoTrainedModelError):
        estimate("food", {"hrt_days": 30.0, "temperature_c": 37.0}, model_dir=empty_dir)


def test_in_domain_request(synthetic_bundle):
    """In-domain request returns hybrid estimate, extrapolation_flag=False, and low <= y <= high."""
    bundle, model_dir = synthetic_bundle
    operating = {
        "hrt_days": 30.0,
        "temperature_c": 37.0,
        "olr": 3.5,
        "c_n": 20.0
    }
    result = estimate("food", operating, bundle=bundle)

    assert result.extrapolation_flag is False
    assert result.basis == "per kg VS"
    # Hybrid value incorporates ML residual (> L1 kinetic in this fixture)
    assert result.y_biogas_nm3_per_kg_vs >= result.y_kinetic_nm3_per_kg_vs
    assert result.interval_low <= result.y_biogas_nm3_per_kg_vs <= result.interval_high
    assert "SYNTHETIC" in result.model_version


def test_out_of_domain_request_falls_back_to_l1(synthetic_bundle):
    """Out-of-domain request returns L1 value, extrapolation_flag=True, and wider interval."""
    bundle, _ = synthetic_bundle

    # In-domain baseline
    in_domain_op = {"hrt_days": 30.0, "temperature_c": 37.0, "olr": 3.5, "c_n": 20.0}
    res_in = estimate("food", in_domain_op, bundle=bundle)

    # OLR = 7.0 is outside [2.0, 5.0] training bounds
    out_domain_op = {"hrt_days": 30.0, "temperature_c": 37.0, "olr": 7.0, "c_n": 20.0}
    res_out = estimate("food", out_domain_op, bundle=bundle)

    assert res_out.extrapolation_flag is True
    # Strictly returns kinetic L1 value
    assert math.isclose(res_out.y_biogas_nm3_per_kg_vs, res_out.y_kinetic_nm3_per_kg_vs, rel_tol=1e-7)

    # Interval width comparison
    # In-domain width ratio: high / low = exp(2 * 1.96 * sigma)
    # Out-of-domain width ratio: high / low = exp(2 * 1.96 * sigma * INTERVAL_WIDENING_EXTRAPOLATION)
    ratio_in = res_in.interval_high / res_in.interval_low
    ratio_out = res_out.interval_high / res_out.interval_low
    assert ratio_out > ratio_in


def test_temperature_plausibility_extrapolation(synthetic_bundle):
    """Temperatures outside 10-80 C (e.g. 5 C or 85 C) trigger extrapolation flag, not ValueError."""
    bundle, _ = synthetic_bundle

    res_cold = estimate("food", {"hrt_days": 30.0, "temperature_c": 5.0, "olr": 3.0, "c_n": 20.0}, bundle=bundle)
    assert res_cold.extrapolation_flag is True

    res_hot = estimate("food", {"hrt_days": 30.0, "temperature_c": 85.0, "olr": 3.0, "c_n": 20.0}, bundle=bundle)
    assert res_hot.extrapolation_flag is True


def test_missing_optional_features_falls_back_to_l1(synthetic_bundle):
    """If olr or c_n are missing/None, prediction falls back to L1 with extrapolation_flag=True."""
    bundle, _ = synthetic_bundle
    res = estimate("food", {"hrt_days": 30.0, "temperature_c": 37.0}, bundle=bundle)
    assert res.extrapolation_flag is True
    assert math.isclose(res.y_biogas_nm3_per_kg_vs, res.y_kinetic_nm3_per_kg_vs, rel_tol=1e-7)


def test_unseen_feedstock_raises_unknown_feedstock_error(synthetic_bundle):
    """Unseen feedstock raises UnknownFeedstockError listing known feedstocks."""
    bundle, _ = synthetic_bundle
    with pytest.raises(UnknownFeedstockError) as ctx:
        estimate("electronic_waste", {"hrt_days": 30.0, "temperature_c": 37.0}, bundle=bundle)

    err = str(ctx.value)
    assert "electronic_waste" in err
    assert "food" in err


def test_buswell_ceiling_clamping(synthetic_bundle):
    """Values exceeding theoretical Buswell bound get clamped."""
    bundle, _ = synthetic_bundle
    ceiling_biogas = DEFAULT_BUSWELL_CH4_BOUND / DEFAULT_CH4_FRACTION  # ~0.91833

    # Force a scenario with artificially low ceiling to test clamping
    low_ch4_ceiling = 0.20
    expected_ceiling = 0.20 / DEFAULT_CH4_FRACTION

    res = estimate(
        "food",
        {"hrt_days": 30.0, "temperature_c": 37.0, "olr": 3.0, "c_n": 20.0},
        bundle=bundle,
        buswell_ch4_bound=low_ch4_ceiling
    )

    assert res.y_biogas_nm3_per_kg_vs <= expected_ceiling + 1e-9
    assert res.y_kinetic_nm3_per_kg_vs <= expected_ceiling + 1e-9
    assert res.interval_high <= expected_ceiling + 1e-9


def test_invalid_physical_inputs_raise_value_error(synthetic_bundle):
    """Hard physical impossibilities raise ValueError."""
    bundle, _ = synthetic_bundle

    # Non-positive HRT
    with pytest.raises(ValueError):
        estimate("food", {"hrt_days": 0.0, "temperature_c": 37.0}, bundle=bundle)

    with pytest.raises(ValueError):
        estimate("food", {"hrt_days": -10.0, "temperature_c": 37.0}, bundle=bundle)

    # Temperature outside 0-100 C
    with pytest.raises(ValueError):
        estimate("food", {"hrt_days": 30.0, "temperature_c": -5.0}, bundle=bundle)

    with pytest.raises(ValueError):
        estimate("food", {"hrt_days": 30.0, "temperature_c": 105.0}, bundle=bundle)

    # Non-positive OLR or C:N
    with pytest.raises(ValueError):
        estimate("food", {"hrt_days": 30.0, "temperature_c": 37.0, "olr": -1.0}, bundle=bundle)

    with pytest.raises(ValueError):
        estimate("food", {"hrt_days": 30.0, "temperature_c": 37.0, "c_n": 0.0}, bundle=bundle)


def test_illustrative_mode_only_runs_when_called_explicitly():
    """estimate_illustrative_l1 only runs when called directly and returns correct metadata."""
    res = estimate_illustrative_l1("food", {"hrt_days": 30.0, "temperature_c": 37.0})
    assert res.model_version == "illustrative-l1-NOT-VALIDATED"
    assert res.extrapolation_flag is False
    assert res.basis == "per kg VS"
    assert res.y_biogas_nm3_per_kg_vs == res.y_kinetic_nm3_per_kg_vs

    with pytest.raises(UnknownFeedstockError):
        estimate_illustrative_l1("unknown_material", {"hrt_days": 30.0, "temperature_c": 37.0})


def test_synthetic_bundle_marks_model_version(synthetic_bundle):
    """Bundle with synthetic=True has 'SYNTHETIC' in model_version; synthetic=False does not."""
    bundle_synth, _ = synthetic_bundle
    op = {"hrt_days": 30.0, "temperature_c": 37.0, "olr": 3.0, "c_n": 20.0}
    res_synth = estimate("food", op, bundle=bundle_synth)
    assert "SYNTHETIC" in res_synth.model_version

    # Bundle with synthetic=False
    bundle_real = ModelBundle(
        model_version="plant-real-v1.0",
        feedstocks_seen=bundle_synth.feedstocks_seen,
        kinetic_params=bundle_synth.kinetic_params,
        residual_model=bundle_synth.residual_model,
        domain_guard=bundle_synth.domain_guard,
        metrics=bundle_synth.metrics,
        training_data_hash="real_data_hash",
        synthetic=False,
    )
    res_real = estimate("food", op, bundle=bundle_real)
    assert "SYNTHETIC" not in res_real.model_version
    assert res_real.model_version == "plant-real-v1.0"


def test_bundle_without_cv_residual_std_log_raises(synthetic_bundle):
    """Bundle without cv_residual_std_log raises clear ValueError without defaulting to made-up sigma."""
    bundle, _ = synthetic_bundle
    bundle_no_sigma = ModelBundle(
        model_version="no-sigma-v0.1",
        feedstocks_seen=bundle.feedstocks_seen,
        kinetic_params=bundle.kinetic_params,
        residual_model=bundle.residual_model,
        domain_guard=bundle.domain_guard,
        metrics={"mae": 0.05},  # Missing cv_residual_std_log
        training_data_hash="hash_123",
        synthetic=True,
    )
    op = {"hrt_days": 30.0, "temperature_c": 37.0, "olr": 3.0, "c_n": 20.0}
    with pytest.raises(ValueError) as ctx:
        estimate("food", op, bundle=bundle_no_sigma)
    assert "cv_residual_std_log" in str(ctx.value)


def test_save_load_bundle_round_trip(tmp_path: Path, synthetic_bundle):
    """save_bundle and load_bundle round trip preserves all bundle fields."""
    from app.ml.registry.store import load_bundle
    bundle, _ = synthetic_bundle

    save_dir = tmp_path / "round_trip_test"
    saved_path = save_bundle(bundle, target_dir=save_dir)
    assert saved_path.exists()

    loaded = load_bundle(model_dir=save_dir)
    assert loaded.model_version == bundle.model_version
    assert loaded.synthetic == bundle.synthetic
    assert loaded.feedstocks_seen == bundle.feedstocks_seen
    assert loaded.metrics == bundle.metrics
    assert loaded.training_data_hash == bundle.training_data_hash


def test_interval_bounds_in_and_out_of_domain(synthetic_bundle):
    """Verifies interval_high <= ceiling and interval_low >= 0 for both in-domain and out-of-domain."""
    bundle, _ = synthetic_bundle
    ceiling_biogas = DEFAULT_BUSWELL_CH4_BOUND / DEFAULT_CH4_FRACTION

    # In-domain
    in_res = estimate("food", {"hrt_days": 30.0, "temperature_c": 37.0, "olr": 3.0, "c_n": 20.0}, bundle=bundle)
    assert in_res.interval_low >= 0.0
    assert in_res.interval_high <= ceiling_biogas + 1e-9
    assert in_res.interval_low <= in_res.y_biogas_nm3_per_kg_vs <= in_res.interval_high

    # Out-of-domain (OLR=10.0 outside bounds)
    out_res = estimate("food", {"hrt_days": 30.0, "temperature_c": 37.0, "olr": 10.0, "c_n": 20.0}, bundle=bundle)
    assert out_res.interval_low >= 0.0
    assert out_res.interval_high <= ceiling_biogas + 1e-9
    assert out_res.interval_low <= out_res.y_biogas_nm3_per_kg_vs <= out_res.interval_high


def test_widened_interval_is_wider_for_same_request(synthetic_bundle):
    """Widened interval under extrapolation is strictly wider than in-domain interval for identical request."""
    bundle, _ = synthetic_bundle
    # Standard request
    op = {"hrt_days": 30.0, "temperature_c": 37.0, "olr": 3.5, "c_n": 20.0}

    # Evaluate with standard in-domain guard
    res_in = estimate("food", op, bundle=bundle)
    assert res_in.extrapolation_flag is False
    width_in = res_in.interval_high - res_in.interval_low

    # Create bundle where bounds are artificially narrow (temp bounds 38-40 C), so 37.0 C is flagged
    lo_narrow = np.array([0.0, 0.0, 0.0, 0.0, 38.0, 15.0, 2.0, 10.0])
    hi_narrow = np.array([1.0, 1.0, 1.0, 1.0, 40.0, 45.0, 5.0, 30.0])
    guard_narrow = DomainGuard(bounds=(lo_narrow, hi_narrow), feedstocks_seen=bundle.feedstocks_seen)

    bundle_narrow = ModelBundle(
        model_version=bundle.model_version,
        feedstocks_seen=bundle.feedstocks_seen,
        kinetic_params=bundle.kinetic_params,
        residual_model=bundle.residual_model,
        domain_guard=guard_narrow,
        metrics=bundle.metrics,
        training_data_hash=bundle.training_data_hash,
        synthetic=bundle.synthetic,
    )

    res_out = estimate("food", op, bundle=bundle_narrow)
    assert res_out.extrapolation_flag is True
    width_out = res_out.interval_high - res_out.interval_low

    assert width_out > width_in


# ---------------------------------------------------------------------------
# Additional tests for edge‑case feedstock handling as requested
# ---------------------------------------------------------------------------

import pytest
from app.ml.yield_model.predict import (
    MissingFeedstockError,
    UnknownFeedstockError,
    NoTrainedModelError,
)
from app.ml.tests._predict_compat import estimate, estimate_illustrative_l1
from app.ml.yield_model.domain_guard import DomainGuard
from app.ml.registry.store import ModelBundle, save_bundle
from pathlib import Path
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor

@pytest.fixture
def bundle_without_manure(tmp_path: Path) -> ModelBundle:
    """Create a bundle that lacks 'manure' in its feedstocks_seen list."""
    feedstocks = ["food", "crop", "mixed"]
    y0_map = {"food": 0.85, "crop": 0.50, "mixed": 0.65}
    kinetic_params = {"y0": y0_map, "mu": 0.4, "k": 0.8}
    lo = np.array([0.0, 0.0, 0.0, 0.0, 30.0, 15.0, 2.0, 10.0])
    hi = np.array([1.0, 1.0, 1.0, 1.0, 40.0, 45.0, 5.0, 30.0])
    guard = DomainGuard(bounds=(lo, hi), feedstocks_seen=feedstocks)
    X_dummy = np.vstack([lo, hi, (lo + hi) / 2])
    y_log_res = np.array([0.05, 0.10, 0.08])
    gbr = GradientBoostingRegressor(n_estimators=10, random_state=42)
    gbr.fit(X_dummy, y_log_res)
    bundle = ModelBundle(
        model_version="test-no-manure",
        feedstocks_seen=feedstocks,
        kinetic_params=kinetic_params,
        residual_model=gbr,
        domain_guard=guard,
        metrics={"cv_residual_std_log": 0.12},
        training_data_hash="hash_no_manure",
        synthetic=True,
    )
    # Save to a temporary directory to emulate a real bundle on disk (optional)
    save_bundle(bundle, target_dir=tmp_path)
    return bundle

def test_missing_feedstock_raises_missing_error(synthetic_bundle):
    """None, empty string and whitespace feedstock should raise MissingFeedstockError (also a ValueError)."""
    bundle, _ = synthetic_bundle
    for bad in [None, "", "   "]:
        with pytest.raises(MissingFeedstockError) as ctx:
            estimate(bad, {"hrt_days": 30.0, "temperature_c": 37.0}, bundle=bundle)
        # The custom error should also be a ValueError subclass
        assert isinstance(ctx.value, ValueError)

def test_normalised_feedstock_works(synthetic_bundle):
    """Feedstock strings with different capitalisation / surrounding whitespace are accepted."""
    bundle, _ = synthetic_bundle
    result = estimate("Food", {"hrt_days": 30.0, "temperature_c": 37.0, "olr": 3.5, "c_n": 20.0}, bundle=bundle)
    assert isinstance(result, YieldEstimate)
    result2 = estimate(" food ", {"hrt_days": 30.0, "temperature_c": 37.0, "olr": 3.5, "c_n": 20.0}, bundle=bundle)
    assert isinstance(result2, YieldEstimate)
    # The two results should be identical (normalisation is deterministic)
    assert result == result2

def test_unknown_feedstock_error_message_includes_all_names():
    """Calling estimate with an unsupported feedstock should raise UnknownFeedstockError and list every known name."""
    from app.ml.yield_model.feedstocks import FEEDSTOCK_NAMES
    # Use a temporary empty bundle directory – the function validates feedstock before loading the bundle
    with pytest.raises(UnknownFeedstockError) as ctx:
        estimate("plastic", {"hrt_days": 30.0, "temperature_c": 37.0})
    err_msg = str(ctx.value)
    for name in FEEDSTOCK_NAMES:
        assert name in err_msg

def test_unseen_feedstock_raises_unknown_and_mentions_valid(bundle_without_manure, tmp_path):
    """When the feedstock is valid but not present in the model bundle, raise UnknownFeedstockError with a helpful message."""
    with pytest.raises(UnknownFeedstockError) as ctx:
        estimate("manure", {"hrt_days": 30.0, "temperature_c": 37.0}, bundle=bundle_without_manure)
    msg = str(ctx.value).lower()
    assert "valid" in msg
    for fs in bundle_without_manure.feedstocks_seen:
        assert fs in msg

def test_missing_feedstock_without_bundle_raises_missing_not_no_model(tmp_path):
    """An empty feedstock string with an empty model directory should raise MissingFeedstockError, not NoTrainedModelError."""
    empty_dir = tmp_path / "empty_models"
    empty_dir.mkdir()
    with pytest.raises(MissingFeedstockError):
        estimate("", {"hrt_days": 30.0, "temperature_c": 37.0}, model_dir=empty_dir)

def test_illustrative_l1_missing_and_unknown_feedstock_errors():
    """estimate_illustrative_l1 should raise MissingFeedstockError for blank input and UnknownFeedstockError for unknown names."""
    with pytest.raises(MissingFeedstockError):
        estimate_illustrative_l1("", {"hrt_days": 30.0, "temperature_c": 37.0})
    with pytest.raises(UnknownFeedstockError):
        estimate_illustrative_l1("plastic", {"hrt_days": 30.0, "temperature_c": 37.0})
