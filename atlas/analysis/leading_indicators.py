"""H8: do chip-cycle leading indicators lead chip-maker revenue?"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analysis.fundamentals_leadlag import bootstrap_slope_ci
from analysis.significance import block_resample_one


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


def _corr_slope(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return np.nan, np.nan
    return float(np.corrcoef(x, y)[0, 1]), float(np.polyfit(x, y, 1)[0])


def _aligned_lead(indicator_q: pd.Series, revenue_q: pd.Series, lead: int) -> tuple[np.ndarray, np.ndarray]:
    """Indicator at quarter t vs revenue YoY at quarter t + lead."""
    shifted = indicator_q.copy()
    shifted.index = shifted.index + lead
    paired = pd.concat(
        [shifted.rename("x"), revenue_q.rename("y")],
        axis=1,
        join="inner",
    ).dropna()
    return paired["x"].to_numpy(), paired["y"].to_numpy()


def indicator_revenue_lead(
    indicator_q: pd.Series,
    revenue_q: pd.Series,
    *,
    leads: tuple[int, ...],
    iters: int,
    seed: int,
) -> dict:
    """Best one-sided lead of a quarterly indicator over revenue YoY."""
    per_lead = {lead: _aligned_lead(indicator_q, revenue_q, lead) for lead in leads}
    best_lead = None
    best_corr = -np.inf
    best = None
    for lead, (x, y) in per_lead.items():
        corr, slope = _corr_slope(x, y)
        if np.isfinite(corr) and corr > best_corr:
            best_lead = lead
            best_corr = corr
            best = (x, y, slope)
    if best is None:
        return {
            "best_lead": leads[0],
            "corr": np.nan,
            "slope": np.nan,
            "slope_lo": np.nan,
            "slope_hi": np.nan,
            "p_selection": 1.0,
            "n_obs": 0,
            "contradicts_thesis": False,
        }

    x, y, slope = best
    rng = np.random.default_rng(seed)
    count = 0
    for _ in range(iters):
        null_max = -np.inf
        for x_lead, y_lead in per_lead.values():
            if len(x_lead) < 3:
                continue
            xb = block_resample_one(x_lead, block=2, rng=rng)
            corr, _ = _corr_slope(xb, y_lead)
            if np.isfinite(corr):
                null_max = max(null_max, corr)
        if null_max >= best_corr:
            count += 1
    lo, hi, _ = bootstrap_slope_ci(x, y, block=2, iters=iters, seed=seed)
    return {
        "best_lead": int(best_lead),
        "corr": float(best_corr),
        "slope": float(slope),
        "slope_lo": lo,
        "slope_hi": hi,
        "p_selection": (count + 1) / (iters + 1),
        "n_obs": int(len(x)),
        "contradicts_thesis": bool(slope < 0),
    }
