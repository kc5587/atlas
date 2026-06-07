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


def _ticker_of(nodes: pd.DataFrame, node_id: str) -> str | None:
    row = nodes.loc[nodes["id"] == node_id]
    if row.empty:
        return None
    return json.loads(row["tickers"].iloc[0])[0]


def link_signal_panel(
    resid: pd.DataFrame,
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    *,
    min_months: int,
) -> pd.DataFrame:
    """Long panel [node, month, signal, fwd_target] for customer->supplier links.

    signal[S,t] = equal-weight mean of S's customers' residual return at t.
    fwd_target[S,t] = S's residual return at t+1.
    """
    rows = []
    for supplier in nodes["id"]:
        supplier_ticker = _ticker_of(nodes, supplier)
        if supplier_ticker is None or supplier_ticker not in resid.columns:
            continue
        customers = edges.loc[edges["from_id"] == supplier, "to_id"]
        customer_tickers = [
            ticker
            for ticker in (_ticker_of(nodes, customer) for customer in customers)
            if ticker and ticker in resid.columns
        ]
        if not customer_tickers:
            continue
        signal = resid[customer_tickers].mean(axis=1)
        target = resid[supplier_ticker].shift(-1)
        paired = pd.concat([signal.rename("signal"), target.rename("fwd_target")], axis=1).dropna()
        if len(paired) < min_months:
            continue
        rows.extend(
            {
                "node": supplier,
                "month": month,
                "signal": float(row["signal"]),
                "fwd_target": float(row["fwd_target"]),
            }
            for month, row in paired.iterrows()
        )
    return pd.DataFrame(rows, columns=["node", "month", "signal", "fwd_target"])
