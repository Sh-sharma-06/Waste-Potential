"""Model registry store and serialization helpers.

Provides serialization and loading utilities for trained yield model bundles.
A bundle packages:
  - Kinetic parameters (Chen-Hashimoto L1 physics)
  - Residual ML model (GBR / MLP for L2 residual)
  - DomainGuard (training domain bounds)
  - Metadata (model_version, metrics, feedstocks_seen, training_data_hash, synthetic flag)

Security Notice:
  joblib/pickle deserializes executable Python objects. Only load model bundles
  created and trained locally in trusted environments. NEVER load bundles from
  untrusted user uploads.
"""

from dataclasses import dataclass, field
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import joblib

from app.ml.yield_model.domain_guard import DomainGuard


class NoTrainedModelError(Exception):
    """Raised when no trained model bundle exists in the registry."""
    pass


@dataclass
class ModelBundle:
    """Trained yield model artifact package."""
    model_version: str
    feedstocks_seen: List[str]
    kinetic_params: Dict[str, Any]  # e.g. {"y0": {"food": 0.85, ...}, "mu": 0.4, "k": 0.8}
    residual_model: Any  # Trained ResidualGBR or scikit-learn regressor
    domain_guard: DomainGuard
    metrics: Dict[str, float]  # Must include "cv_residual_std_log"
    training_data_hash: str
    synthetic: bool = False
    feature_names: List[str] = field(default_factory=lambda: ["temp", "hrt", "olr", "c_n"])
    metadata: Dict[str, Any] = field(default_factory=dict)


def get_default_model_dir() -> Path:
    """Returns the configured model directory, respecting MODEL_DIR env var."""
    env_dir = os.environ.get("MODEL_DIR")
    if env_dir:
        return Path(env_dir)
    # Default to backend/models relative to the project root
    backend_root = Path(__file__).resolve().parent.parent.parent.parent
    return backend_root / "models"


def save_bundle(
    bundle: ModelBundle,
    target_dir: Optional[Union[str, Path]] = None,
    filename: str = "yield_model_bundle.joblib"
) -> Path:
    """Saves a model bundle to disk.

    Args:
        bundle: ModelBundle instance to save.
        target_dir: Destination directory. Defaults to get_default_model_dir().
        filename: Destination filename.

    Returns:
        Path to the saved bundle file.
    """
    out_dir = Path(target_dir) if target_dir else get_default_model_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / filename
    joblib.dump(bundle, out_path)
    return out_path


def load_bundle(
    model_dir: Optional[Union[str, Path]] = None,
    filename: str = "yield_model_bundle.joblib"
) -> ModelBundle:
    """Loads a trained model bundle from disk.

    Security Notice:
        joblib/pickle executes code on load; only load bundles trained locally;
        never load bundles from untrusted user uploads.

    Args:
        model_dir: Directory where the bundle is stored. Defaults to get_default_model_dir().
        filename: Name of the bundle file.

    Returns:
        Loaded ModelBundle instance.

    Raises:
        NoTrainedModelError: If the bundle file is not found.
    """
    src_dir = Path(model_dir) if model_dir else get_default_model_dir()
    file_path = src_dir / filename

    if not file_path.exists():
        raise NoTrainedModelError(
            f"No trained model bundle found at '{file_path}'. "
            f"A model bundle must be trained and registered before calling estimate(). "
            f"Check MODEL_DIR or train a bundle using yield_model/train.py."
        )

    bundle = joblib.load(file_path)
    if not isinstance(bundle, ModelBundle):
        raise TypeError(f"Loaded object from '{file_path}' is not a ModelBundle, got {type(bundle)}")

    return bundle
