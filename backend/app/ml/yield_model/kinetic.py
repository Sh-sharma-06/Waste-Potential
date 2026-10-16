"""Chen-Hashimoto kinetic physics model for anaerobic digestion yield.

Implements the L1 physics level:
    Y = Y0 * (1 - K / (HRT * mu - 1 + K))
where Y0 is the maximum yield per feedstock (Nm3 biogas / kg VS),
mu is the maximum specific growth rate (1/day), and K is the kinetic parameter.

Parameters are fitted via non-linear least squares in log-space on training rows only.
"""

from typing import Sequence, Tuple, Union
import numpy as np
from scipy.optimize import least_squares


def kinetic(
    params: Sequence[float],
    fs_idx: Union[int, np.ndarray],
    hrt: Union[float, np.ndarray]
) -> np.ndarray:
    """Computes predicted biogas yield using Chen-Hashimoto kinetics.

    Equation:
        Y = Y0[fs] * (1 - K / (HRT * mu - 1 + K))

    Args:
        params: Array-like containing [Y0_0, Y0_1, ..., Y0_{n-1}, mu, K].
                The first n elements are feedstock-specific theoretical potentials Y0
                (Nm3 biogas / kg VS), followed by mu (1/day) and dimensionless K.
        fs_idx: Feedstock integer index or 1D array of indices (0 to n-1).
        hrt: Hydraulic Retention Time in days (scalar or 1D array).

    Returns:
        Predicted biogas yield in Nm3 biogas per kg VS (numpy array or float).
    """
    params = np.asarray(params, dtype=float)
    n_fs = len(params) - 2
    y0_all = params[:n_fs]
    mu = params[n_fs]
    k = params[n_fs + 1]

    hrt = np.asarray(hrt, dtype=float)
    denom = hrt * mu - 1.0 + k
    # Guard against division by zero or non-physical denominator
    denom = np.where(np.abs(denom) < 1e-9, 1e-9, denom)
    factor = 1.0 - (k / denom)
    
    y0 = y0_all[fs_idx]
    return y0 * factor


def fit_kinetic(
    fs_idx: np.ndarray,
    hrt: np.ndarray,
    y: np.ndarray,
    n_fs: int = 4
) -> np.ndarray:
    """Calibrates Chen-Hashimoto kinetic parameters on training observations in log space.

    Minimizes:
        residual = log(clip(Y_pred, 1e-6)) - log(Y_obs)

    Args:
        fs_idx: 1D array of feedstock integer indices for training observations.
        hrt: 1D array of HRT values in days for training observations.
        y: 1D array of measured biogas yields (Nm3 biogas per kg VS).
        n_fs: Number of distinct feedstock categories. Default is 4.

    Returns:
        Fitted parameter vector: [Y0_0, ..., Y0_{n_fs-1}, mu, K].
    """
    fs_idx = np.asarray(fs_idx, dtype=int)
    hrt = np.asarray(hrt, dtype=float)
    y = np.asarray(y, dtype=float)

    def residual(p: np.ndarray) -> np.ndarray:
        pred = kinetic(p, fs_idx, hrt)
        return np.log(np.clip(pred, 1e-6, None)) - np.log(y)

    # Initial guess and bounds from verified blueprint Appendix D
    p0 = [0.6] * n_fs + [0.4, 0.8]
    lower_bounds = [0.05] * n_fs + [0.05, 0.05]
    upper_bounds = [1.2] * n_fs + [2.0, 5.0]

    result = least_squares(
        residual,
        p0,
        bounds=(lower_bounds, upper_bounds)
    )
    return result.x
