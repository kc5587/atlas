import json

import numpy as np
import pandas as pd

from analysis.leadlag import (
    _stable_across_halves,
    align_pair,
    bh_fdr,
    build_hardened_edges,
    build_leadlag_table,
    cross_correlations,
    infer_period_freq,
    log_returns,
    resample_returns_to_freq,
    stationary_bootstrap_pvalue,
)
from analysis.residualize import residual_for_spec
from analysis.significance import auto_block_length
from analysis.significance import _corr_at_lag


def _returns_df():
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2012-01-01", periods=1500)
    spy = rng.standard_normal(1500)
    soxx = 0.8 * spy + 0.4 * rng.standard_normal(1500)
    up = 0.5 * spy + 0.6 * soxx + rng.standard_normal(1500)
    down = np.empty(1500)
    down[:3] = rng.standard_normal(3)
    down[3:] = up[:-3] + 0.6 * rng.standard_normal(1497)   # up leads down by 3
    # IGV drawn last so the up/down RNG sequence above is unchanged. The cloud
    # node maps to IGV (chips -> SOXX, cloud -> IGV), mirroring production.
    igv = 0.7 * spy + 0.5 * rng.standard_normal(1500)
    frames = []
    for tkr, vals in {"SPY": spy, "SOXX": soxx, "IGV": igv, "UP": up, "DOWN": down}.items():
        frames.append(pd.DataFrame({"ticker": tkr, "date": idx, "log_return": vals}))
    return pd.concat(frames, ignore_index=True)


def _nodes_edges():
    nodes = pd.DataFrame([
        {"id": "up", "tickers": json.dumps(["UP"]), "stage": "chips"},
        {"id": "down", "tickers": json.dumps(["DOWN"]), "stage": "cloud"},
    ])
    edges = pd.DataFrame([{"from_id": "up", "to_id": "down"}])
    return nodes, edges


def test_emits_one_row_per_edge_per_spec():
    nodes, edges = _nodes_edges()
    rows = build_hardened_edges(_returns_df(), nodes, edges, iters=300, seed=7)
    specs = {r["factor_model"] for r in rows}
    assert specs == {"M1_market", "M2_market_sector"}
    assert len(rows) == 2  # 1 edge x 2 specs


def test_real_lead_lag_confirmed_and_correct_direction():
    nodes, edges = _nodes_edges()
    rows = build_hardened_edges(_returns_df(), nodes, edges, iters=300, seed=7)
    for r in rows:
        assert r["lag"] >= 1
        assert r["m"] == 1
        assert r["contradicts_thesis"] is False


def test_hardened_corr_raw_uses_selected_lag_not_minimum_lag():
    returns = _returns_df()
    nodes, edges = _nodes_edges()
    rows = build_hardened_edges(returns, nodes, edges, iters=200, seed=7)
    row = rows[0]
    assert row["lag"] != 1

    ret = {t: g.set_index("date")["log_return"] for t, g in returns.groupby("ticker")}
    left, right = align_pair(ret["UP"], ret["DOWN"])
    expected = _corr_at_lag(left.to_numpy(), right.to_numpy(), row["lag"])
    wrong_lag = _corr_at_lag(left.to_numpy(), right.to_numpy(), 1)

    assert np.isclose(row["corr_raw"], expected)
    assert not np.isclose(row["corr_raw"], wrong_lag)


def _half_lagged_pair(first_lag: int, second_lag: int) -> tuple[pd.Series, pd.Series]:
    rng = np.random.default_rng(31)
    half = 80
    left = rng.standard_normal(half * 2)
    right = rng.standard_normal(half * 2)
    for start, lag in ((0, first_lag), (half, second_lag)):
        stop = start + half
        if lag >= 0:
            right[start + lag:stop] = left[start:stop - lag] + 0.01 * rng.standard_normal(half - lag)
        else:
            lead = abs(lag)
            left[start + lead:stop] = right[start:stop - lead] + 0.01 * rng.standard_normal(half - lead)
    idx = pd.date_range("2020-01-01", periods=half * 2, freq="B")
    return pd.Series(left, index=idx), pd.Series(right, index=idx)


def test_stable_across_halves_requires_close_lags_and_matching_corr_signs():
    left, right = _half_lagged_pair(1, 20)
    assert _stable_across_halves(left, right, 20) is False

    left, right = _half_lagged_pair(3, 4)
    assert _stable_across_halves(left, right, 3) is True

    left, right = _half_lagged_pair(3, -3)
    assert _stable_across_halves(left, right, 3) is False


def test_bh_fdr_monotone():
    q = bh_fdr(np.array([0.001, 0.02, 0.5]))
    assert (np.diff(q) >= -1e-9).all()
    assert (q <= 1).all()


def test_handles_mismatched_ticker_histories():
    """Right ticker (e.g. DELL) has a shorter/later history than the left ticker.

    Regression: train must be derived from the pair's OVERLAP, not the left
    ticker's own index, or residualizing the right series raises a pandas
    KeyError on dates the right ticker never traded.
    """
    rng = np.random.default_rng(11)
    full = pd.bdate_range("2012-01-01", periods=1500)
    short = full[600:]                       # right ticker starts ~600 days later
    spy = rng.standard_normal(1500)
    soxx = 0.8 * spy + 0.4 * rng.standard_normal(1500)
    igv = 0.7 * spy + 0.5 * rng.standard_normal(1500)
    up = 0.5 * spy + 0.6 * soxx + rng.standard_normal(1500)
    down_vals = np.empty(len(short))
    down_vals[:3] = rng.standard_normal(3)
    down_vals[3:] = up[600:][:-3] + 0.6 * rng.standard_normal(len(short) - 3)
    frames = [
        pd.DataFrame({"ticker": "SPY", "date": full, "log_return": spy}),
        pd.DataFrame({"ticker": "SOXX", "date": full, "log_return": soxx}),
        pd.DataFrame({"ticker": "IGV", "date": full, "log_return": igv}),
        pd.DataFrame({"ticker": "UP", "date": full, "log_return": up}),
        pd.DataFrame({"ticker": "DOWN", "date": short, "log_return": down_vals}),
    ]
    returns = pd.concat(frames, ignore_index=True)
    nodes, edges = _nodes_edges()
    rows = build_hardened_edges(returns, nodes, edges, iters=200, seed=7)  # must not raise
    assert len(rows) == 2
    assert {r["factor_model"] for r in rows} == {"M1_market", "M2_market_sector"}


