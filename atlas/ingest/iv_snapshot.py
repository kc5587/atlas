"""Collector B: daily single-name option-chain snapshot into an accumulating panel."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from config import DATA_RAW, UNIVERSE
from ingest._base import atomic_write_parquet
from ingest.schemas import IV_SNAPSHOT_SCHEMA


def atm_iv(calls: pd.DataFrame, *, spot: float) -> float:
    """ATM implied vol = IV at the strike nearest spot."""
    if calls.empty or "impliedVolatility" not in calls:
        return float("nan")
    idx = (calls["strike"] - spot).abs().idxmin()
    return float(calls.loc[idx, "impliedVolatility"])


def put_call_oi_ratio(calls: pd.DataFrame, puts: pd.DataFrame) -> float:
    call_oi = float(calls["openInterest"].sum()) if not calls.empty else 0.0
    put_oi = float(puts["openInterest"].sum()) if not puts.empty else 0.0
    return put_oi / call_oi if call_oi > 0 else float("nan")


def risk_reversal_skew(calls: pd.DataFrame, puts: pd.DataFrame, *, spot: float) -> float:
    """OTM put IV minus OTM call IV, using +/-10% moneyness as a 25-delta proxy."""
    if calls.empty or puts.empty:
        return float("nan")
    put_idx = (puts["strike"] - spot * 0.9).abs().idxmin()
    call_idx = (calls["strike"] - spot * 1.1).abs().idxmin()
    return float(puts.loc[put_idx, "impliedVolatility"] - calls.loc[call_idx, "impliedVolatility"])


def term_slope(near_atm: float, far_atm: float) -> float:
    """Far-minus-near ATM IV."""
    if not np.isfinite(near_atm) or not np.isfinite(far_atm):
        return float("nan")
    return float(far_atm - near_atm)


def merge_panel(prior: pd.DataFrame, today: pd.DataFrame) -> pd.DataFrame:
    """Append today's rows, keeping the latest row per ticker/date."""
    cols = list(IV_SNAPSHOT_SCHEMA.columns)
    combined = pd.concat([prior[cols], today[cols]], ignore_index=True)
    combined = combined.drop_duplicates(subset=["ticker", "date"], keep="last")
    combined = combined.sort_values(["ticker", "date"]).reset_index(drop=True)
    return IV_SNAPSHOT_SCHEMA.validate(combined)


def snapshot_one(ticker: str, *, asof: pd.Timestamp) -> dict | None:  # pragma: no cover
    """Compute today's IV features for one ticker from the live yfinance chain."""
    import yfinance as yf

    tk = yf.Ticker(ticker)
    expiries = list(tk.options or [])
    if not expiries:
        return None
    spot = float(tk.fast_info.get("last_price") or tk.history(period="1d")["Close"].iloc[-1])
    near = tk.option_chain(expiries[0])
    far = tk.option_chain(expiries[-1])
    near_atm = atm_iv(near.calls, spot=spot)
    far_atm = atm_iv(far.calls, spot=spot)
    return {
        "ticker": ticker,
        "date": pd.Timestamp(asof.date()),
        "atm_iv_30d": near_atm,
        "skew_25d": risk_reversal_skew(near.calls, near.puts, spot=spot),
        "term_slope": term_slope(near_atm, far_atm),
        "put_call_oi": put_call_oi_ratio(near.calls, near.puts),
    }


def _load_prior_panel(path: Path) -> pd.DataFrame:  # pragma: no cover
    if path.exists():
        return IV_SNAPSHOT_SCHEMA.validate(pd.read_parquet(path))
    return IV_SNAPSHOT_SCHEMA.validate(
        pd.DataFrame(
            {
                col: pd.Series(
                    [],
                    dtype="datetime64[ns]" if col == "date" else ("object" if col == "ticker" else "float64"),
                )
                for col in IV_SNAPSHOT_SCHEMA.columns
            }
        )
    )


def run() -> None:  # pragma: no cover
    asof = pd.Timestamp(datetime.now(timezone.utc))
    panel_path = Path(DATA_RAW) / "iv_snapshots" / "panel.parquet"
    rows = []
    for ticker in UNIVERSE:
        try:
            row = snapshot_one(ticker, asof=asof)
        except Exception as exc:  # noqa: BLE001 - tolerate one flaky chain
            print(f"iv_snapshot: SKIP {ticker} ({type(exc).__name__}: {exc})")
            continue
        if row is not None:
            rows.append(row)
    if not rows:
        print("iv_snapshot: no chains fetched; leaving panel unchanged")
        return
    today = IV_SNAPSHOT_SCHEMA.validate(pd.DataFrame(rows))
    merged = merge_panel(_load_prior_panel(panel_path), today)
    atomic_write_parquet(merged, panel_path)
    print(f"iv_snapshot: panel now {len(merged)} rows ({today['ticker'].nunique()} names today)")


if __name__ == "__main__":
    run()
