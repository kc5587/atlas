"""H5: is upstream capex priced into downstream equity?

Capex growth (known at the SEC FILING date) vs downstream forward de-beta'd
returns over 1-2 quarters. Point-in-time on the filing date -- the forward window
opens strictly AFTER filed, and the de-beta betas use only data up to filed --
so this is a tradeability test, not look-ahead. Sample is small (~25 filings/
edge): effect sizes + bootstrap CIs + FDR, NO walk-forward.
"""
from __future__ import annotations

import pandas as pd

from analysis.residualize import residual_for_spec


def forward_excess_return(
    asset_daily: pd.Series,
    factors: dict[str, pd.Series],
    *,
    sector: str | None,
    filed: pd.Timestamp,
    horizon_days: int,
) -> float:
    """Sum of D's M2 residual daily returns over (filed, filed+horizon_days]."""
    filed = pd.Timestamp(filed)
    train = asset_daily.index[asset_daily.index <= filed]
    if len(train) < 60:
        return float("nan")
    resid = residual_for_spec(asset_daily, factors, sector=sector, spec="M2", train_index=train)
    fwd = resid[resid.index > filed]
    if fwd.empty:
        return float("nan")
    window = fwd.iloc[:horizon_days]
    if len(window) < max(5, horizon_days // 2):
        return float("nan")
    return float(window.sum())
