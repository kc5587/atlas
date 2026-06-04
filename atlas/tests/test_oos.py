import numpy as np
import pandas as pd

from analysis.oos import oos_stability, walk_forward_folds


def test_folds_anchored_with_fixed_test_window_and_embargo():
    idx = pd.bdate_range("2010-01-01", periods=4128)
    folds = walk_forward_folds(idx, test_days=252, step_days=252,
                               init_train_frac=0.5, embargo=20)
    assert len(folds) == 8
    for train_idx, test_idx in folds:
        assert train_idx[0] == idx[0]          # anchored: always starts at origin
        assert len(test_idx) == 252 - 20       # 232 usable after embargo
        assert train_idx[-1] < test_idx[0]     # no overlap


def test_short_series_yields_fewer_but_not_thinner_folds():
    idx = pd.bdate_range("2016-08-18", periods=2461)
    folds = walk_forward_folds(idx, test_days=252, step_days=252,
                               init_train_frac=0.5, embargo=20)
    assert len(folds) == 4
    assert all(len(t) == 232 for _, t in folds)


def test_oos_stability_reports_sign_retention():
    # Synthetic: left leads right by 3, positive corr, stable across folds.
    rng = np.random.default_rng(0)
    n = 2000
    left = rng.standard_normal(n)
    right = np.empty(n)
    right[:3] = rng.standard_normal(3)
    right[3:] = left[:-3] + 0.5 * rng.standard_normal(n - 3)
    idx = pd.bdate_range("2012-01-01", periods=n)
    out = oos_stability(pd.Series(left, idx), pd.Series(right, idx),
                        lag_min=1, lag_max=20, test_days=252, step_days=252,
                        init_train_frac=0.5, embargo=20)
    assert out["n_folds"] >= 3
    assert out["oos_sign_rate"] >= 0.6
    assert np.isfinite(out["oos_corr_median"])
    assert len(out["fold_date_ranges"]) == out["n_folds"]
