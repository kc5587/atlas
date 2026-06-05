"""H2: does an upstream capex surprise predict downstream forward drift?

Standardized, point-in-time capex surprise at the filing date vs downstream
forward de-beta'd returns, pooled across edges as an event study. Sample is
event-clustered, so inference uses block bootstrap rather than walk-forward.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analysis.capex_price import capex_growth_at_filed, forward_excess_return


def capex_surprise(fundamentals: pd.DataFrame, ticker: str, *, k: int = 4) -> pd.Series:
    """Standardized capex-growth surprise, indexed by filing date."""
    growth = capex_growth_at_filed(fundamentals, ticker)
    if len(growth) < k + 1:
        return pd.Series(dtype=float)
    prior = growth.shift(1)
    expected = prior.rolling(k).mean()
    sigma = prior.rolling(k).std()
    surprise = (growth - expected) / sigma.replace(0.0, np.nan)
    return surprise.dropna()


def pooled_events(
    fundamentals: pd.DataFrame,
    returns: pd.DataFrame,
    factors: dict[str, pd.Series],
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    *,
    horizon: int,
    k: int,
) -> pd.DataFrame:
    """Collect filing-date surprise events across cross-edges for one horizon."""
    import json as _json

    from config import FACTOR_TICKERS, STAGE_SECTOR

    ret = {
        t: g.set_index("date")["log_return"].sort_index()
        for t, g in returns.groupby("ticker")
    }
    stage = {r.id: r.stage for r in nodes.itertuples()}

    def ticker_of(node_id: str) -> str:
        row = nodes.loc[nodes["id"] == node_id]
        return _json.loads(row["tickers"].iloc[0])[0] if not row.empty else ""

    rows = []
    for e in edges.itertuples():
        upstream, downstream = ticker_of(e.from_id), ticker_of(e.to_id)
        surprise = capex_surprise(fundamentals, upstream, k=k)
        if surprise.empty or downstream not in ret:
            continue
        sector = FACTOR_TICKERS.get(STAGE_SECTOR.get(stage.get(e.to_id), ""))
        sector = sector if sector in factors else None
        for filed, value in surprise.items():
            if not np.isfinite(value):
                continue
            fwd = forward_excess_return(
                ret[downstream], factors, sector=sector, filed=filed, horizon_days=horizon
            )
            if np.isfinite(fwd):
                rows.append({"date": pd.Timestamp(filed), "surprise": float(value), "fwd": fwd})
    return (
        pd.DataFrame(rows, columns=["date", "surprise", "fwd"])
        .sort_values("date")
        .reset_index(drop=True)
    )
