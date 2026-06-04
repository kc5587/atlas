"""H1: hardened quarterly capex -> downstream revenue lead/lag.

YoY-growth transform (stationarity) + cycle control (de-beta analog) + one-sided
lead search over [1,4] quarters + bootstrap slope CI. Sample is small (~20-40
quarters) so we report effect sizes + CIs, NOT walk-forward.
"""
from __future__ import annotations

import json as _json

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


def capex_revenue_edges(fundamentals: pd.DataFrame, nodes: pd.DataFrame,
                        edges: pd.DataFrame, *, iters: int, seed: int) -> pd.DataFrame:
    """Driver: per eligible edge, hardened capex->revenue stats. Quarterly lags 1-4.

    Cycle factor = leave-one-out cross-sectional mean of downstream revenue growth.
    """
    def series(ticker, col):
        sub = fundamentals.loc[fundamentals["ticker"] == ticker, ["period_end", col]].dropna()
        if sub.empty:
            return pd.Series(dtype=float)
        return pd.Series(sub[col].to_numpy(float),
                         index=pd.to_datetime(sub["period_end"])).sort_index()

    def ticker_of(node_id):
        row = nodes.loc[nodes["id"] == node_id]
        return _json.loads(row["tickers"].iloc[0])[0] if not row.empty else ""

    # revenue YoY growth per ticker (for the cycle factor)
    rev_growth = {}
    for t in fundamentals["ticker"].unique():
        g = yoy_growth(series(t, "revenue"))
        if not g.empty:
            rev_growth[t] = g

    rows = []
    for e in edges.itertuples():
        ut, dt = ticker_of(e.from_id), ticker_of(e.to_id)
        cg = yoy_growth(series(ut, "capex"))
        rg = rev_growth.get(dt)
        if cg.empty or rg is None:
            continue
        peers = [g for t, g in rev_growth.items() if t != dt]
        if not peers:
            continue
        cycle = pd.concat(peers, axis=1, join="outer", sort=True).mean(axis=1).dropna()
        out = capex_revenue_edge(cg, rg, cycle, lag_min=1, lag_max=4, iters=iters, seed=seed)
        out.update({"left": e.from_id, "right": e.to_id})
        rows.append(out)
    df = pd.DataFrame(rows)
    if not df.empty:
        from analysis.leadlag import bh_fdr
        df["q_value"] = bh_fdr(df["p_selection"].to_numpy())
        df["slope_lo"] = df["slope_ci"].apply(lambda c: c[0])
        df["slope_hi"] = df["slope_ci"].apply(lambda c: c[1])
        df = df.drop(columns=["slope_ci"])
    return df
