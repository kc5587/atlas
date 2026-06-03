from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import requests

from config import DATA_RAW, FRED_SERIES, PRICE_START
from ingest._base import atomic_write_parquet, with_retry
from ingest.schemas import MACRO_SCHEMA


# FRED's public CSV endpoint — no API key required.
FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def normalize_macro(raw: pd.DataFrame, series_id: str) -> pd.DataFrame:
    """Convert a single-column, date-indexed FRED frame into validated long format."""
    s = raw[series_id] if series_id in raw.columns else raw.iloc[:, 0]
    df = pd.DataFrame(
        {
            "series_id": series_id,
            "date": pd.to_datetime(s.index).tz_localize(None),
            "value": pd.to_numeric(s.values, errors="coerce"),
        }
    )
    df = df.dropna(subset=["value"]).reset_index(drop=True)
    df["value"] = df["value"].astype(float)
    return MACRO_SCHEMA.validate(df)


def _csv_to_indexed_frame(text: str, series_id: str) -> pd.DataFrame:
    """Parse a fredgraph CSV (DATE,<series>) into a date-indexed single-column frame.

    FRED encodes missing observations as '.'; convert those to NaN.
    """
    df = pd.read_csv(io.StringIO(text))
    if df.shape[1] < 2 or df.empty:
        raise RuntimeError(f"unexpected FRED CSV shape for {series_id}")
    date_col, val_col = df.columns[0], df.columns[1]
    df = df.rename(columns={val_col: series_id})
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.set_index(date_col)
    df[series_id] = pd.to_numeric(df[series_id].replace(".", pd.NA), errors="coerce")
    return df[[series_id]]


def fetch_macro(series_id: str, start: str = PRICE_START) -> pd.DataFrame:  # pragma: no cover
    def _dl() -> pd.DataFrame:
        resp = requests.get(
            FRED_CSV_URL, params={"id": series_id, "cosd": start}, timeout=60
        )
        resp.raise_for_status()
        frame = _csv_to_indexed_frame(resp.text, series_id)
        if frame.empty:
            raise RuntimeError(f"empty FRED download for {series_id}")
        return frame

    return normalize_macro(with_retry(_dl), series_id)


def _empty_macro_frame() -> pd.DataFrame:
    """Schema-correct, zero-row frame so dbt's macro parquet glob never matches nothing."""
    return pd.DataFrame(
        {
            "series_id": pd.Series([], dtype="object"),
            "date": pd.Series([], dtype="datetime64[ns]"),
            "value": pd.Series([], dtype="float64"),
        }
    )


def run() -> None:
    out_dir = Path(DATA_RAW) / "macro"
    wrote_any = False
    for series_id in FRED_SERIES:
        try:
            df = fetch_macro(series_id)
        except Exception as exc:  # noqa: BLE001 - tolerate a flaky FRED series, keep going
            print(f"macro: SKIP {series_id} ({type(exc).__name__}: {exc})")
            continue
        atomic_write_parquet(df, out_dir / f"{series_id}.parquet")
        wrote_any = True
        print(f"macro: wrote {len(df)} rows for {series_id}")
    if not wrote_any:
        # All series failed (e.g. FRED unreachable): write an empty fallback so the
        # downstream dbt model still builds instead of erroring on an empty glob.
        atomic_write_parquet(_empty_macro_frame(), out_dir / "_empty.parquet")
        print("macro: all series failed; wrote empty fallback parquet")


if __name__ == "__main__":
    run()
