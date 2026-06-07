import numpy as np
import pandas as pd

from analysis.link_momentum import monthly_returns, residual_monthly_returns


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
