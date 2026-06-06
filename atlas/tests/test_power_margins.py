import numpy as np
import pandas as pd


def test_config_track3_constants():
    import config

    for sid in ("WPU0543", "IPG2211A2N"):
        assert sid in config.FRED_SERIES
    assert config.POWER_NAMES == ["VST", "NRG", "CEG", "ETN", "VRT", "D"]
    assert config.POWER_PRICE_SERIES == ("WPU0543",)
    assert config.POWER_DEMAND_SERIES == ("IPG2211A2N",)
    assert config.H9_LEAD_QUARTERS == (0, 1, 2)
    assert config.H10_HORIZON_MONTHS == (1, 2, 3)
    for sid in config.POWER_PRICE_SERIES + config.POWER_DEMAND_SERIES:
        assert config.INDICATOR_PUB_LAG_MONTHS[sid] >= 1


def test_sector_margin_delta_median():
    from analysis.power_margins import sector_margin_delta

    rows = []
    for tkr in ["MSFT", "ORCL"]:
        for i, q in enumerate(pd.period_range("2015Q1", periods=12, freq="Q")):
            rows.append(
                {
                    "ticker": tkr,
                    "period_end": q.to_timestamp(how="end"),
                    "gross_margin": 0.60 - 0.005 * i,
                }
            )
    fund = pd.DataFrame(rows)
    d = sector_margin_delta(fund, names=["MSFT", "ORCL"])
    assert isinstance(d.index, pd.PeriodIndex)
    assert abs(d.dropna().iloc[0] - (-0.005)) < 1e-9


def _macro_long(series_levels, start="2010-01-01", n=120):
    idx = pd.date_range(start, periods=n, freq="MS")
    return pd.concat(
        [
            pd.DataFrame({"series_id": series, "date": idx, "value": f(idx)})
            for series, f in series_levels.items()
        ],
        ignore_index=True,
    )


def test_power_margins_table_detects_compression():
    from analysis.power_margins import power_margins_table

    rng = np.random.default_rng(0)
    macro = _macro_long({"WPU0543": lambda i: np.exp(np.linspace(0, 0.8, len(i)))})
    rows = []
    for tkr in ["MSFT", "ORCL"]:
        for k, q in enumerate(pd.period_range("2010Q1", periods=40, freq="Q")):
            rows.append(
                {
                    "ticker": tkr,
                    "period_end": q.to_timestamp(how="end"),
                    "gross_margin": 0.60 - 0.001 * k + rng.normal(0, 0.0005),
                }
            )
    fund = pd.DataFrame(rows)
    out = power_margins_table(
        macro,
        fund,
        price_series=("WPU0543",),
        names=["MSFT", "ORCL"],
        leads=(0, 1, 2),
        pub_lag={"WPU0543": 1},
        iters=200,
        seed=1,
    )
    assert set(out["indicator"]) == {"WPU0543"}
    for col in (
        "best_lead",
        "slope",
        "slope_lo",
        "slope_hi",
        "p_selection",
        "q_value",
        "n_obs",
        "contradicts_thesis",
    ):
        assert col in out.columns
