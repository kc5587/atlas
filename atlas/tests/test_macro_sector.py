import numpy as np
import pandas as pd


def _macro_long(series_levels, start="2008-01-01", n=180):
    idx = pd.date_range(start, periods=n, freq="MS")
    frames = [
        pd.DataFrame({"series_id": sid, "date": idx, "value": level(idx)})
        for sid, level in series_levels.items()
    ]
    return pd.concat(frames, ignore_index=True)


def _daily_returns(ticker, start="2008-01-01", n=4000, seed=3):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=n)
    return pd.DataFrame(
        {"ticker": ticker, "date": idx, "log_return": rng.normal(0, 0.01, n)}
    )


def test_monthly_returns_sum():
    from analysis.macro_sector import monthly_returns

    returns = _daily_returns("SOXX")
    monthly = monthly_returns(returns, "SOXX")

    assert isinstance(monthly.index, pd.DatetimeIndex)
    assert len(monthly) > 100
    assert abs(monthly.iloc[0]) < 0.5


def test_macro_sector_table_shapes_and_fdr():
    from analysis.macro_sector import macro_sector_table

    rng = np.random.default_rng(4)
    macro = _macro_long(
        {
            "IPG3344S": lambda i: np.exp(np.linspace(0, 0.6, len(i)))
            * (1 + rng.normal(0, 0.01, len(i))),
            "A34SNO": lambda i: np.exp(np.linspace(0, 0.3, len(i)))
            * (1 + rng.normal(0, 0.01, len(i))),
        }
    )
    returns = _daily_returns("SOXX")
    out = macro_sector_table(
        macro,
        returns,
        indicators=("IPG3344S", "A34SNO"),
        target="SOXX",
        horizons=(1, 2, 3),
        pub_lag={"IPG3344S": 1, "A34SNO": 2},
        iters=150,
        seed=5,
    )

    assert len(out) == 2 * 3
    for col in (
        "indicator",
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
