import json

import numpy as np
import pandas as pd
from analysis.event_drift import capex_surprise, event_drift, pooled_events

from config import H2_DRIFT_HORIZONS, H2_SURPRISE_K


def test_h2_config():
    assert H2_DRIFT_HORIZONS == (21, 42, 63)
    assert H2_SURPRISE_K == 4


def _fund(ticker, n=24, start="2016-03-31"):
    pe = pd.date_range(start, periods=n, freq="QE")
    filed = pe + pd.Timedelta(days=40)
    rng = np.random.default_rng(0)
    capex = np.exp(np.cumsum(0.05 + 0.1 * rng.standard_normal(n)))
    return pd.DataFrame({"ticker": ticker, "period_end": pe, "filed": filed, "capex": capex})


def test_capex_surprise_is_standardized_and_filing_indexed():
    s = capex_surprise(_fund("U"), "U", k=4)
    assert isinstance(s.index, pd.DatetimeIndex)
    assert abs(s.mean()) < 1.0 and 0.3 < s.std() < 3.0
    f2 = _fund("U")
    base = capex_surprise(f2, "U", k=4)
    f2.loc[f2.index[-1], "capex"] *= 5
    after = capex_surprise(f2, "U", k=4)
    assert np.allclose(base.iloc[:-1].to_numpy(), after.iloc[:-1].to_numpy())


def test_pooled_events_pools_across_edges_after_filing():
    fund = pd.concat([_fund("U"), _fund("V")], ignore_index=True)
    ridx = pd.bdate_range("2015-06-01", periods=3000)
    rng = np.random.default_rng(1)
    returns = pd.concat(
        [
            pd.DataFrame(
                {"ticker": "D", "date": ridx, "log_return": 0.0002 * rng.standard_normal(len(ridx))}
            ),
        ],
        ignore_index=True,
    )
    factors = {"SPY": pd.Series(0.0, index=ridx), "SOXX": pd.Series(0.0, index=ridx)}
    nodes = pd.DataFrame(
        [
            {"id": "u", "tickers": json.dumps(["U"]), "stage": "chips"},
            {"id": "v", "tickers": json.dumps(["V"]), "stage": "chips"},
            {"id": "d", "tickers": json.dumps(["D"]), "stage": "cloud"},
        ]
    )
    edges = pd.DataFrame([{"from_id": "u", "to_id": "d"}, {"from_id": "v", "to_id": "d"}])
    ev = pooled_events(fund, returns, factors, nodes, edges, horizon=42, k=4)
    assert {"date", "surprise", "fwd"}.issubset(ev.columns)
    assert len(ev) > 20
    assert ev["date"].is_monotonic_increasing


def _nodes_edges():
    nodes = pd.DataFrame(
        [
            {"id": "u", "tickers": json.dumps(["U"]), "stage": "chips"},
            {"id": "d", "tickers": json.dumps(["D"]), "stage": "cloud"},
        ]
    )
    edges = pd.DataFrame([{"from_id": "u", "to_id": "d"}])
    return nodes, edges


def test_event_drift_detects_positive_under_reaction():
    fund = _fund("U", n=28)
    surprises = capex_surprise(fund, "U", k=4)
    ridx = pd.bdate_range("2015-06-01", periods=3200)
    daily = pd.Series(0.0, index=ridx)
    for filed, value in surprises.items():
        win = daily.index[daily.index > filed][:42]
        daily.loc[win] += 0.0006 * value
    rng = np.random.default_rng(3)
    daily += 0.0001 * pd.Series(rng.standard_normal(len(ridx)), index=ridx)
    returns = pd.DataFrame({"ticker": "D", "date": ridx, "log_return": daily.to_numpy()})
    factors = {"SPY": pd.Series(0.0, index=ridx), "SOXX": pd.Series(0.0, index=ridx)}
    nodes, edges = _nodes_edges()
    out = event_drift(
        fund, returns, factors, nodes, edges, horizons=(21, 42, 63), iters=200, seed=1
    )
    assert out["slope"] > 0
    assert out["n_events"] > 10
    assert out["pos_drift"] > out["neg_drift"]


def test_event_drift_null_for_noise():
    fund = _fund("U", n=28)
    ridx = pd.bdate_range("2015-06-01", periods=3200)
    rng = np.random.default_rng(5)
    returns = pd.DataFrame(
        {"ticker": "D", "date": ridx, "log_return": 0.0002 * rng.standard_normal(len(ridx))}
    )
    factors = {"SPY": pd.Series(0.0, index=ridx), "SOXX": pd.Series(0.0, index=ridx)}
    nodes, edges = _nodes_edges()
    out = event_drift(
        fund, returns, factors, nodes, edges, horizons=(21, 42, 63), iters=200, seed=2
    )
    assert out["p_selection"] > 0.1
