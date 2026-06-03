import numpy as np
import pandas as pd

from analysis.leadlag import (
    align_pair,
    bh_fdr,
    build_leadlag_table,
    cross_correlations,
    infer_period_freq,
    log_returns,
    resample_returns_to_freq,
    stationary_bootstrap_pvalue,
)


def test_log_returns_basic():
    s = pd.Series([100.0, 110.0, 121.0],
                  index=pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]))
    r = log_returns(s)
    assert len(r) == 2
    np.testing.assert_allclose(r.values, [np.log(1.1), np.log(1.1)], rtol=1e-9)


def test_align_pair_inner_join_no_ffill():
    a = pd.Series([1.0, 2.0, 3.0], index=pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]))
    b = pd.Series([10.0, 30.0], index=pd.to_datetime(["2024-01-01", "2024-01-03"]))
    xa, xb = align_pair(a, b)
    assert list(xa.index) == list(pd.to_datetime(["2024-01-01", "2024-01-03"]))
    assert len(xa) == len(xb) == 2


def test_cross_correlations_detects_lag():
    # y leads x by 2: x_t == y_{t-2}; so corr peaks at lag where upstream(y) leads.
    rng = np.random.default_rng(0)
    n = 500
    y = pd.Series(rng.standard_normal(n), index=pd.date_range("2020-01-01", periods=n, freq="B"))
    x = y.shift(2).dropna()
    y2, x2 = align_pair(y, x)
    table = cross_correlations(y2, x2, max_lag=5)
    peak = table.loc[table["corr"].abs().idxmax(), "lag"]
    assert peak == 2


def test_bh_fdr_monotone():
    p = np.array([0.001, 0.01, 0.2, 0.8])
    q = bh_fdr(p)
    assert (q >= p).all()
    assert q[0] <= q[-1]


def test_bootstrap_pvalue_in_unit_interval():
    rng = np.random.default_rng(1)
    n = 300
    x = pd.Series(rng.standard_normal(n))
    y = x * 0.5 + rng.standard_normal(n) * 0.5
    p = stationary_bootstrap_pvalue(x.values, y.values, iters=200, block=10, seed=3)
    assert 0.0 <= p <= 1.0
    assert p < 0.5  # genuine correlation -> smallish p

def test_build_leadlag_table_price_pairs(tmp_path):
    rng = np.random.default_rng(5)
    dates = pd.date_range("2019-01-01", periods=400, freq="B")
    y = rng.standard_normal(400)
    # nvidia leads microsoft by 1 day
    returns = pd.DataFrame(
        {
            "ticker": ["asml_t"] * 400 + ["tsmc_t"] * 400,
            "date": list(dates) * 2,
            "log_return": list(y) + list(np.roll(y, 1)),
        }
    )
    edges = pd.DataFrame(
        {"from_id": ["asml"], "to_id": ["tsmc"],
         "relationship": ["supplies"], "note": [""], "evidence": [""], "as_of": ["2024-01-01"]}
    )
    nodes = pd.DataFrame(
        {"id": ["asml", "tsmc"], "name": ["A", "T"],
         "tickers": ['["asml_t"]', '["tsmc_t"]'],
         "stage": ["equipment", "foundry"], "region": ["NL", "TW"]}
    )
    table = build_leadlag_table(returns, pd.DataFrame(columns=["series_id", "date", "value"]),
                                nodes, edges, max_lag=5, price_nmin=100, iters=100)
    assert set(["pair_type", "left", "right", "lag", "corr", "p_value", "q_value", "n_eff", "stable"]).issubset(table.columns)
    assert (table["pair_type"] == "edge").any()
    assert (table["q_value"] <= 1.0).all()
def test_infer_period_freq_monthly():
    idx = pd.date_range("2015-01-31", periods=24, freq="ME")
    assert infer_period_freq(idx) == "ME"


def test_infer_period_freq_daily():
    idx = pd.date_range("2020-01-01", periods=60, freq="B")
    assert infer_period_freq(idx) == "D"


def test_resample_returns_to_monthly_counts_periods():
    d = pd.date_range("2020-01-01", periods=400, freq="B")
    r = pd.Series(0.001, index=d)
    monthly = resample_returns_to_freq(r, "ME")
    assert len(monthly) <= 20  # ~19 months, far fewer than 400 daily obs


