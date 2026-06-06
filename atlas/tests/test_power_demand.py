import numpy as np
import pandas as pd


def _macro_long(series_levels, start="2008-01-01", n=180):
    idx = pd.date_range(start, periods=n, freq="MS")
    return pd.concat(
        [
            pd.DataFrame({"series_id": series, "date": idx, "value": f(idx)})
            for series, f in series_levels.items()
        ],
        ignore_index=True,
    )


def _daily_returns(tickers, start="2008-01-01", n=4000, seed=3):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=n)
    return pd.concat(
        [
            pd.DataFrame(
                {
                    "ticker": ticker,
                    "date": idx,
                    "log_return": rng.normal(0, 0.012, n),
                }
            )
            for ticker in tickers
        ],
        ignore_index=True,
    )


def test_power_demand_table_shapes_and_fdr():
    from analysis.power_demand import power_demand_table

    macro = _macro_long({"IPG2211A2N": lambda i: np.exp(np.linspace(0, 0.4, len(i)))})
    returns = _daily_returns(["VST", "ETN", "D"])
    out = power_demand_table(
        macro,
        returns,
        demand_series=("IPG2211A2N",),
        names=["VST", "ETN", "D"],
        horizons=(1, 2, 3),
        pub_lag={"IPG2211A2N": 1},
        iters=150,
        seed=5,
    )
    assert len(out) == 3 * 3
    for col in (
        "name",
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
