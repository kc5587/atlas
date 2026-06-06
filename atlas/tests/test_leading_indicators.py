import numpy as np
import pandas as pd


def test_config_track2_constants():
    import config

    # leading-indicator FRED ids are present in FRED_SERIES and in LEADING_INDICATORS
    for sid in ("XTEXVA01KRM664S", "IPG3344S", "CAPUTLG3344S", "PCU334413334413", "A34SNO"):
        assert sid in config.FRED_SERIES
        assert sid in config.LEADING_INDICATORS
    assert config.SEMIS_REVENUE_NAMES == ["AMAT", "LRCX", "NVDA", "AMD", "AVGO", "MU"]
    assert config.H8_LEAD_QUARTERS == (1, 2)
    assert config.H4_HORIZON_MONTHS == (1, 2, 3)
    # every indicator has a publication lag (months)
    for sid in config.LEADING_INDICATORS:
        assert config.INDICATOR_PUB_LAG_MONTHS[sid] >= 1


def test_indicator_yoy_pit_lag():
    from analysis.leading_indicators import indicator_yoy

    idx = pd.date_range("2018-01-01", periods=36, freq="MS")
    level = pd.Series(np.exp(np.linspace(0, 0.36, 36)), index=idx)
    yoy = indicator_yoy(level, pub_lag_months=1)

    # First 12 months drop (no YoY base), then ref month 2019-01 becomes available 2019-02.
    assert yoy.index.min() == pd.Timestamp("2019-02-01")
    assert abs(yoy.iloc[0] - 0.12) < 0.02
    assert yoy.isna().sum() == 0
