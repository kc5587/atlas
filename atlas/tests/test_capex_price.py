from config import H5_FORWARD_HORIZONS

import numpy as np
import pandas as pd
from analysis.capex_price import capex_growth_at_filed, capex_price_edge, forward_excess_return


def test_horizons_are_one_and_two_quarters():
    assert H5_FORWARD_HORIZONS == (63, 126)


def _daily(start, n, vals):
    return pd.Series(vals, index=pd.bdate_range(start, periods=n))


def test_forward_excess_return_starts_strictly_after_filed():
    # Flat in train (alpha≈0), positive drift AFTER filed -> forward residual > 0.
    # (M2 residual subtracts fitted alpha, so a constant-everywhere series → ~0.)
    idx = pd.bdate_range("2020-01-01", periods=400)
    vals = np.where(np.arange(400) <= 100, 0.0, 0.001)
    asset = pd.Series(vals, index=idx)
    factors = {"SPY": pd.Series(0.0, index=idx), "SOXX": pd.Series(0.0, index=idx)}
    filed = idx[100]
    r = forward_excess_return(asset, factors, sector="SOXX", filed=filed, horizon_days=63)
    assert r > 0
    assert abs(r - 0.063) < 0.01


def test_forward_excess_return_nan_when_no_future_data():
    idx = pd.bdate_range("2020-01-01", periods=100)
    asset = pd.Series(0.001, index=idx)
    factors = {"SPY": pd.Series(0.0, index=idx), "SOXX": pd.Series(0.0, index=idx)}
    r = forward_excess_return(asset, factors, sector="SOXX", filed=idx[-1], horizon_days=63)
    assert np.isnan(r)


def test_capex_growth_indexed_by_filed_date():
    pe = pd.date_range("2018-03-31", periods=12, freq="QE")
    filed = pe + pd.Timedelta(days=40)
    fund = pd.DataFrame(
        {"ticker": "U", "period_end": pe, "filed": filed, "capex": np.linspace(100, 210, 12)}
    )
    g = capex_growth_at_filed(fund, "U")
    assert len(g) == 8
    assert (g.index == pd.DatetimeIndex(filed[4:])).all()


def test_capex_price_edge_detects_forward_predictability():
    rng = np.random.default_rng(0)
    pe = pd.date_range("2016-03-31", periods=28, freq="QE")
    filed = pe + pd.Timedelta(days=40)
    g = rng.standard_normal(28)
    capex_level = np.exp(np.cumsum(0.05 + 0.02 * np.concatenate([np.zeros(4), g[:-4]])))
    fund = pd.DataFrame({"ticker": "U", "period_end": pe, "filed": filed, "capex": capex_level})
    idx = pd.bdate_range("2015-06-01", periods=3000)
    daily = pd.Series(0.0, index=idx)
    cg = capex_growth_at_filed(fund, "U")
    for f, val in cg.items():
        win = daily.index[daily.index > f][:63]
        daily.loc[win] += 0.0008 * val
    daily += 0.0001 * pd.Series(rng.standard_normal(len(idx)), index=idx)
    factors = {"SPY": pd.Series(0.0, index=idx), "SOXX": pd.Series(0.0, index=idx)}
    out = capex_price_edge(cg, daily, factors, sector="SOXX", horizons=(63, 126), iters=200, seed=1)
    assert out["slope"] > 0
    assert out["horizon"] in (63, 126)
    assert out["n_obs"] >= 10
    assert out["contradicts_thesis"] is False


def test_capex_price_edge_null_for_unrelated_returns():
    rng = np.random.default_rng(2)
    pe = pd.date_range("2016-03-31", periods=28, freq="QE")
    filed = pe + pd.Timedelta(days=40)
    fund = pd.DataFrame(
        {
            "ticker": "U",
            "period_end": pe,
            "filed": filed,
            "capex": np.exp(np.cumsum(0.05 + 0.1 * rng.standard_normal(28))),
        }
    )
    idx = pd.bdate_range("2015-06-01", periods=3000)
    daily = 0.0002 * pd.Series(rng.standard_normal(len(idx)), index=idx)
    factors = {"SPY": pd.Series(0.0, index=idx), "SOXX": pd.Series(0.0, index=idx)}
    cg = capex_growth_at_filed(fund, "U")
    out = capex_price_edge(cg, daily, factors, sector="SOXX", horizons=(63, 126), iters=200, seed=3)
    assert out["p_selection"] > 0.1
