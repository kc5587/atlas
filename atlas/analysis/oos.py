"""Anchored/expanding walk-forward OOS for lead/lag stability.

Per fold: select the peak lag on the (anchored) train slice, embargo the
boundary, then measure residual corr at that fixed lag on a fixed 252-day test
window. Reports the DISTRIBUTION of test corr; sign-rate is descriptive only
(folds overlap and returns autocorrelate — not independent Bernoulli trials).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analysis.significance import _corr_at_lag, _signed_peak


def walk_forward_folds(index, *, test_days, step_days, init_train_frac, embargo):
    index = pd.DatetimeIndex(index)
    n = len(index)
    k = int((init_train_frac * n) // test_days)
    init_train = n - k * test_days
    folds = []
    for i in range(k):
        train_end = init_train + i * step_days
        test_start = train_end + embargo
        test_end = train_end + test_days
        if test_end > n:
            break
        folds.append((index[:train_end], index[test_start:test_end]))
    return folds


def oos_stability(left: pd.Series, right: pd.Series, *, lag_min, lag_max,
                  test_days, step_days, init_train_frac, embargo) -> dict:
    paired = pd.concat([left.rename("l"), right.rename("r")], axis=1, join="inner").dropna()
    folds = walk_forward_folds(paired.index, test_days=test_days, step_days=step_days,
                               init_train_frac=init_train_frac, embargo=embargo)
    corrs, signs, ranges = [], [], []
    for train_idx, test_idx in folds:
        tr = paired.loc[train_idx]
        lag, train_corr = _signed_peak(tr["l"].to_numpy(), tr["r"].to_numpy(), lag_min, lag_max)
        te = paired.loc[test_idx]
        test_corr = _corr_at_lag(te["l"].to_numpy(), te["r"].to_numpy(), lag)
        if np.isfinite(test_corr):
            corrs.append(test_corr)
            signs.append(np.sign(test_corr) == np.sign(train_corr) if train_corr != 0 else False)
            ranges.append((str(test_idx[0].date()), str(test_idx[-1].date())))
    corrs_arr = np.array(corrs) if corrs else np.array([np.nan])
    return {
        "n_folds": len(corrs),
        "oos_corr_median": float(np.nanmedian(corrs_arr)),
        "oos_corr_iqr": float(np.nanpercentile(corrs_arr, 75) - np.nanpercentile(corrs_arr, 25)) if corrs else np.nan,
        "oos_sign_rate": float(np.mean(signs)) if signs else 0.0,
        "fold_date_ranges": ranges,
    }
