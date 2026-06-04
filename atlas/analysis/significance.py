"""Selection-aware significance for one-sided lead/lag tests.

INVARIANT: the bootstrap null perturbs a SINGLE residual series independently,
never the pair jointly. Joint resampling preserves the lead/lag under test and
yields an invalid null.
"""
from __future__ import annotations

import numpy as np

from config import BOOTSTRAP_BLOCK


def _autocorr(x: np.ndarray, max_lag: int) -> np.ndarray:
    x = x - x.mean()
    var = np.dot(x, x)
    if var == 0:
        return np.zeros(max_lag + 1)
    return np.array([np.dot(x[: len(x) - k], x[k:]) / var for k in range(max_lag + 1)])


def auto_block_length(x: np.ndarray, *, fallback: int = BOOTSTRAP_BLOCK) -> int:
    """Politis-White (2004) optimal stationary-bootstrap expected block length.

    Returns a clamped integer in [1, n // 3]; falls back on degenerate input.
    """
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < 8 or np.std(x) == 0:
        return max(1, min(fallback, max(1, n // 3)))
    max_lag = min(n - 1, int(np.ceil(np.sqrt(n))) + 20)
    rho = _autocorr(x, max_lag)
    # Flat-top: first lag after which K consecutive |rho| are below the bound.
    bound = 2.0 * np.sqrt(np.log10(n) / n)
    K = max(5, int(np.ceil(np.sqrt(np.log10(n)))))
    m = 1
    for k in range(1, max_lag - K + 1):
        if np.all(np.abs(rho[k : k + K]) < bound):
            m = k - 1
            break
    else:
        m = max_lag // 2
    M = max(1, 2 * m)
    lags = np.arange(-M, M + 1)
    rho_sym = np.array([rho[abs(int(k))] for k in lags])
    # Flat-top lag window weights.
    w = np.where(np.abs(lags) <= M / 2, 1.0, 2.0 * (1.0 - np.abs(lags) / M))
    w = np.clip(w, 0.0, 1.0)
    g_hat = float(np.sum(w * np.abs(lags) * rho_sym))
    d_hat = float(np.sum(w * rho_sym) ** 2) + 1e-12
    b_opt = (2.0 * g_hat**2 / d_hat) ** (1.0 / 3.0) * n ** (1.0 / 3.0)
    if not np.isfinite(b_opt) or b_opt < 1:
        return max(1, min(fallback, n // 3))
    return int(np.clip(round(b_opt), 1, n // 3))