def test_macro_pairs_use_native_frequency(tmp_path):
    # Monthly macro must NOT be counted as daily observations.
    dates_d = pd.date_range("2015-01-01", periods=2000, freq="B")
    rng = np.random.default_rng(2)
    returns = pd.DataFrame(
        {"ticker": ["nvda_t"] * 2000, "date": dates_d,
         "log_return": rng.standard_normal(2000) * 0.01}
    )
    macro_dates = pd.date_range("2015-01-31", periods=96, freq="ME")
    macro = pd.DataFrame(
        {"series_id": ["IPG"] * 96, "date": macro_dates, "value": rng.standard_normal(96)}
    )
    nodes = pd.DataFrame(
        {"id": ["nvidia"], "name": ["NVIDIA"], "tickers": ['["nvda_t"]'],
         "stage": ["chips"], "region": ["US"]}
    )
    edges = pd.DataFrame(columns=["from_id", "to_id", "relationship", "note", "evidence", "as_of"])
    table = build_leadlag_table(returns, macro, nodes, edges, iters=50)
    macro_rows = table[table["pair_type"] == "macro"]
    assert not macro_rows.empty
    # n_eff reflects monthly periods (~96), not 2000 daily rows
    assert macro_rows["n_eff"].max() <= 96


def test_fundamentals_capex_revenue_pair():
    periods = pd.date_range("2016-03-31", periods=32, freq="QE")
    filed = periods + pd.Timedelta(days=40)
    rng = np.random.default_rng(11)
    capex = rng.normal(100, 10, 32)
    fundamentals = pd.DataFrame({
        "ticker": ["up_t"] * 32 + ["down_t"] * 32,
        "period_end": list(periods) * 2,
        "filed": list(filed) * 2,
        "revenue": [np.nan] * 32 + list(np.roll(capex, 1) * 5),
        "capex": list(capex) + [np.nan] * 32,
        "gross_margin": [np.nan] * 64,
    })
    nodes = pd.DataFrame({
        "id": ["up", "down"],
        "name": ["U", "D"],
        "tickers": ['["up_t"]', '["down_t"]'],
        "stage": ["foundry", "chips"],
        "region": ["US", "US"],
        "cik": ["1", "2"],
    })
    edges = pd.DataFrame({
        "from_id": ["up"],
        "to_id": ["down"],
        "relationship": ["supplies"],
        "note": [""],
        "evidence": [""],
        "as_of": ["2024-01-01"],
    })
    empty_ret = pd.DataFrame(columns=["ticker", "date", "log_return"])
    empty_macro = pd.DataFrame(columns=["series_id", "date", "value"])
    table = build_leadlag_table(
        empty_ret,
        empty_macro,
        nodes,
        edges,
        fundamentals=fundamentals,
        iters=100,
    )
    fund = table[table["pair_type"] == "fund_capex_rev"]
    assert not fund.empty
    assert fund["n_eff"].max() <= 32


def test_fundamentals_capex_price_pair_uses_filed_dates():
    periods = pd.date_range("2016-03-31", periods=32, freq="QE")
    filed = periods + pd.Timedelta(days=40)
    rng = np.random.default_rng(12)
    capex = rng.normal(100, 10, 32)
    returns = pd.DataFrame({
        "ticker": ["up_t"] * len(filed),
        "date": filed,
        "log_return": np.roll(capex, 1) * 0.001,
    })
    fundamentals = pd.DataFrame({
        "ticker": ["up_t"] * 32,
        "period_end": periods,
        "filed": filed,
        "revenue": [np.nan] * 32,
        "capex": capex,
        "gross_margin": [np.nan] * 32,
    })
    nodes = pd.DataFrame({
        "id": ["up"],
        "name": ["U"],
        "tickers": ['["up_t"]'],
        "stage": ["foundry"],
        "region": ["US"],
        "cik": ["1"],
    })
    edges = pd.DataFrame(columns=["from_id", "to_id", "relationship", "note", "evidence", "as_of"])
    empty_macro = pd.DataFrame(columns=["series_id", "date", "value"])
    table = build_leadlag_table(
        returns,
        empty_macro,
        nodes,
        edges,
        fundamentals=fundamentals,
        iters=100,
    )
    fund = table[table["pair_type"] == "fund_capex_price"]
    assert not fund.empty
    assert fund["n_eff"].max() <= 32
