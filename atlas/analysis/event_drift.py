"""H2: does an upstream capex surprise predict downstream forward drift?

Standardized, point-in-time capex surprise at the filing date vs downstream
forward de-beta'd returns, pooled across edges as an event study. Sample is
event-clustered, so inference uses block bootstrap rather than walk-forward.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analysis.capex_price import capex_growth_at_filed, forward_excess_return
from analysis.fundamentals_leadlag import bootstrap_slope_ci
from analysis.significance import block_resample_one


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


def _ols_slope_corr(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return np.nan, np.nan
    slope = float(np.polyfit(x, y, 1)[0])
    corr = float(np.corrcoef(x, y)[0, 1])
    return slope, corr


def event_drift(
    fundamentals: pd.DataFrame,
    returns: pd.DataFrame,
    factors: dict[str, pd.Series],
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    *,
    horizons: tuple[int, ...],
    iters: int,
    seed: int,
    k: int = 4,
) -> dict:
    """Pooled capex-surprise -> downstream forward drift over selected horizons."""
    per_h = {
        h: pooled_events(fundamentals, returns, factors, nodes, edges, horizon=h, k=k)
        for h in horizons
    }
    best_h, best_slope, best_corr = None, 0.0, -np.inf
    for h, events in per_h.items():
        if len(events) < 10:
            continue
        slope, corr = _ols_slope_corr(events["surprise"].to_numpy(), events["fwd"].to_numpy())
        if np.isfinite(corr) and corr > best_corr:
            best_h, best_slope, best_corr = h, slope, corr
    if best_h is None:
        return {
            "horizon": horizons[0],
            "slope": np.nan,
            "slope_lo": np.nan,
            "slope_hi": np.nan,
            "p_selection": 1.0,
            "n_events": 0,
            "pos_drift": np.nan,
            "neg_drift": np.nan,
            "contradicts_thesis": False,
        }
    events = per_h[best_h]
    x = events["surprise"].to_numpy()
    y = events["fwd"].to_numpy()
    rng = np.random.default_rng(seed)
    count = 0
    for _ in range(iters):
        null_max = -np.inf
        for e2 in per_h.values():
            if len(e2) < 10:
                continue
            xb = block_resample_one(e2["surprise"].to_numpy(), block=8, rng=rng)
            _, corr = _ols_slope_corr(xb, e2["fwd"].to_numpy())
            if np.isfinite(corr):
                null_max = max(null_max, corr)
        if null_max >= best_corr:
            count += 1
    lo, hi, _ = bootstrap_slope_ci(x, y, block=8, iters=iters, seed=seed)
    pos = float(np.mean(y[x > 0])) if (x > 0).any() else np.nan
    neg = float(np.mean(y[x < 0])) if (x < 0).any() else np.nan
    return {
        "horizon": int(best_h),
        "slope": float(best_slope),
        "slope_lo": lo,
        "slope_hi": hi,
        "p_selection": (count + 1) / (iters + 1),
        "n_events": int(len(events)),
        "pos_drift": pos,
        "neg_drift": neg,
        "contradicts_thesis": bool(best_slope < 0),
    }
