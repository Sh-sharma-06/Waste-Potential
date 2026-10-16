"""Domain guard for hybrid yield model.

Stores training domain bounds (min and max for each feature) and flags inputs
falling outside the validated training domain as extrapolations.
"""

from typing import Optional, Sequence, Tuple, Union
import numpy as np


class DomainGuard:
    """Monitors input features against empirical training domain bounds.

    Whenever an input feature falls outside the minimum or maximum observed
    during model training, the domain guard flags the observation as an extrapolation,
    signaling the orchestrator to fall back to the L1 kinetic physics baseline.
    """

    def __init__(
        self,
        X: Optional[np.ndarray] = None,
        bounds: Optional[Tuple[Sequence[float], Sequence[float]]] = None,
        feedstocks_seen: Optional[Sequence[str]] = None
    ):
        """Initializes DomainGuard from a training feature matrix or explicit bounds.

        Args:
            X: Optional 1D or 2D array of training features. If 1D, treated as (n_samples, 1).
            bounds: Optional tuple of (lower_bounds, upper_bounds).
            feedstocks_seen: Optional list of validated feedstock names.
        """
        self.feedstocks_seen = list(feedstocks_seen) if feedstocks_seen is not None else []
        if X is not None:
            arr = np.asarray(X, dtype=float)
            if arr.ndim == 1:
                arr = arr.reshape(-1, 1)
            self.lo = arr.min(axis=0)
            self.hi = arr.max(axis=0)
        elif bounds is not None:
            self.lo = np.asarray(bounds[0], dtype=float)
            self.hi = np.asarray(bounds[1], dtype=float)
        else:
            self.lo = np.array([], dtype=float)
            self.hi = np.array([], dtype=float)

    def outside(self, X: np.ndarray) -> np.ndarray:
        """Determines if any feature in each input observation falls outside training bounds.

        Args:
            X: 1D or 2D array of feature vectors to check.
               If 1D and len == len(self.lo): treated as 1 sample with n features.
               If 1D and len(self.lo) == 1: treated as n samples of 1 feature.

        Returns:
            Boolean array of shape (n_samples,) where True indicates out-of-domain extrapolation.
        """
        arr = np.asarray(X, dtype=float)
        if len(self.lo) == 0 or len(self.hi) == 0:
            return np.zeros(len(arr), dtype=bool)

        if arr.ndim == 1:
            if len(self.lo) == 1:
                arr = arr.reshape(-1, 1)
                return ((arr < self.lo) | (arr > self.hi)).any(axis=1)
            else:
                # Single sample with multiple features
                arr = arr.reshape(1, -1)
                return ((arr < self.lo) | (arr > self.hi)).any(axis=1)[0]
        else:
            return ((arr < self.lo) | (arr > self.hi)).any(axis=1)

    def is_extrapolation(self, x: Sequence[float]) -> bool:
        """Check a single feature vector for extrapolation.

        Args:
            x: 1D sequence of feature values.

        Returns:
            True if any feature in x is outside [lo, hi], False otherwise.
        """
        arr = np.asarray(x, dtype=float).reshape(1, -1)
        return bool(((arr < self.lo) | (arr > self.hi)).any())
