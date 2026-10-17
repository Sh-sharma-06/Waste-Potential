"""Yield prediction service and inference entry point.

Provides the orchestrator-facing `estimate(feedstock, operating)` function.
Returns a validated `YieldEstimate` (from `schemas/ml.py`) adhering to all
scientific mass-balance, Buswell ceiling, domain guard, and uncertainty rules.
"""

import math
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union
import numpy as np

from app.schemas.ml import YieldEstimate
from app.ml.registry.store import ModelBundle, NoTrainedModelError, load_bundle

# Placeholder widening factor to be calibrated on empirical plant extrapolation tests
INTERVAL_WIDENING_EXTRAPOLATION: float = 2.5

# Default stoichiometric Buswell theoretical limits
DEFAULT_BUSWELL_CH4_BOUND: float = 0.551  # Nm3 CH4 / kg VS
DEFAULT_CH4_FRACTION: float = 0.60        # Volumetric fraction

# Fixed illustrative parameters (for explicit illustrative mode only; never automatic)
ILLUSTRATIVE_Y0_NM3_PER_KG_VS: Dict[str, float] = {
    "food": 0.85,
    "manure": 0.35,
    "crop": 0.50,
    "mixed": 0.65,
}
ILLUSTRATIVE_MU: float = 0.4
ILLUSTRATIVE_K: float = 0.8
ILLUSTRATIVE_RESIDUAL_STD_LOG: float = 0.15


class UnknownFeedstockError(Exception):
    """Raised when an input feedstock has no fitted kinetic parameters in the model bundle."""
    pass


def _validate_inputs(feedstock: str, operating: Dict[str, Any]) -> Tuple[float, float, Optional[float], Optional[float]]:
    """Validates input values for physical impossibility.

    Raises:
        ValueError: For physical impossibilities (hrt_days <= 0, olr <= 0, c_n <= 0,
                    or temperature_c outside [0, 100] C).
    """
    if not isinstance(feedstock, str) or not feedstock.strip():
        raise ValueError("feedstock must be a non-empty string")

    hrt = operating.get("hrt_days")
    if hrt is None or float(hrt) <= 0:
        raise ValueError(f"hrt_days must be positive, got {hrt}")
    hrt_val = float(hrt)

    temp = operating.get("temperature_c")
    if temp is None:
        raise ValueError("temperature_c is required")
    temp_val = float(temp)
    if not (0.0 <= temp_val <= 100.0):
        raise ValueError(f"temperature_c must be physically possible between 0 and 100 C, got {temp_val}")

    olr = operating.get("olr")
    olr_val: Optional[float] = None
    if olr is not None:
        olr_val = float(olr)
        if olr_val <= 0:
            raise ValueError(f"olr must be positive, got {olr_val}")

    cn = operating.get("c_n")
    cn_val: Optional[float] = None
    if cn is not None:
        cn_val = float(cn)
        if cn_val <= 0:
            raise ValueError(f"c_n must be positive, got {cn_val}")

    return hrt_val, temp_val, olr_val, cn_val


