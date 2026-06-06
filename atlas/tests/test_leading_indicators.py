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


def test_sector_revenue_yoy_median():
    from analysis.leading_indicators import sector_revenue_yoy

    rows = []
    for tkr, base in [("NVDA", 100.0), ("AMD", 50.0)]:
        for i, q in enumerate(pd.period_range("2018Q1", periods=12, freq="Q")):
            rows.append(
                {
                    "ticker": tkr,
                    "period_end": q.to_timestamp(how="end"),
                    "revenue": base * (1.10 ** i),
                }
            )
    fund = pd.DataFrame(rows)
    agg = sector_revenue_yoy(fund, names=["NVDA", "AMD"])

    assert abs(agg.dropna().iloc[0] - np.log(1.10 ** 4)) < 1e-6
    assert isinstance(agg.index, pd.PeriodIndex)


def test_indicator_revenue_lead_detects_planted_lead():
    from analysis.leading_indicators import indicator_revenue_lead

    rng = np.random.default_rng(0)
    q = pd.period_range("2008Q1", periods=60, freq="Q")
    ind = pd.Series(rng.normal(0, 0.05, 60), index=q)
    rev = pd.Series(
        0.8 * ind.shift(1).fillna(0).to_numpy() + rng.normal(0, 0.01, 60),
        index=q,
    )

    out = indicator_revenue_lead(ind, rev, leads=(1, 2), iters=300, seed=1)

    assert out["best_lead"] == 1
    assert out["slope"] > 0.5
    assert out["p_selection"] < 0.05
    assert out["slope_lo"] > 0
    assert out["n_obs"] >= 40
