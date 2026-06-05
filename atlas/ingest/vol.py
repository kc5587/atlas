from __future__ import annotations

from pathlib import Path

import pandas as pd
import yfinance as yf

from config import DATA_RAW, PRICE_START, VOL_FRED_FALLBACK, VOL_SERIES
from ingest._base import atomic_write_parquet, with_retry
from ingest.macro import fetch_macro
from ingest.schemas import VOL_SCHEMA


def normalize_vol(raw: pd.DataFrame, series: str) -> pd.DataFrame:
    """Convert a yfinance index OHLC frame into validated long format."""
    close = raw["Close"] if "Close" in raw.columns else raw.iloc[:, 0]
    df = pd.DataFrame(
        {
            "series": series,
            "date": pd.to_datetime(close.index).tz_localize(None),
            "close": pd.to_numeric(close.to_numpy().ravel(), errors="coerce"),
        }
    )
    df = df.dropna(subset=["close"]).reset_index(drop=True)
    df["date"] = df["date"].astype("datetime64[ns]")
    df["close"] = df["close"].astype(float)
    return VOL_SCHEMA.validate(df)


def _from_fred(series: str) -> pd.DataFrame:  # pragma: no cover - network
    """Fallback: pull the FRED equivalent and relabel to the ^-series id."""
    fred_id = VOL_FRED_FALLBACK[series]
    macro = fetch_macro(fred_id)
    return VOL_SCHEMA.validate(
        macro.rename(columns={"value": "close"})[["date", "close"]]
        .assign(series=series)[["series", "date", "close"]]
    )


def fetch_vol(series: str, start: str = PRICE_START) -> pd.DataFrame:  # pragma: no cover
    """Download one vol index's history; fall back to FRED for ^VIX/^VXN."""
    def _dl() -> pd.DataFrame:
        raw = yf.download(series, start=start, auto_adjust=False, progress=False)
        if raw.empty:
            raise RuntimeError(f"empty download for {series}")
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        return normalize_vol(raw, series)

    try:
        return with_retry(_dl)
    except Exception:
        if series in VOL_FRED_FALLBACK:
            return _from_fred(series)
        raise


def run() -> None:  # pragma: no cover - network
    out_dir = Path(DATA_RAW) / "vol"
    wrote_any = False
    for series in VOL_SERIES:
        try:
            df = fetch_vol(series)
        except Exception as exc:  # noqa: BLE001 - tolerate a flaky series
            print(f"vol: SKIP {series} ({type(exc).__name__}: {exc})")
            continue
        atomic_write_parquet(df, out_dir / f"{series.lstrip('^')}.parquet")
        wrote_any = True
        print(f"vol: wrote {len(df)} rows for {series}")
    if not wrote_any:
        empty = VOL_SCHEMA.validate(
            pd.DataFrame(
                {
                    "series": pd.Series([], dtype="object"),
                    "date": pd.Series([], dtype="datetime64[ns]"),
                    "close": pd.Series([], dtype="float64"),
                }
            )
        )
        atomic_write_parquet(empty, out_dir / "_empty.parquet")
        print("vol: all series failed; wrote empty fallback parquet")


if __name__ == "__main__":
    run()
