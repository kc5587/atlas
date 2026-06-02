import pandas as pd
import pandera.errors
import pytest

from ingest.schemas import MACRO_SCHEMA, PRICE_SCHEMA


def _valid_prices() -> pd.DataFrame:
    return pd.DataFrame({
        "ticker": ["NVDA"],
        "date": pd.to_datetime(["2024-01-02"]),
        "open": [1.0], "high": [2.0], "low": [0.5],
        "close": [1.5], "adj_close": [1.5], "volume": [100],
    })


def test_price_schema_accepts_valid():
    PRICE_SCHEMA.validate(_valid_prices())


def test_price_schema_rejects_negative_close():
    bad = _valid_prices()
    bad.loc[0, "close"] = -1.0
    with pytest.raises(pandera.errors.SchemaError):
        PRICE_SCHEMA.validate(bad)


def test_price_schema_rejects_null_close():
    bad = _valid_prices()
    bad.loc[0, "close"] = None
    with pytest.raises(pandera.errors.SchemaError):
        PRICE_SCHEMA.validate(bad)


def test_macro_schema_accepts_valid():
    df = pd.DataFrame({
        "series_id": ["DFF"],
        "date": pd.to_datetime(["2024-01-01"]),
        "value": [5.33],
    })
    MACRO_SCHEMA.validate(df)
