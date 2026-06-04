"""H5: is upstream capex priced into downstream equity?

Capex growth (known at the SEC FILING date) vs downstream forward de-beta'd
returns over 1-2 quarters. Point-in-time on the filing date -- the forward window
opens strictly AFTER filed, and the de-beta betas use only data up to filed --
so this is a tradeability test, not look-ahead. Sample is small (~25 filings/
edge): effect sizes + bootstrap CIs + FDR, NO walk-forward.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analysis.fundamentals_leadlag import bootstrap_slope_ci, yoy_growth
from analysis.residualize import residual_for_spec
from analysis.significance import block_resample_one


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


def capex_growth_at_filed(fundamentals: pd.DataFrame, ticker: str) -> pd.Series:
    """Upstream capex YoY growth, re-indexed onto the filing date of each quarter."""
    sub = fundamentals.loc[
        fundamentals["ticker"] == ticker, ["period_end", "filed", "capex"]
    ].dropna()
    if sub.empty:
        return pd.Series(dtype=float)
    q = pd.to_datetime(sub["period_end"]).dt.to_period("Q")
    level = pd.Series(sub["capex"].to_numpy(float), index=q).sort_index()
    level = level[~level.index.duplicated(keep="last")]
    filed_by_q = pd.Series(pd.to_datetime(sub["filed"]).to_numpy(), index=q).sort_index()
    filed_by_q = filed_by_q[~filed_by_q.index.duplicated(keep="last")]
    growth = yoy_growth(level)
    filed_idx = pd.DatetimeIndex([filed_by_q.loc[qi] for qi in growth.index])
    return pd.Series(growth.to_numpy(), index=filed_idx).sort_index()


def _corr_slope(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return np.nan, np.nan
    corr = float(np.corrcoef(x, y)[0, 1])
    slope = float(np.polyfit(x, y, 1)[0])
    return corr, slope


def _aligned_forward(
    capex_growth: pd.Series,
    down_daily: pd.Series,
    factors: dict[str, pd.Series],
    sector: str | None,
    horizon: int,
) -> tuple[np.ndarray, np.ndarray]:
    xs, ys = [], []
    for filed, g in capex_growth.items():
        fwd = forward_excess_return(down_daily, factors, sector=sector, filed=filed, horizon_days=horizon)
        if np.isfinite(fwd):
            xs.append(float(g))
            ys.append(fwd)
    return np.asarray(xs), np.asarray(ys)


def horizon_selection_pvalue(
    capex_growth: pd.Series,
    down_daily: pd.Series,
    factors: dict[str, pd.Series],
    sector: str | None,
    *,
    horizons: tuple[int, ...],
    iters: int,
    seed: int,
) -> dict:
    """Best signed-corr horizon and selection-aware p-value over horizons."""
    per_h = {h: _aligned_forward(capex_growth, down_daily, factors, sector, h) for h in horizons}
    best_h, best_corr, best = None, -np.inf, None
    for h, (x, y) in per_h.items():
        c, s = _corr_slope(x, y)
        if np.isfinite(c) and c > best_corr:
            best_h, best_corr, best = h, c, (x, y, s)
    if best is None:
        return {
            "horizon": horizons[0],
            "corr": np.nan,
            "slope": np.nan,
            "p_selection": 1.0,
            "n_obs": 0,
        }
    x, _, slope = best
    rng = np.random.default_rng(seed)
    count = 0
    for _ in range(iters):
        null_max = -np.inf
        for xh, yh in per_h.values():
            if len(xh) < 3:
                continue
            xb = block_resample_one(xh, block=2, rng=rng)
            c, _ = _corr_slope(xb, yh)
            if np.isfinite(c):
                null_max = max(null_max, c)
        if null_max >= best_corr:
            count += 1
    return {
        "horizon": best_h,
        "corr": best_corr,
        "slope": slope,
        "p_selection": (count + 1) / (iters + 1),
        "n_obs": int(len(x)),
    }


def capex_price_edge(
    capex_growth: pd.Series,
    down_daily: pd.Series,
    factors: dict[str, pd.Series],
    *,
    sector: str | None,
    horizons: tuple[int, ...],
    iters: int,
    seed: int,
) -> dict:
    sel = horizon_selection_pvalue(
        capex_growth, down_daily, factors, sector, horizons=horizons, iters=iters, seed=seed
    )
    if sel["n_obs"] < 10:
        return {
            "horizon": sel["horizon"],
            "corr": float("nan"),
            "slope": float("nan"),
            "slope_lo": float("nan"),
            "slope_hi": float("nan"),
            "p_selection": 1.0,
            "contradicts_thesis": False,
            "n_obs": sel["n_obs"],
        }
    x, y = _aligned_forward(capex_growth, down_daily, factors, sector, sel["horizon"])
    lo, hi, slope = bootstrap_slope_ci(x, y, block=2, iters=iters, seed=seed)
    neg = any(
        _corr_slope(*_aligned_forward(capex_growth, down_daily, factors, sector, h))[0]
        < -abs(sel["corr"])
        for h in horizons
    )
    return {
        "horizon": int(sel["horizon"]),
        "corr": float(sel["corr"]),
        "slope": slope,
        "slope_lo": lo,
        "slope_hi": hi,
        "p_selection": sel["p_selection"],
        "contradicts_thesis": bool(slope < 0 or neg),
        "n_obs": int(sel["n_obs"]),
    }


def capex_price_edges(
    fundamentals: pd.DataFrame,
    returns: pd.DataFrame,
    factors: dict[str, pd.Series],
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    *,
    horizons: tuple[int, ...],
    iters: int,
    seed: int,
) -> pd.DataFrame:
    """Estimate H5 over cross-edges, with FDR over finite-slope edges."""
    import json as _json

    from analysis.leadlag import bh_fdr
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
        ut, dt = ticker_of(e.from_id), ticker_of(e.to_id)
        cg = capex_growth_at_filed(fundamentals, ut)
        if cg.empty or dt not in ret:
            continue
        sector = FACTOR_TICKERS.get(STAGE_SECTOR.get(stage.get(e.to_id), ""))
        sec_d = sector if sector in factors else None
        out = capex_price_edge(cg, ret[dt], factors, sector=sec_d, horizons=horizons, iters=iters, seed=seed)
        out.update({"left": e.from_id, "right": e.to_id})
        rows.append(out)
    df = pd.DataFrame(rows)
    if not df.empty:
        elig = df["slope"].notna()
        df["q_value"] = np.nan
        if elig.any():
            df.loc[elig, "q_value"] = bh_fdr(df.loc[elig, "p_selection"].to_numpy())
    return df
