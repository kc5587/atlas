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
