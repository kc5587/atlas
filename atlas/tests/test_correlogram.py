import numpy as np
import pandas as pd

from analysis.correlogram import correlogram_curve


def _series(n, seed):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    return pd.Series(rng.standard_normal(n), index=idx)


def test_correlogram_curve_shape_and_peak():
    left = _series(400, 1)
    # right is left shifted forward by 3 days => peak cross-corr near lag +3
    right = left.shift(3).fillna(0.0)
    out = correlogram_curve(left, right, max_lag=20, iters=200, seed=7)

    # one row per lag in [-20, 20]
    assert list(out["lag"]) == list(range(-20, 21))
    # required columns present
    assert {"lag", "corr", "ci_lo", "ci_hi", "is_peak", "passes_fdr"} <= set(out.columns)
    # band brackets the estimate
    assert (out["ci_lo"] <= out["corr"] + 1e-9).all()
    assert (out["ci_hi"] >= out["corr"] - 1e-9).all()
    # exactly one selected peak, at the strongest |corr|
    assert int(out["is_peak"].sum()) == 1
    peak_lag = int(out.loc[out["is_peak"], "lag"].iloc[0])
    assert peak_lag == int(out.loc[out["corr"].abs().idxmax(), "lag"])


def test_correlogram_curve_handles_short_series():
    left = _series(10, 2)
    right = _series(10, 3)
    out = correlogram_curve(left, right, max_lag=20, iters=50, seed=7)
    assert out.empty
