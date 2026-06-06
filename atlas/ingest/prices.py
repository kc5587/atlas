from __future__ import annotations

from pathlib import Path

import pandas as pd
import yfinance as yf

from config import DATA_RAW, PRICE_START, UNIVERSE
from ingest._base import atomic_write_parquet, with_retry
from ingest.schemas import PRICE_SCHEMA

_COLUMN_MAP = {
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Adj Close": "adj_close",
    "Volume": "volume",
}


def normalize_prices(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Convert a yfinance OHLCV frame into validated long format."""
    df = raw.rename(columns=_COLUMN_MAP).copy()
    df = df[[c for c in _COLUMN_MAP.values() if c in df.columns]]
    df = df.dropna(how="all")
    df.insert(0, "date", pd.to_datetime(df.index))
    df.insert(0, "ticker", ticker)
    df = df.reset_index(drop=True)
    df["volume"] = df["volume"].fillna(0).astype("int64")
    df["date"] = df["date"].dt.tz_localize(None)
    return PRICE_SCHEMA.validate(df)


def fetch_prices(ticker: str, start: str = PRICE_START) -> pd.DataFrame:  # pragma: no cover
    """Download one ticker's daily history (retried)."""
    def _dl() -> pd.DataFrame:
        raw = yf.download(ticker, start=start, auto_adjust=False, progress=False)
        if raw.empty:
            raise RuntimeError(f"empty download for {ticker}")
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        return raw

    return normalize_prices(with_retry(_dl), ticker)


def run(tickers: list[str] | None = None) -> None:  # pragma: no cover
    from config import AUX_TICKERS, FACTOR_TICKERS, POWER_NAMES

    tickers = tickers or (UNIVERSE + list(FACTOR_TICKERS.values()) + AUX_TICKERS + POWER_NAMES)
    out_dir = Path(DATA_RAW) / "prices"
    for t in tickers:
        df = fetch_prices(t)
        atomic_write_parquet(df, out_dir / f"{t}.parquet")
        print(f"prices: wrote {len(df)} rows for {t}")


if __name__ == "__main__":
    run()
