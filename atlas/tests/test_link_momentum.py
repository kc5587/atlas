import numpy as np
import pandas as pd

from analysis.link_momentum import link_signal_panel, monthly_returns, residual_monthly_returns

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
    idx = pd.date_range("2018-01-31", periods=48, freq="ME")
    rng = np.random.default_rng(0)
    spy = pd.Series(rng.normal(0, 0.04, 48), index=idx)
    aaa = 1.5 * spy + pd.Series(rng.normal(0, 0.02, 48), index=idx)
    monthly = pd.DataFrame({"AAA": aaa, "SPY": spy, "SOXX": spy * 0.9})
    nodes = pd.DataFrame([{"id": "a", "tickers": '["AAA"]', "stage": "chips"}])

    residual = residual_monthly_returns(monthly, nodes)
    valid = residual["AAA"].dropna()
    corr = np.corrcoef(valid, spy.loc[valid.index])[0, 1]

    assert abs(corr) < 0.2


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
