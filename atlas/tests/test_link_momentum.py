import numpy as np
import pandas as pd

from analysis.link_momentum import (
    link_backtest,
    link_predictability,
    link_signal_panel,
    monthly_returns,
    residual_monthly_returns,
)

_NODES = pd.DataFrame([
    {"id": "nvidia", "tickers": '["NVDA"]', "stage": "chips"},
    {"id": "microsoft", "tickers": '["MSFT"]', "stage": "cloud"},
    {"id": "meta", "tickers": '["META"]', "stage": "cloud"},
])
_EDGES = pd.DataFrame([
    {"from_id": "nvidia", "to_id": "microsoft", "relationship": "supplies"},
    {"from_id": "nvidia", "to_id": "meta", "relationship": "supplies"},
])


def test_h15_constants_exist():
    import config

    assert config.H15_MIN_MONTHS == 36
    assert config.H15_OOS_TEST_MONTHS == 12
    assert config.H15_OOS_STEP_MONTHS == 12


def test_monthly_returns_sums_daily_logs_per_month():
    dates = pd.date_range("2020-01-01", "2020-02-29", freq="D")
    df = pd.DataFrame({"ticker": "AAA", "date": dates, "log_return": 0.001})
    monthly = monthly_returns(df)

    assert list(monthly.columns) == ["AAA"]
    assert len(monthly) == 2
    assert abs(monthly["AAA"].iloc[0] - 31 * 0.001) < 1e-9


def test_residual_monthly_returns_removes_market_beta():
    idx = pd.date_range("2014-01-31", periods=96, freq="ME")
    rng = np.random.default_rng(0)
    spy = pd.Series(rng.normal(0, 0.04, len(idx)), index=idx)
    aaa = 1.5 * spy + pd.Series(rng.normal(0, 0.01, len(idx)), index=idx)
    monthly = pd.DataFrame({"AAA": aaa, "SPY": spy, "SOXX": spy * 0.9})
    nodes = pd.DataFrame([{"id": "a", "tickers": '["AAA"]', "stage": "chips"}])

    residual = residual_monthly_returns(monthly, nodes)
    valid = residual["AAA"].dropna()
    corr = np.corrcoef(valid, spy.loc[valid.index])[0, 1]

    assert abs(corr) < 0.2


def test_residual_monthly_returns_no_lookahead_at_target_month():
    idx = pd.date_range("2017-01-31", periods=72, freq="ME")
    target_month = idx[48]
    rng = np.random.default_rng(12)
    spy = pd.Series(rng.normal(0, 0.04, len(idx)), index=idx)
    igv = pd.Series(rng.normal(0, 0.035, len(idx)), index=idx)
    early_aaa = 1.1 * spy + 0.6 * igv + pd.Series(rng.normal(0, 0.005, len(idx)), index=idx)
    future_aaa = -4.0 * spy + 3.0 * igv + pd.Series(
        rng.normal(0, 0.005, len(idx)),
        index=idx,
    )
    aaa = pd.Series(
        np.where(idx > target_month, future_aaa.to_numpy(), early_aaa.to_numpy()),
        index=idx,
    )
    monthly = pd.DataFrame({"AAA": aaa, "SPY": spy, "IGV": igv})
    nodes = pd.DataFrame([{"id": "a", "tickers": '["AAA"]', "stage": "cloud"}])

    full = residual_monthly_returns(monthly, nodes)
    truncated = residual_monthly_returns(monthly.loc[:target_month], nodes)

    assert np.isfinite(full.loc[target_month, "AAA"])
    np.testing.assert_allclose(
        full.loc[target_month, "AAA"],
        truncated.loc[target_month, "AAA"],
        rtol=1e-12,
        atol=1e-12,
    )


