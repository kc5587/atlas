"""By-lag cross-correlogram with a block-bootstrap CI band.

This module is additive export support only; it does not write hypothesis verdict tables.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analysis.leadlag import align_pair, cross_correlations
from analysis.significance import auto_block_length

_MIN_OBS = 60
_COLUMNS = ["lag", "corr", "ci_lo", "ci_hi", "is_peak", "passes_fdr"]


def _stationary_block_indices(
    n: int,
    block: int,
    rng: np.random.Generator,
) -> np.ndarray:
    """Indices for one stationary-bootstrap resample of length n."""
    idx = np.empty(n, dtype=int)
    i = 0
    while i < n:
        start = rng.integers(0, n)
        length = rng.geometric(1.0 / block)
        for k in range(length):
            if i >= n:
                break
            idx[i] = (start + k) % n
            i += 1
    return idx


def _bh_qvalues(pvalues: np.ndarray) -> np.ndarray:
    q = np.full(len(pvalues), np.nan, dtype=float)
    finite = np.isfinite(pvalues)
    if not finite.any():
        return q
    p = pvalues[finite]
    order = np.argsort(p)
    ranked = p[order] * len(p) / (np.arange(len(p)) + 1)
    q_sorted = np.minimum.accumulate(ranked[::-1])[::-1]
    q_valid = np.empty(len(p), dtype=float)
    q_valid[order] = np.clip(q_sorted, 0, 1)
    q[finite] = q_valid
    return q


def correlogram_curve(
    left: pd.Series,
    right: pd.Series,
    *,
    max_lag: int,
    iters: int,
    seed: int,
    ci: float = 0.95,
) -> pd.DataFrame:
    """Cross-correlation by lag in [-max_lag, max_lag] with bootstrap CI bands."""
    a, b = align_pair(left, right)
    if len(a) < _MIN_OBS:
        return pd.DataFrame(columns=_COLUMNS)

    lags = list(range(-max_lag, max_lag + 1))
    base = cross_correlations(a, b, max_lag=max_lag).set_index("lag")["corr"].reindex(lags)

    av = a.to_numpy()
    bv = b.to_numpy()
    block = auto_block_length(av)
    rng = np.random.default_rng(seed)
    draws = np.full((iters, len(lags)), np.nan)
    for it in range(iters):
        sel = _stationary_block_indices(len(av), block, rng)
        ra = pd.Series(av[sel], index=a.index)
        rb = pd.Series(bv[sel], index=b.index)
        cc = cross_correlations(ra, rb, max_lag=max_lag).set_index("lag")["corr"].reindex(lags)
        draws[it, :] = cc.to_numpy()

    lo_q = (1.0 - ci) / 2.0
    ci_lo = np.nanpercentile(draws, 100 * lo_q, axis=0)
    ci_hi = np.nanpercentile(draws, 100 * (1.0 - lo_q), axis=0)

    corr = base.to_numpy()
    ci_lo = np.minimum(ci_lo, corr)
    ci_hi = np.maximum(ci_hi, corr)
    centred = draws - np.nanmean(draws, axis=0)
    pvalues = np.array([
        (np.sum(np.abs(centred[:, j]) >= abs(corr[j])) + 1)
        / (np.sum(~np.isnan(centred[:, j])) + 1)
        for j in range(len(lags))
    ])
    qvalues = _bh_qvalues(pvalues)

    finite_corr = np.where(np.isfinite(corr), np.abs(corr), -np.inf)
    peak_idx = int(np.argmax(finite_corr))
    is_peak = np.zeros(len(lags), dtype=bool)
    if np.isfinite(finite_corr[peak_idx]):
        is_peak[peak_idx] = True

    return pd.DataFrame({
        "lag": lags,
        "corr": corr,
        "ci_lo": ci_lo,
        "ci_hi": ci_hi,
        "is_peak": is_peak,
        "passes_fdr": qvalues <= 0.10,
    })
