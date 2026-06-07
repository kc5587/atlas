"""Selection-aware significance for one-sided lead/lag tests.

INVARIANT: the bootstrap null perturbs a SINGLE residual series independently,
never the pair jointly. Joint resampling preserves the lead/lag under test and
yields an invalid null.
"""
from __future__ import annotations

import numpy as np

from config import BOOTSTRAP_BLOCK


def corr_slope(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Pearson corr and OLS slope of y on x; NaN/NaN if degenerate (<3 pts or zero var)."""
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return np.nan, np.nan
    return float(np.corrcoef(x, y)[0, 1]), float(np.polyfit(x, y, 1)[0])


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
    # Clamp the flat-top bandwidth to the autocorrelations actually computed: for a
    # highly persistent series (e.g. overlapping realized-variance windows) 2*m can
    # exceed max_lag, which would index past `rho`. Non-persistent series have 2*m <
    # max_lag, so this is a no-op for them and existing verdicts are unchanged.
    M = max(1, min(2 * m, max_lag))
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


def circular_rotate(y: np.ndarray, shift: int) -> np.ndarray:
    """Circularly shift one series (preserves its autocorrelation exactly)."""
    return np.roll(np.asarray(y, dtype=float), int(shift))


def block_resample_one(y: np.ndarray, *, block: int, rng: np.random.Generator) -> np.ndarray:
    """Stationary block bootstrap of a SINGLE series (geometric block lengths)."""
    y = np.asarray(y, dtype=float)
    n = len(y)
    p = 1.0 / max(1, block)
    out = np.empty(n)
    i = 0
    while i < n:
        start = int(rng.integers(0, n))
        length = int(rng.geometric(p))
        for k in range(length):
            if i >= n:
                break
            out[i] = y[(start + k) % n]
            i += 1
    return out


def _corr_at_lag(left: np.ndarray, right: np.ndarray, lag: int) -> float:
    if lag >= 0:
        x, y = left[: len(left) - lag], right[lag:]
    else:
        x, y = left[-lag:], right[: len(right) + lag]
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return np.nan
    return float(np.corrcoef(x, y)[0, 1])


def _signed_peak(left, right, lag_min, lag_max) -> tuple[int, float]:
    """Lag in [lag_min, lag_max] maximizing SIGNED corr (the one-sided hypothesis)."""
    best_lag, best = lag_min, -np.inf
    for lag in range(lag_min, lag_max + 1):
        c = _corr_at_lag(left, right, lag)
        if np.isfinite(c) and c > best:
            best, best_lag = c, lag
    return best_lag, (best if np.isfinite(best) else np.nan)


def _abs_peak(left, right, lags) -> float:
    vals = [abs(_corr_at_lag(left, right, lag)) for lag in lags]
    vals = [v for v in vals if np.isfinite(v)]
    return max(vals) if vals else np.nan


def selection_aware(
    left: np.ndarray, right: np.ndarray, *,
    lag_min: int, lag_max: int, iters: int, seed: int,
    method: str = "block", block: int | None = None,
) -> dict:
    """Signed, one-sided, selection-aware p-value over positive lags.

    Null: perturb ONE series (block bootstrap default; circular rotation cross-check),
    recompute the signed max(+corr) over [lag_min, lag_max] each iteration.
    """
    left = np.asarray(left, dtype=float)
    right = np.asarray(right, dtype=float)
    rng = np.random.default_rng(seed)
    block = block or auto_block_length(right)

    lag, corr = _signed_peak(left, right, lag_min, lag_max)
    if not np.isfinite(corr):
        return {
            "lag": 0,
            "corr": np.nan,
            "corr_contemporaneous": _corr_at_lag(left, right, 0),
            "p_selection": 1.0,
            "block_len": int(block),
            "best_neg_lag_corr": np.nan,
            "contradicts_thesis": False,
            "inverse_lead": False,
        }
    pos_lags = range(lag_min, lag_max + 1)
    neg_lags = range(-lag_max, -lag_min + 1)
    pos_abs = _abs_peak(left, right, pos_lags)
    neg_abs = _abs_peak(left, right, neg_lags)
    # dominant positive-lag relationship sign (for inverse_lead)
    pa_lag = max(pos_lags, key=lambda L: (abs(_corr_at_lag(left, right, L)) if np.isfinite(_corr_at_lag(left, right, L)) else -1))
    pa_sign_corr = _corr_at_lag(left, right, pa_lag)

    count = 0
    for _ in range(iters):
        if method == "rotate":
            yb = circular_rotate(right, int(rng.integers(1, len(right))))
        else:
            yb = block_resample_one(right, block=block, rng=rng)
        _, null_peak = _signed_peak(left, yb, lag_min, lag_max)
        if np.isfinite(null_peak) and null_peak >= corr:
            count += 1
    p = (count + 1) / (iters + 1)

    return {
        "lag": int(lag),
        "corr": float(corr) if np.isfinite(corr) else np.nan,
        "corr_contemporaneous": _corr_at_lag(left, right, 0),
        "p_selection": float(p),
        "block_len": int(block),
        "best_neg_lag_corr": float(neg_abs) if np.isfinite(neg_abs) else np.nan,
        "contradicts_thesis": bool(np.isfinite(neg_abs) and np.isfinite(pos_abs) and neg_abs > pos_abs),
        "inverse_lead": bool(np.isfinite(pa_sign_corr) and pa_sign_corr < 0),
    }
