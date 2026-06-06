import numpy as np
import pandas as pd


def test_termstructure_slope_ratio():
    from analysis.vol_termstructure import termstructure_slope

    idx = pd.bdate_range("2015-01-01", periods=5)
    vix = pd.Series([20, 22, 18, 30, 15], index=idx, dtype=float)
    vix3m = pd.Series([18, 20, 20, 24, 18], index=idx, dtype=float)
    s = termstructure_slope(vix, vix3m)
    assert np.isclose(s.iloc[0], 20 / 18)
    assert (s.index == idx).all()


def test_aligned_forward_returns_planted_relationship():
    from analysis.vol_termstructure import aligned_forward

    rng = np.random.default_rng(7)
    n = 800
    idx = pd.bdate_range("2012-01-01", periods=n)
    s = pd.Series(1.0 + rng.normal(0, 0.1, n), index=idx)
    base = pd.Series(rng.normal(0, 0.01, n), index=idx)
    log_ret = base + 0.02 * (s.shift(21).fillna(1.0) - 1.0)
    x, y = aligned_forward(s, log_ret, horizon=21)
    assert len(x) == len(y) > 300
    assert np.corrcoef(x, y)[0, 1] > 0


def test_aligned_forward_supports_short_monthly_horizon():
    from analysis.vol_termstructure import aligned_forward

    idx = pd.date_range("2020-01-01", periods=8, freq="MS")
    slope = pd.Series(np.arange(8, dtype=float), index=idx)
    log_ret = pd.Series(np.arange(10, 18, dtype=float), index=idx)

    x, y = aligned_forward(slope, log_ret, horizon=1)

    assert x.tolist() == list(range(7))
    assert y.tolist() == list(range(11, 18))


def test_selection_pvalue_small_when_signal_strong():
    from analysis.vol_termstructure import selection_pvalue_one_series

    rng = np.random.default_rng(11)
    x = rng.normal(1.0, 0.1, 500)
    y = 0.5 * (x - 1.0) + rng.normal(0, 0.02, 500)
    p = selection_pvalue_one_series(x, y, iters=300, seed=1)
    assert p < 0.05


def test_selection_pvalue_large_when_no_signal():
    # Under a true null (x independent of y) the one-sided p must be well-calibrated
    # across many independent draws (~Uniform), not a fabricated constant and not
    # systematically tiny. A single-draw assertion would itself be tautological.
    from analysis.vol_termstructure import selection_pvalue_one_series

    pvals = []
    for s in range(24):
        rng = np.random.default_rng(1000 + s)
        x = rng.normal(1.0, 0.1, 600)
        y = rng.normal(0.0, 0.02, 600)
        pvals.append(selection_pvalue_one_series(x, y, iters=300, seed=s))
    pvals = np.array(pvals)
    assert pvals.std() > 0.05            # genuine variation, not a constant
    assert (pvals < 0.05).mean() <= 0.25  # rejection rate near alpha, not inflated
    assert pvals.mean() > 0.30            # centered well above zero


def test_oos_sign_rate_high_for_stable_positive():
    from analysis.vol_termstructure import oos_sign_rate

    rng = np.random.default_rng(13)
    n = 1600
    idx = pd.bdate_range("2010-01-01", periods=n)
    s = pd.Series(1.0 + rng.normal(0, 0.1, n), index=idx)
    log_ret = pd.Series(rng.normal(0, 0.01, n), index=idx) + 0.03 * (
        s.shift(21).fillna(1.0) - 1.0
    )
    rate = oos_sign_rate(
        s,
        log_ret,
        horizon=21,
        test_days=252,
        step_days=252,
        init_train_frac=0.5,
    )
    assert rate >= 0.6


def _vol_df(series_levels, n=1000, seed=21):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2011-01-01", periods=n)
    frames = []
    for series, lvl in series_levels.items():
        frames.append(
            pd.DataFrame(
                {"series": series, "date": idx, "close": lvl + rng.normal(0, 1.0, n)}
            )
        )
    return pd.concat(frames, ignore_index=True)


def _ret_df(tickers, n=1000, seed=22):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2011-01-01", periods=n)
    frames = [
        pd.DataFrame({"ticker": t, "date": idx, "log_return": rng.normal(0, 0.01, n)})
        for t in tickers
    ]
    return pd.concat(frames, ignore_index=True)


def test_vol_termstructure_table_family_and_fdr_columns():
    from analysis.vol_termstructure import vol_termstructure_table
    from config import BOOTSTRAP_ITERS, H7_HORIZONS, H7_PREDICTOR, H7_TARGETS, RANDOM_SEED

    vol = _vol_df({"^VIX": 20.0, "^VIX3M": 21.0})
    returns = _ret_df(list(H7_TARGETS))
    out = vol_termstructure_table(
        vol,
        returns,
        predictor=H7_PREDICTOR,
        targets=H7_TARGETS,
        horizons=H7_HORIZONS,
        iters=BOOTSTRAP_ITERS,
        seed=RANDOM_SEED,
    )
    assert len(out) == len(H7_TARGETS) * len(H7_HORIZONS)
    for col in (
        "target",
        "horizon",
        "corr",
        "slope",
        "slope_lo",
        "slope_hi",
        "p_selection",
        "q_value",
        "oos_sign_rate",
        "n_obs",
        "contradicts_thesis",
    ):
        assert col in out.columns
    assert out["q_value"].notna().all()


def test_selection_pvalue_runs_null_even_when_obs_corr_below_point_one():
    # Regression: a fabricated short-circuit (obs<0.10 -> p=0.50) bypassed the
    # resampling null and contaminated the FDR family. A weak-but-real signal whose
    # observed corr is < 0.10 must still get a genuine (small) p from the null.
    from analysis.vol_termstructure import selection_pvalue_one_series

    rng = np.random.default_rng(101)
    n, rho = 6000, 0.07
    x = rng.normal(0.0, 1.0, n)
    y = rho * x + np.sqrt(1 - rho**2) * rng.normal(0.0, 1.0, n)
    obs = float(np.corrcoef(x, y)[0, 1])
    assert 0.0 < obs < 0.10  # precondition: lands in the old buggy regime
    p = selection_pvalue_one_series(x, y, iters=500, seed=3)
    assert p != 0.5  # not the fabricated constant
    assert p < 0.05  # genuine null: a ~5-sigma signal is significant


def test_degenerate_cell_qvalue_is_nan_not_one():
    # Degenerate (non-eligible) cells must keep q_value NaN, mirroring capex_price/H5,
    # so they cannot perturb the BH-FDR of genuinely-tested cells.
    from analysis.vol_termstructure import vol_termstructure_table

    vol = _vol_df({"^VIX": 20.0, "^VIX3M": 21.0})
    returns = _ret_df(["SPY"])
    out = vol_termstructure_table(
        vol, returns, predictor=("^VIX", "^VIX3M"),
        targets=("SPY",), horizons=(21, 100000), iters=200, seed=7,
    )
    deg = out[out["horizon"] == 100000]
    elig = out[out["horizon"] == 21]
    assert deg["slope"].isna().all()
    assert deg["q_value"].isna().all()
    assert elig["q_value"].notna().all()