def test_residualized_link_predictability_detects_planted_customer_supplier_signal():
    idx = pd.date_range("2014-01-31", periods=108, freq="ME")
    rng = np.random.default_rng(5)
    spy = pd.Series(rng.normal(0, 0.025, len(idx)), index=idx)
    igv = pd.Series(rng.normal(0, 0.02, len(idx)), index=idx)
    monthly = {"SPY": spy, "IGV": igv}
    nodes = []
    edges = []
    for k in range(6):
        supplier = f"S{k}"
        customer = f"C{k}"
        customer_resid = pd.Series(rng.normal(0, 0.04, len(idx)), index=idx)
        supplier_noise = rng.normal(0, 0.004, len(idx))
        supplier_resid = pd.Series(
            np.concatenate([
                supplier_noise[:1],
                supplier_noise[1:] + 0.9 * customer_resid.iloc[:-1].to_numpy(),
            ]),
            index=idx,
        )
        monthly[customer] = 0.8 * spy - 0.3 * igv + customer_resid
        monthly[supplier] = 1.2 * spy + 0.5 * igv + supplier_resid
        nodes.extend([
            {"id": f"supplier{k}", "tickers": f'["{supplier}"]', "stage": "cloud"},
            {"id": f"customer{k}", "tickers": f'["{customer}"]', "stage": "cloud"},
        ])
        edges.append({
            "from_id": f"supplier{k}",
            "to_id": f"customer{k}",
            "relationship": "supplies",
        })
    residual = residual_monthly_returns(pd.DataFrame(monthly), pd.DataFrame(nodes))
    panel = link_signal_panel(residual, pd.DataFrame(nodes), pd.DataFrame(edges), min_months=36)

    out = link_predictability(panel, iters=300, seed=6)

    assert out["slope"] > 0.5
    assert out["p_value"] < 0.05
    assert out["n_nodes"] == 6


def test_link_signal_panel_builds_customer_signal_and_forward_target():
    idx = pd.date_range("2020-01-31", periods=6, freq="ME")
    residual = pd.DataFrame({
        "NVDA": [0.0, 0.1, 0.2, -0.1, 0.05, 0.0],
        "MSFT": [0.02, 0.04, -0.01, 0.03, 0.0, 0.01],
        "META": [0.00, 0.02, 0.01, 0.05, 0.0, -0.02],
    }, index=idx)

    panel = link_signal_panel(residual, _NODES, _EDGES, min_months=3)
    row = panel[(panel["node"] == "nvidia") & (panel["month"] == idx[0])].iloc[0]

    assert abs(row["signal"] - np.mean([0.02, 0.00])) < 1e-9
    assert abs(row["fwd_target"] - 0.1) < 1e-9
    assert panel["month"].max() < idx[-1]


def _panel_with_signal(beta, n_nodes=8, n_months=60, noise=0.02, seed=0):
    rng = np.random.default_rng(seed)
    months = pd.date_range("2016-01-31", periods=n_months, freq="ME")
    rows = []
    for k in range(n_nodes):
        signal = rng.normal(0, 0.03, n_months)
        target = beta * signal + rng.normal(0, noise, n_months)
        rows.extend(
            {
                "node": f"n{k}",
                "month": month,
                "signal": signal[i],
                "fwd_target": target[i],
            }
            for i, month in enumerate(months)
        )
    return pd.DataFrame(rows)


def test_link_predictability_detects_positive_slope():
    out = link_predictability(_panel_with_signal(0.5), iters=300, seed=1)

    assert out["slope"] > 0
    assert out["p_value"] < 0.05
    assert 0.0 <= out["oos_sign_rate"] <= 1.0
    assert out["n_obs"] == 8 * 60


def test_link_predictability_null_on_noise():
    out = link_predictability(_panel_with_signal(0.0), iters=300, seed=2)

    assert out["p_value"] > 0.05


def test_link_backtest_profits_when_signal_predicts():
    rng = np.random.default_rng(0)
    months = pd.date_range("2016-01-31", periods=48, freq="ME")
    raw = {}
    rows = []
    for k in range(6):
        signal = rng.choice([-1.0, 1.0], 48) * 0.02
        returns = np.concatenate([
            [0.0],
            (np.sign(signal) * 0.03 + rng.normal(0, 0.01, 48))[:-1],
        ])
        raw[f"T{k}"] = pd.Series(returns, index=months)
        rows.extend(
            {
                "node": f"n{k}",
                "ticker": f"T{k}",
                "month": month,
                "signal": signal[i],
                "fwd_target": returns[i + 1],
            }
            for i, month in enumerate(months[:-1])
        )
    panel = pd.DataFrame(rows)
    raw_wide = pd.DataFrame(raw)

    out = link_backtest(panel, raw_wide)

    assert out["sharpe"] > 0
    assert out["n_months_bt"] > 10
    assert -1.0 <= out["max_drawdown"] <= 0.0
