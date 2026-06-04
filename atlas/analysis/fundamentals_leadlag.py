"""H1: hardened quarterly capex -> downstream revenue lead/lag.

YoY-growth transform (stationarity) + cycle control (de-beta analog) + one-sided
lead search over [1,4] quarters + bootstrap slope CI. Sample is small (~20-40
quarters) so we report effect sizes + CIs, NOT walk-forward.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analysis.significance import _corr_at_lag, _signed_peak, selection_aware


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


def bootstrap_slope_ci(x: np.ndarray, y: np.ndarray, *, block: int, iters: int,
                       seed: int, ci: float = 0.90) -> tuple[float, float, float]:
    """Block-bootstrap CI for the OLS slope of y on x (moving blocks of pairs)."""
    x = np.asarray(x, float); y = np.asarray(y, float)
    n = len(x)
    def slope(xs, ys):
        A = np.column_stack([np.ones(len(xs)), xs])
        b, *_ = np.linalg.lstsq(A, ys, rcond=None)
        return b[1]
    point = slope(x, y)
    rng = np.random.default_rng(seed)
    nblocks = int(np.ceil(n / block))
    draws = []
    for _ in range(iters):
        starts = rng.integers(0, max(1, n - block + 1), size=nblocks)
        idx = np.concatenate([np.arange(s, s + block) for s in starts])[:n]
        draws.append(slope(x[idx], y[idx]))
    lo = float(np.percentile(draws, (1 - ci) / 2 * 100))
    hi = float(np.percentile(draws, (1 + ci) / 2 * 100))
    return lo, hi, float(point)


def capex_revenue_edge(capex_growth: pd.Series, rev_growth: pd.Series,
                       cycle_growth: pd.Series, *, lag_min: int, lag_max: int,
                       iters: int, seed: int) -> dict:
    """One edge: capex growth (lead) vs cycle-controlled revenue growth."""
    rev_resid = cycle_control(rev_growth, cycle_growth)
    paired = pd.concat([capex_growth.rename("x"), rev_resid.rename("y")],
                       axis=1, join="inner").dropna()
    if len(paired) < lag_max + 5:
        return {"lag": 0, "corr": float("nan"), "slope": float("nan"),
                "slope_ci": [float("nan"), float("nan")], "p_selection": 1.0,
                "contradicts_thesis": False, "n_quarters": int(len(paired))}
    x, y = paired["x"].to_numpy(), paired["y"].to_numpy()
    lag, corr = _signed_peak(x, y, lag_min, lag_max)
    sig = selection_aware(x, y, lag_min=lag_min, lag_max=lag_max, iters=iters,
                          seed=seed, block=2)
    # align at the chosen lag for slope
    xs, ys = x[: len(x) - lag], y[lag:]
    lo, hi, slope = bootstrap_slope_ci(xs, ys, block=2, iters=iters, seed=seed)
    return {
        "lag": int(lag), "corr": float(corr), "slope": slope, "slope_ci": [lo, hi],
        "p_selection": sig["p_selection"], "contradicts_thesis": sig["contradicts_thesis"],
        "n_quarters": int(len(paired)),
    }