def estimate(
    feedstock: str,
    operating: Dict[str, Any],
    bundle: Optional[ModelBundle] = None,
    model_dir: Optional[Union[str, Path]] = None,
    buswell_ch4_bound: float = DEFAULT_BUSWELL_CH4_BOUND,
    ch4_fraction: float = DEFAULT_CH4_FRACTION
) -> YieldEstimate:
    """Computes hybrid yield prediction for a given feedstock and operating conditions.

    Physics & Safeguard Architecture:
      1. Bundle Loading: Loads trained model package from MODEL_DIR or raises NoTrainedModelError.
      2. Feedstock Validation: If feedstock is not in bundle.feedstocks_seen, raises UnknownFeedstockError.
      3. Physical Validation: Invalid inputs (negative HRT/OLR/C:N or temperature outside 0-100 C) raise ValueError.
      4. Kinetic L1 Physics: Computes Chen-Hashimoto kinetic baseline yield Y_kinetic.
      5. Domain Guard: If operating features are outside training bounds or required features (olr, c_n)
         are missing, sets extrapolation_flag=True and strictly uses the L1 kinetic value (never ML).
      6. Buswell Ceiling: Theoretical limit = buswell_ch4_bound / ch4_fraction (default 0.551 / 0.60).
         Applied to both hybrid and L1 fallback values.
      7. Uncertainty Interval: Calculated as an approximate spread based on cv_residual_std_log stored in
         the bundle. Widened by INTERVAL_WIDENING_EXTRAPOLATION (2.5x) if extrapolation_flag is True.
         Note: This interval is an empirical spread estimate, NOT a 95% statistical guarantee.

    Args:
        feedstock: Feedstock name (e.g. 'food', 'manure', 'crop', 'mixed').
        operating: Dictionary containing 'hrt_days', 'temperature_c', and optionally 'olr', 'c_n'.
        bundle: Optional pre-loaded ModelBundle instance. If None, loads from model_dir.
        model_dir: Optional path to model storage directory.
        buswell_ch4_bound: Maximum theoretical methane yield (Nm3 CH4 / kg VS).
        ch4_fraction: Volumetric fraction of CH4 in biogas.

    Returns:
        YieldEstimate (Pydantic model) with all yields in Nm3 biogas per kg VS.

    Raises:
        NoTrainedModelError: If no trained bundle is present on disk.
        UnknownFeedstockError: If the feedstock was not present in the trained model.
        ValueError: For physically impossible input values.
    """
    if bundle is None:
        bundle = load_bundle(model_dir=model_dir)

    hrt_val, temp_val, olr_val, cn_val = _validate_inputs(feedstock, operating)

    fs_clean = feedstock.lower().strip()
    if fs_clean not in bundle.feedstocks_seen:
        raise UnknownFeedstockError(
            f"Unknown feedstock '{feedstock}'. Known feedstocks in model: {bundle.feedstocks_seen}"
        )

    # 1. Calculate L1 Kinetic Physics Yield
    kp = bundle.kinetic_params
    y0_map = kp.get("y0", {})
    if fs_clean not in y0_map:
        raise UnknownFeedstockError(
            f"No kinetic potential Y0 available for feedstock '{feedstock}'."
        )
    y0 = y0_map[fs_clean]
    mu = kp.get("mu", 0.4)
    k = kp.get("k", 0.8)

    denom = hrt_val * mu - 1.0 + k
    denom = 1e-9 if abs(denom) < 1e-9 else denom
    y_kinetic_raw = y0 * (1.0 - (k / denom))

    # Calculate Buswell ceiling on biogas basis: bound / ch4_fraction
    if not (0.0 < ch4_fraction <= 1.0):
        raise ValueError(f"ch4_fraction must be in (0, 1.0], got {ch4_fraction}")
    ceiling_biogas = buswell_ch4_bound / ch4_fraction
    y_kinetic = min(float(y_kinetic_raw), ceiling_biogas)

    # 2. Check for extrapolation (Missing features or Out-Of-Domain features)
    extrapolation_flag = False

    # Temperatures between 0-10 C or 80-100 C are outside biological digestion range
    if not (10.0 <= temp_val <= 80.0):
        extrapolation_flag = True

    # If ML model expects OLR or C:N but they are omitted, fall back to L1
    if olr_val is None or cn_val is None:
        extrapolation_flag = True

    # Build feature vector for DomainGuard and ML
    fs_idx = bundle.feedstocks_seen.index(fs_clean)
    oh = np.zeros(len(bundle.feedstocks_seen))
    oh[fs_idx] = 1.0

    features = np.concatenate([
        oh,
        [temp_val, hrt_val, olr_val if olr_val is not None else 0.0, cn_val if cn_val is not None else 0.0]
    ])

    if bundle.domain_guard is not None:
        if bool(bundle.domain_guard.outside(features)):
            extrapolation_flag = True

    # 3. Hybrid vs Fallback Prediction
    if extrapolation_flag:
        # Strictly return L1 kinetic physics; NEVER use ML prediction when extrapolated
        y_biogas = y_kinetic
    else:
        # Compute ML residual
        if hasattr(bundle.residual_model, "predict_residual"):
            mult = float(bundle.residual_model.predict_residual(features.reshape(1, -1))[0])
        elif hasattr(bundle.residual_model, "predict"):
            pred_log_res = float(bundle.residual_model.predict(features.reshape(1, -1))[0])
            mult = math.exp(pred_log_res)
        else:
            mult = 1.0
        y_hybrid_raw = y_kinetic * mult
        y_biogas = min(y_hybrid_raw, ceiling_biogas)

    # 4. Uncertainty Interval Calculation
    cv_std = bundle.metrics.get("cv_residual_std_log")
    if cv_std is None:
        raise ValueError(
            "Model bundle missing required metric 'cv_residual_std_log' for interval estimation."
        )

    # Widen interval if extrapolating to reflect elevated epistemic risk
    spread_factor = cv_std * (INTERVAL_WIDENING_EXTRAPOLATION if extrapolation_flag else 1.0)
    low_bound = max(0.0, y_biogas * math.exp(-1.96 * spread_factor))
    high_bound = min(ceiling_biogas, y_biogas * math.exp(1.96 * spread_factor))

    # 5. Version string handling (SYNTHETIC marker)
    version_str = bundle.model_version
    if bundle.synthetic and "SYNTHETIC" not in version_str:
        version_str = f"{version_str}-SYNTHETIC"

    return YieldEstimate(
        y_biogas_nm3_per_kg_vs=float(y_biogas),
        y_kinetic_nm3_per_kg_vs=float(y_kinetic),
        interval_low=float(low_bound),
        interval_high=float(high_bound),
        extrapolation_flag=bool(extrapolation_flag),
        model_version=version_str,
        basis="per kg VS"
    )


