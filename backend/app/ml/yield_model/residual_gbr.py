"""Gradient Boosting Regressor for L2 residual yield learning.

Trains on the multiplicative log-residual between observed yields and L1 kinetic physics:
    residual = log(Y_obs / Y_kinetic)

Yield prediction:
    Y = Y_kinetic * exp(ML(features))
subject to the Buswell theoretical ceiling and training domain guardrails.
"""

from typing import Optional, Union, Literal
import numpy as np
from sklearn.ensemble import GradientBoostingRegressor

from app.ml.yield_model.domain_guard import DomainGuard


class ResidualGBR:
    """Gradient Boosting Regressor predicting log-residuals on top of kinetic physics."""

    def __init__(
        self,
        n_estimators: int = 300,
        max_depth: int = 3,
        learning_rate: float = 0.05,
        subsample: float = 0.8,
        random_state: int = 0
    ):
        """Initializes GradientBoostingRegressor with verified hyperparameters from blueprint."""
        self.model = GradientBoostingRegressor(
            n_estimators=n_estimators,
            max_depth=max_depth,
            learning_rate=learning_rate,
            subsample=subsample,
            random_state=random_state
        )
        self.guard: Optional[DomainGuard] = None

    def fit(
        self,
        X: np.ndarray,
        y_obs: np.ndarray,
        y_kinetic: np.ndarray
    ) -> "ResidualGBR":
        """Fits the GBR on log(y_obs / y_kinetic) and records training domain bounds.

        Args:
            X: 2D feature matrix (feedstock one-hot + operating conditions).
            y_obs: 1D array of observed biogas yields (Nm3 biogas / kg VS).
            y_kinetic: 1D array of L1 kinetic baseline yields (Nm3 biogas / kg VS).

        Returns:
            self
        """
        X = np.asarray(X, dtype=float)
        y_obs = np.asarray(y_obs, dtype=float)
        y_kinetic = np.asarray(y_kinetic, dtype=float)

        log_residual = np.log(y_obs / y_kinetic)
        self.model.fit(X, log_residual)
        self.guard = DomainGuard(X)
        return self

    def predict_residual(self, X: np.ndarray) -> np.ndarray:
        """Predicts the multiplicative factor exp(residual).

        Args:
            X: 2D feature matrix.

        Returns:
            1D array of multiplicative correction factors.
        """
        X = np.asarray(X, dtype=float)
        return np.exp(self.model.predict(X))

    def predict_hybrid(
        self,
        X: np.ndarray,
        y_kinetic: np.ndarray,
        buswell_ch4_bound: Optional[float] = 0.551,
        ch4_fraction: float = 0.60,
        yield_type: Literal["biogas", "ch4"] = "biogas",
        guarded: bool = True
    ) -> tuple[np.ndarray, np.ndarray]:
        """Generates hybrid predictions, applying Buswell theoretical ceiling and domain fallback.

        Theoretical Ceiling Application:
            The Buswell bound `buswell_ch4_bound` represents the theoretical maximum stoichiometric
            methane yield in Nm3 CH4 / kg VS (e.g. 0.551 Nm3 CH4 / kg VS for 60/20/20 carb/protein/lipid).

            - If yield_type == 'biogas':
                The model outputs biogas yield (Nm3 biogas / kg VS).
                The physical ceiling must be converted from CH4 to biogas:
                    ceiling_biogas = buswell_ch4_bound / ch4_fraction
                (Default: 0.551 / 0.60 = 0.918333 Nm3 biogas / kg VS).
                The prediction is clamped so that predicted_biogas <= ceiling_biogas.

            - If yield_type == 'ch4':
                The model outputs CH4 yield directly (Nm3 CH4 / kg VS).
                The physical ceiling is applied directly:
                    ceiling_ch4 = buswell_ch4_bound
                The prediction is clamped so that predicted_ch4 <= ceiling_ch4.

        Args:
            X: 2D feature matrix.
            y_kinetic: L1 kinetic baseline yield (Nm3 biogas or CH4 / kg VS).
            buswell_ch4_bound: Maximum theoretical CH4 potential (Nm3 CH4 / kg VS). Default is 0.551.
                               Pass None to disable clamping.
            ch4_fraction: Volumetric CH4 fraction in biogas (0 < ch4_fraction <= 1.0). Default is 0.60.
            yield_type: 'biogas' or 'ch4'. Determines whether bound is divided by ch4_fraction.
            guarded: If True, any out-of-domain sample falls back strictly to y_kinetic.

        Returns:
            Tuple of (predictions, extrapolation_flags).
        """
        X = np.asarray(X, dtype=float)
        y_kinetic = np.asarray(y_kinetic, dtype=float)

        mult = self.predict_residual(X)
        hyb = y_kinetic * mult

        if buswell_ch4_bound is not None:
            if not (0.0 < ch4_fraction <= 1.0):
                raise ValueError(f"ch4_fraction must be in (0, 1.0], got {ch4_fraction}")
            yt = yield_type.lower().strip()
            if yt == "biogas":
                ceiling = buswell_ch4_bound / ch4_fraction
            elif yt == "ch4":
                ceiling = buswell_ch4_bound
            else:
                raise ValueError(f"yield_type must be 'biogas' or 'ch4', got '{yield_type}'")
            hyb = np.minimum(hyb, ceiling)

        if self.guard is not None:
            flags = self.guard.outside(X)
        else:
            flags = np.zeros(len(hyb), dtype=bool)

        if guarded:
            final_pred = np.where(flags, y_kinetic, hyb)
        else:
            final_pred = hyb

        return final_pred, flags
