"""H8: do chip-cycle leading indicators lead chip-maker revenue?"""
from __future__ import annotations

import numpy as np
import pandas as pd


def indicator_yoy(level: pd.Series, *, pub_lag_months: int) -> pd.Series:
    """Year-over-year log growth, shifted forward for point-in-time availability."""
    s = level.sort_index().astype(float)
    g = (np.log(s) - np.log(s.shift(12))).dropna()
    if pub_lag_months:
        g = g.shift(pub_lag_months).dropna()
    return g


def sector_revenue_yoy(fundamentals: pd.DataFrame, *, names: list[str]) -> pd.Series:
    """Cross-sectional median YoY revenue growth across names by calendar quarter."""
    per_name = {}
    for ticker in names:
        sub = fundamentals.loc[
            fundamentals["ticker"] == ticker,
            ["period_end", "revenue"],
        ].dropna()
        if sub.empty:
            continue
        q = pd.to_datetime(sub["period_end"]).dt.to_period("Q")
        level = pd.Series(sub["revenue"].to_numpy(float), index=q).sort_index()
        level = level[~level.index.duplicated(keep="last")]
        growth = (np.log(level) - np.log(level.shift(4))).dropna()
        if not growth.empty:
            per_name[ticker] = growth
    if not per_name:
        return pd.Series(dtype=float)
    return pd.concat(per_name, axis=1).median(axis=1).dropna()
