import numpy as np
import pandas as pd


def _const_vol_returns(n, sigma_daily, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2015-01-01", periods=n)
    return pd.Series(rng.normal(0, sigma_daily, n), index=idx)


def test_realized_var_annualized_recovers_known_sigma():
    from analysis.vol_premium import realized_var_annualized

    sigma_daily = 0.01
    r = _const_vol_returns(252 * 4, sigma_daily, seed=1)
    rv = realized_var_annualized(r.to_numpy())
    assert abs(rv - 252 * sigma_daily**2) < 0.25 * (252 * sigma_daily**2)


def test_vrp_series_positive_when_implied_above_realized():
    from analysis.vol_premium import vrp_series

    r = _const_vol_returns(600, 0.01, seed=2)
    implied = pd.Series(25.0, index=r.index)
    vrp = vrp_series(implied, r, horizon=21)
    assert vrp.notna().sum() > 100
    assert vrp.mean() > 0


def test_vrp_timeseries_aligned_points():
    from analysis.vol_premium import vrp_timeseries

    idx = pd.date_range("2021-01-01", periods=120, freq="B")
    iv = pd.Series(np.linspace(18, 22, 120), index=idx)
    r = pd.Series(np.random.default_rng(7).standard_normal(120) * 0.01, index=idx)

    out = vrp_timeseries(iv, r, horizon=21)
    assert {"date", "implied_var", "realized_var", "vrp"} <= set(out.columns)
    assert len(out) >= 1
    row = out.iloc[0]
    assert abs(row["implied_var"] - row["realized_var"] - row["vrp"]) < 1e-9
    assert row["implied_var"] > 0


def test_incremental_oos_r2_positive_when_iv_carries_signal():
    from analysis.vol_premium import incremental_oos_r2

    rng = np.random.default_rng(3)
    n = 1500
    idx = pd.bdate_range("2010-01-01", periods=n)
    iv = pd.Series(20 + 5 * np.sin(np.arange(n) / 40.0), index=idx)
    fwd_rv = pd.Series((iv.to_numpy() / 100.0) ** 2 + rng.normal(0, 0.0003, n), index=idx)
    lag_rv = fwd_rv.shift(21).bfill()
    r2 = incremental_oos_r2(
        iv=iv,
        fwd_rv=fwd_rv,
        lag_rv=lag_rv,
        horizon=21,
        test_days=252,
        step_days=252,
        init_train_frac=0.5,
    )
    assert r2 > 0


def _make_returns_df(tickers, n=900, seed=4):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2012-01-01", periods=n)
    frames = []
    for ticker in tickers:
        frames.append(
            pd.DataFrame(
                {"ticker": ticker, "date": idx, "log_return": rng.normal(0, 0.01, n)}
            )
        )
    return pd.concat(frames, ignore_index=True)


def _make_vol_df(series, n=900, level=22.0, seed=5):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2012-01-01", periods=n)
    frames = []
    for name in series:
        frames.append(
            pd.DataFrame(
                {"series": name, "date": idx, "close": level + rng.normal(0, 1.0, n)}
            )
        )
    return pd.concat(frames, ignore_index=True)


def test_vol_premium_table_shape_and_positive_vrp():
    from analysis.vol_premium import vol_premium_table
    from config import BOOTSTRAP_ITERS, H6_PAIRS, H6_RV_HORIZON, RANDOM_SEED

    returns = _make_returns_df(["SPY", "QQQ"])
    vol = _make_vol_df(["^VIX", "^VXN"], level=25.0)
    out = vol_premium_table(
        vol,
        returns,
        pairs=H6_PAIRS,
        horizon=H6_RV_HORIZON,
        iters=BOOTSTRAP_ITERS,
        seed=RANDOM_SEED,
    )
    assert set(out["pair"]) == {"^VIX~SPY", "^VXN~QQQ"}
    for col in ("mean_vrp", "vrp_lo", "vrp_hi", "incremental_oos_r2", "n_obs"):
        assert col in out.columns
    assert (out["mean_vrp"] > 0).all()


def test_incremental_oos_r2_not_positive_for_unrelated_iv():
    # Embargo regression: with IV independent of forward RV, adding IV must NOT improve
    # OOS forecast. A missing embargo leaks the overlapping forward window and can
    # manufacture a spurious positive incremental R2.
    from analysis.vol_premium import incremental_oos_r2

    rng = np.random.default_rng(202)
    n = 1600
    idx = pd.bdate_range("2010-01-01", periods=n)
    base = np.abs(rng.normal(0.04, 0.01, n))
    fwd_rv = pd.Series(pd.Series(base).rolling(21, min_periods=1).mean().to_numpy(), index=idx)
    lag_rv = fwd_rv.shift(21)
    iv = pd.Series(rng.normal(20, 5, n), index=idx)  # independent of fwd_rv
    r2 = incremental_oos_r2(
        iv=iv, fwd_rv=fwd_rv, lag_rv=lag_rv, horizon=21,
        test_days=252, step_days=252, init_train_frac=0.5,
    )
    assert r2 <= 0.02
