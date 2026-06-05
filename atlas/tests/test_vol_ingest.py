import pandas as pd
import pytest


def test_config_exposes_vol_constants():
    import config

    assert config.AUX_TICKERS == ["QQQ"]
    assert set(config.VOL_SERIES) == {"^VIX9D", "^VIX", "^VIX3M", "^VIX6M", "^VXN"}
    assert config.VOL_FRED_FALLBACK["^VIX"] == "VIXCLS"
    assert config.VOL_FRED_FALLBACK["^VXN"] == "VXNCLS"
    assert config.H6_RV_HORIZON == 21
    assert config.H6_PAIRS == (("^VIX", "SPY"), ("^VXN", "QQQ"))
    assert config.H7_PREDICTOR == ("^VIX", "^VIX3M")
    assert config.H7_TARGETS == ("SPY", "SOXX", "IGV")
    assert config.H7_HORIZONS == (21, 42, 63)


def test_vol_schema_validates_long_frame():
    from ingest.schemas import VOL_SCHEMA

    df = pd.DataFrame(
        {
            "series": ["^VIX", "^VIX"],
            "date": pd.to_datetime(["2020-01-02", "2020-01-03"]),
            "close": [12.5, 13.1],
        }
    )
    assert len(VOL_SCHEMA.validate(df)) == 2


def test_vol_schema_rejects_negative_close():
    import pandera.errors as pae

    from ingest.schemas import VOL_SCHEMA

    bad = pd.DataFrame(
        {"series": ["^VIX"], "date": pd.to_datetime(["2020-01-02"]), "close": [-1.0]}
    )
    with pytest.raises(pae.SchemaError):
        VOL_SCHEMA.validate(bad)


def test_normalize_vol_long_format():
    from ingest.vol import normalize_vol

    raw = pd.DataFrame(
        {
            "Open": [12.0, 13.0],
            "High": [12.5, 13.5],
            "Low": [11.0, 12.0],
            "Close": [12.3, 13.1],
            "Adj Close": [12.3, 13.1],
            "Volume": [0, 0],
        },
        index=pd.to_datetime(["2020-01-02", "2020-01-03"]),
    )
    out = normalize_vol(raw, "^VIX")
    assert list(out.columns) == ["series", "date", "close"]
    assert (out["series"] == "^VIX").all()
    assert out["close"].tolist() == [12.3, 13.1]
    assert str(out["date"].dtype) == "datetime64[ns]"
