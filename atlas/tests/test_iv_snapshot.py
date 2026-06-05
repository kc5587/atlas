import pandas as pd


def _chain(strikes, ivs, ois, kind):
    return pd.DataFrame(
        {"strike": strikes, "impliedVolatility": ivs, "openInterest": ois, "type": kind}
    )


def test_atm_iv_picks_nearest_strike():
    from ingest.iv_snapshot import atm_iv

    calls = _chain([90, 100, 110], [0.40, 0.30, 0.35], [10, 10, 10], "call")
    assert atm_iv(calls, spot=101.0) == 0.30


def test_put_call_oi_ratio():
    from ingest.iv_snapshot import put_call_oi_ratio

    calls = _chain([100], [0.3], [200], "call")
    puts = _chain([100], [0.3], [300], "put")
    assert put_call_oi_ratio(calls, puts) == 1.5


def test_iv_snapshot_schema_validates():
    from ingest.schemas import IV_SNAPSHOT_SCHEMA

    df = pd.DataFrame(
        {
            "ticker": ["NVDA"],
            "date": pd.to_datetime(["2026-06-05"]),
            "atm_iv_30d": [0.45],
            "skew_25d": [0.05],
            "term_slope": [0.02],
            "put_call_oi": [1.1],
        }
    )
    assert len(IV_SNAPSHOT_SCHEMA.validate(df)) == 1


def test_merge_panel_dedupes_on_ticker_date():
    from ingest.iv_snapshot import merge_panel

    prior = pd.DataFrame(
        {
            "ticker": ["NVDA"],
            "date": pd.to_datetime(["2026-06-04"]),
            "atm_iv_30d": [0.40],
            "skew_25d": [0.05],
            "term_slope": [0.02],
            "put_call_oi": [1.0],
        }
    )
    today = pd.DataFrame(
        {
            "ticker": ["NVDA", "AMD"],
            "date": pd.to_datetime(["2026-06-04", "2026-06-05"]),
            "atm_iv_30d": [0.99, 0.50],
            "skew_25d": [0.06, 0.04],
            "term_slope": [0.03, 0.01],
            "put_call_oi": [1.1, 0.9],
        }
    )
    out = merge_panel(prior, today)
    assert len(out) == 2
    nvda = out[(out.ticker == "NVDA") & (out.date == pd.Timestamp("2026-06-04"))]
    assert float(nvda["atm_iv_30d"].iloc[0]) == 0.99


def test_load_prior_panel_missing_file_then_merge(tmp_path):
    # First-ever run: no panel file exists. The empty prior must not crash pandera
    # validation, and merging today's rows onto it must succeed.
    from ingest.iv_snapshot import _load_prior_panel, merge_panel

    prior = _load_prior_panel(tmp_path / "panel.parquet")
    assert list(prior.columns) == ["ticker", "date", "atm_iv_30d", "skew_25d",
                                   "term_slope", "put_call_oi"]
    assert len(prior) == 0
    today = pd.DataFrame([{"ticker": "NVDA", "date": pd.Timestamp("2026-06-06"),
                           "atm_iv_30d": 0.45, "skew_25d": 0.05, "term_slope": 0.02,
                           "put_call_oi": 1.1}])
    merged = merge_panel(prior, today)
    assert len(merged) == 1
