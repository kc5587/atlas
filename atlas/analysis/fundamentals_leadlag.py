"""H1: hardened quarterly capex -> downstream revenue lead/lag.

YoY-growth transform (stationarity) + cycle control (de-beta analog) + one-sided
lead search over [1,4] quarters + bootstrap slope CI. Sample is small (~20-40
quarters) so we report effect sizes + CIs, NOT walk-forward.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def yoy_growth(level: pd.Series) -> pd.Series:
    """Year-over-year log growth (4-quarter difference); removes seasonality."""
    s = level.sort_index().astype(float)
    g = np.log(s) - np.log(s.shift(4))
    return g.dropna()


def cycle_control(target_growth: pd.Series, cycle_growth: pd.Series) -> pd.Series:
    """Residual of target on [const, cycle] — the fundamental de-beta analog."""
    df = pd.concat([target_growth.rename("y"), cycle_growth.rename("c")],
                   axis=1, join="inner").dropna()
    if len(df) < 3:
        return pd.Series(dtype=float)
    A = np.column_stack([np.ones(len(df)), df["c"].to_numpy()])
    beta, *_ = np.linalg.lstsq(A, df["y"].to_numpy(), rcond=None)
    return pd.Series(df["y"].to_numpy() - A @ beta, index=df.index)
