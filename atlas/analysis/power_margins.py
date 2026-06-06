"""H9: does electricity cost compress cloud gross margins?"""
from __future__ import annotations

import pandas as pd


def sector_margin_delta(fundamentals: pd.DataFrame, *, names: list[str]) -> pd.Series:
    """Cross-sectional median quarter-over-quarter gross-margin change."""
    per_name = {}
    for ticker in names:
        sub = fundamentals.loc[
            fundamentals["ticker"] == ticker,
            ["period_end", "gross_margin"],
        ].dropna()
        if sub.empty:
            continue
        quarter = pd.to_datetime(sub["period_end"]).dt.to_period("Q")
        level = pd.Series(sub["gross_margin"].to_numpy(float), index=quarter).sort_index()
        level = level[~level.index.duplicated(keep="last")]
        delta = level.diff().dropna()
        if not delta.empty:
            per_name[ticker] = delta
    if not per_name:
        return pd.Series(dtype=float)
    return pd.concat(per_name, axis=1).median(axis=1).dropna()
