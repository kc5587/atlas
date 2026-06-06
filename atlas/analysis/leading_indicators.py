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