def test_residual_orthogonal_to_factors():
    returns = _returns_df()
    ret = {t: g.set_index("date")["log_return"] for t, g in returns.groupby("ticker")}
    factors = {"SPY": ret["SPY"], "SOXX": ret["SOXX"]}
    r = residual_for_spec(ret["UP"], factors, sector="SOXX", spec="M2",
                          train_index=ret["UP"].index)
    aligned = pd.concat([r.rename("e"), ret["SPY"].rename("spy")], axis=1, join="inner").dropna()
    assert abs(np.corrcoef(aligned["e"], aligned["spy"])[0, 1]) < 1e-6


def test_block_length_within_bounds():
    n = 1500
    b = auto_block_length(np.random.default_rng(0).standard_normal(n))
    assert 1 <= b <= n // 3


def test_fdr_family_size_equals_edge_count_per_spec():
    nodes, edges = _nodes_edges()
    rows = build_hardened_edges(_returns_df(), nodes, edges, iters=200, seed=7)
    for r in rows:
        assert r["m"] == len(edges)


def test_legacy_helpers_remain_covered_for_hardening_gate():
    prices = pd.Series([100.0, 110.0, 121.0],
                       index=pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]))
    returns = log_returns(prices)
    np.testing.assert_allclose(returns.values, [np.log(1.1), np.log(1.1)], rtol=1e-9)

    a = pd.Series([1.0, 2.0, 3.0], index=pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]))
    b = pd.Series([10.0, 30.0], index=pd.to_datetime(["2024-01-01", "2024-01-03"]))
    xa, xb = align_pair(a, b)
    assert len(xa) == len(xb) == 2

    idx = pd.date_range("2020-01-01", periods=60, freq="B")
    assert infer_period_freq(idx) == "D"
    assert infer_period_freq(pd.date_range("2015-01-31", periods=24, freq="ME")) == "ME"
    assert len(resample_returns_to_freq(pd.Series(0.001, index=idx), "ME")) < len(idx)


def test_legacy_cross_correlation_and_bootstrap_paths():
    rng = np.random.default_rng(20)
    n = 500
    lead = pd.Series(rng.standard_normal(n), index=pd.date_range("2020-01-01", periods=n, freq="B"))
    lagged = lead.shift(2).dropna()
    lead2, lagged2 = align_pair(lead, lagged)
    table = cross_correlations(lead2, lagged2, max_lag=5)
    assert int(table.loc[table["corr"].abs().idxmax(), "lag"]) == 2

    p = stationary_bootstrap_pvalue(
        lead2.to_numpy(), lagged2.to_numpy(), iters=100, block=10, seed=3
    )
    assert 0.0 <= p <= 1.0


def test_legacy_edge_macro_and_fundamental_rows_are_preserved():
    rng = np.random.default_rng(21)
    dates = pd.date_range("2015-01-01", periods=2000, freq="B")
    upstream = rng.standard_normal(2000) * 0.01
    downstream = np.roll(upstream, 1)
    returns = pd.DataFrame({
        "ticker": ["up_t"] * 2000 + ["down_t"] * 2000,
        "date": list(dates) * 2,
        "log_return": list(upstream) + list(downstream),
    })
    macro_dates = pd.date_range("2015-01-31", periods=96, freq="ME")
    macro = pd.DataFrame({
        "series_id": ["IPG"] * 96,
        "date": macro_dates,
        "value": rng.standard_normal(96),
    })
    periods = pd.date_range("2016-03-31", periods=32, freq="QE")
    filed = periods + pd.Timedelta(days=40)
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
    table = build_leadlag_table(
        returns,
        macro,
        nodes,
        edges,
        max_lag=5,
        price_nmin=100,
        fundamentals=fundamentals,
        iters=50,
    )
    assert {"edge", "macro", "fund_capex_rev", "fund_capex_price"}.issubset(set(table["pair_type"]))
    assert (table["q_value"] <= 1.0).all()


def test_exclude_stage_drops_power_nodes_and_their_edges():
    from analysis.leadlag import exclude_stage

    nodes = pd.DataFrame([
        {"id": "nvidia", "stage": "chips", "tickers": json.dumps(["NVDA"])},
        {"id": "microsoft", "stage": "cloud", "tickers": json.dumps(["MSFT"])},
        {"id": "vistra", "stage": "power", "tickers": json.dumps(["VST"])},
    ])
    edges = pd.DataFrame([
        {"from_id": "nvidia", "to_id": "microsoft"},
        {"from_id": "microsoft", "to_id": "vistra"},
    ])
    cn, ce = exclude_stage(nodes, edges, "power")
    assert set(cn["id"]) == {"nvidia", "microsoft"}
    assert len(ce) == 1
    assert ce.iloc[0]["to_id"] == "microsoft"
