import pandas as pd
import inspect

from ingest.prices import normalize_prices


def _raw_yf() -> pd.DataFrame:
    # Mimics yfinance single-ticker frame: DatetimeIndex + OHLCV columns.
    idx = pd.to_datetime(["2024-01-02", "2024-01-03"])
    return pd.DataFrame(
        {
            "Open": [1.0, 1.1],
            "High": [2.0, 2.1],
            "Low": [0.5, 0.6],
            "Close": [1.5, 1.6],
            "Adj Close": [1.4, 1.5],
            "Volume": [100, 200],
        },
        index=idx,
    )


def test_normalize_prices_long_format():
    out = normalize_prices(_raw_yf(), "NVDA")
    assert list(out.columns) == [
        "ticker", "date", "open", "high", "low", "close", "adj_close", "volume",
    ]
    assert out["ticker"].unique().tolist() == ["NVDA"]
    assert len(out) == 2
    assert out["volume"].dtype == "int64"


def test_normalize_prices_drops_all_nan_rows():
    raw = _raw_yf()
    raw.loc[raw.index[1], ["Open", "High", "Low", "Close", "Adj Close", "Volume"]] = None
    out = normalize_prices(raw, "NVDA")
    assert len(out) == 1


def test_run_default_ticker_list_includes_aux_tickers():
    import ingest.prices as p
    from config import AUX_TICKERS

    assert "QQQ" in AUX_TICKERS
    assert "AUX_TICKERS" in inspect.getsource(p.run)
