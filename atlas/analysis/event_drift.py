"""H2: does an upstream capex surprise predict downstream forward drift?

Standardized, point-in-time capex surprise at the filing date vs downstream
forward de-beta'd returns, pooled across edges as an event study. Sample is
event-clustered, so inference uses block bootstrap rather than walk-forward.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analysis.capex_price import capex_growth_at_filed


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