def estimate_illustrative_l1(
    feedstock: str,
    operating: Dict[str, Any],
    buswell_ch4_bound: float = DEFAULT_BUSWELL_CH4_BOUND,
    ch4_fraction: float = DEFAULT_CH4_FRACTION
) -> YieldEstimate:
    """Explicit illustrative L1 physics calculation using fixed reference Y0 values.

    This function MUST only run when explicitly invoked by demo scenarios;
    it is NEVER used as an automatic fallback when bundles are missing.
    """
    hrt_val, temp_val, _, _ = _validate_inputs(feedstock, operating)

    fs_clean = feedstock.lower().strip()
    if fs_clean not in ILLUSTRATIVE_Y0_NM3_PER_KG_VS:
        raise UnknownFeedstockError(
            f"Unknown illustrative feedstock '{feedstock}'. Available: {list(ILLUSTRATIVE_Y0_NM3_PER_KG_VS.keys())}"
        )

    y0 = ILLUSTRATIVE_Y0_NM3_PER_KG_VS[fs_clean]
    denom = hrt_val * ILLUSTRATIVE_MU - 1.0 + ILLUSTRATIVE_K
    denom = 1e-9 if abs(denom) < 1e-9 else denom
    y_raw = y0 * (1.0 - (ILLUSTRATIVE_K / denom))

    ceiling_biogas = buswell_ch4_bound / ch4_fraction
    y_biogas = min(max(0.0, float(y_raw)), ceiling_biogas)

    spread = ILLUSTRATIVE_RESIDUAL_STD_LOG
    low_bound = max(0.0, y_biogas * math.exp(-1.96 * spread))
    high_bound = min(ceiling_biogas, y_biogas * math.exp(1.96 * spread))

    return YieldEstimate(
        y_biogas_nm3_per_kg_vs=y_biogas,
        y_kinetic_nm3_per_kg_vs=y_biogas,
        interval_low=low_bound,
        interval_high=high_bound,
        extrapolation_flag=False,
        model_version="illustrative-l1-NOT-VALIDATED",
        basis="per kg VS"
    )
