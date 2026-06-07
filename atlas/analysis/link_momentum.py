"""H15: customer -> supplier monthly link momentum (Cohen-Frazzini).

A node's customers' prior-month idiosyncratic (M2-residual) return predicts the
node's forward idiosyncratic return. Pure functions: DataFrame in, dict/DataFrame
out. Uses the full graph because this is returns-based, not fundamentals-based.
"""
from __future__ import annotations

import json

import pandas as pd

from analysis.residualize import residual_for_spec
from config import FACTOR_TICKERS, STAGE_SECTOR

FACTOR_ETFS = ("SPY", "SOXX", "IGV")


def monthly_returns(returns: pd.DataFrame) -> pd.DataFrame:
    """Daily log returns -> wide month-end DataFrame, columns=tickers."""
    df = returns.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["month"] = df["date"].dt.to_period("M").dt.to_timestamp("M")
    return df.groupby(["month", "ticker"])["log_return"].sum().unstack("ticker").sort_index()


def _sector_etf(stage: str) -> str | None:
    return FACTOR_TICKERS.get(STAGE_SECTOR.get(stage, ""))


def residual_monthly_returns(monthly: pd.DataFrame, nodes: pd.DataFrame) -> pd.DataFrame:
    """M2-residual monthly return per node ticker, with betas fit on full sample."""
    factors = {etf: monthly[etf] for etf in FACTOR_ETFS if etf in monthly.columns}
    stage_of = {}
    for row in nodes.itertuples():
        for ticker in json.loads(row.tickers):
            stage_of[ticker] = row.stage

    out = {}
    for ticker in monthly.columns:
        if ticker in FACTOR_ETFS or ticker not in stage_of:
            continue
        sector = _sector_etf(stage_of[ticker])
        sector = sector if sector and sector in factors else None
        out[ticker] = residual_for_spec(
            monthly[ticker],
            factors,
            sector=sector,
            spec="M2",
            train_index=monthly.index,
        )
    return pd.DataFrame(out)
