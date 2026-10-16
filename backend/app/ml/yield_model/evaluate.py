"""Evaluation metrics and data partition integrity utilities for yield models.

Implements standard benchmark error metrics:
    - MAE: Mean Absolute Error (Nm3 biogas / kg VS)
    - RMSE: Root Mean Squared Error (Nm3 biogas / kg VS)
    - Bias: Mean error (Predicted - Actual) (Nm3 biogas / kg VS)
    - MAPE: Mean Absolute Percentage Error (%)

Also provides leak-detection assertions for grouped cross-validation.
"""

from typing import Dict, Sequence, Union
import numpy as np


def mae(actual: np.ndarray, predicted: np.ndarray) -> float:
    """Mean Absolute Error: mean(|predicted - actual|)."""
    return float(np.mean(np.abs(np.asarray(predicted) - np.asarray(actual))))


def rmse(actual: np.ndarray, predicted: np.ndarray) -> float:
    """Root Mean Squared Error: sqrt(mean((predicted - actual)^2))."""
    return float(np.sqrt(np.mean((np.asarray(predicted) - np.asarray(actual)) ** 2)))


def bias(actual: np.ndarray, predicted: np.ndarray) -> float:
    """Mean prediction bias: mean(predicted - actual)."""
    return float(np.mean(np.asarray(predicted) - np.asarray(actual)))


def mape(actual: np.ndarray, predicted: np.ndarray) -> float:
    """Mean Absolute Percentage Error (%): 100 * mean(|predicted - actual| / actual)."""
    act = np.asarray(actual, dtype=float)
    pred = np.asarray(predicted, dtype=float)
    # Guard against zero division
    denom = np.where(act == 0, 1e-9, act)
    return float(100.0 * np.mean(np.abs(pred - act) / denom))


def calculate_metrics(
    actual: Union[np.ndarray, list],
    predicted: Union[np.ndarray, list]
) -> Dict[str, float]:
    """Calculates all 4 standard evaluation metrics.

    Args:
        actual: 1D array of ground truth measured yields.
        predicted: 1D array of predicted yields.

    Returns:
        Dictionary with keys 'MAE', 'RMSE', 'bias', 'MAPE'.
    """
    a = np.asarray(actual, dtype=float)
    p = np.asarray(predicted, dtype=float)
    e = p - a
    return {
        "MAE": float(np.mean(np.abs(e))),
        "RMSE": float(np.sqrt(np.mean(e ** 2))),
        "bias": float(np.mean(e)),
        "MAPE": float(100.0 * np.mean(np.abs(e) / a)),
    }


def assert_no_leakage(train_groups: Sequence, test_groups: Sequence) -> None:
    """Verifies that no group (e.g. study_id or plant_id) appears in both train and test partitions.

    Args:
        train_groups: Sequence of group identifiers for training samples.
        test_groups: Sequence of group identifiers for test samples.

    Raises:
        ValueError: If any group identifier appears in both train_groups and test_groups,
                    explicitly naming the overlapping study_ids.
    """
    train_set = set(train_groups)
    test_set = set(test_groups)
    overlap = train_set.intersection(test_set)
    if overlap:
        sorted_overlap = sorted(list(overlap), key=lambda x: str(x))
        raise ValueError(
            f"Study/group leakage detected between train and test splits! "
            f"Overlapping study_ids: {sorted_overlap}"
        )
