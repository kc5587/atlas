"""H6: variance risk premium + implied-vol information content."""
from __future__ import annotations

import numpy as np
import pandas as pd

from analysis.oos import walk_forward_folds
from analysis.significance import auto_block_length


def realized_var_annualized(returns: np.ndarray) -> float:
    """Annualized realized variance from daily log returns."""
    r = np.asarray(returns, dtype=float)
    if len(r) < 2:
        return float("nan")
    return float(252.0 * np.mean(r**2))


def vrp_series(
    implied_vol_pts: pd.Series,
    underlying_returns: pd.Series,
    *,
    horizon: int,
) -> pd.Series:
    """Per-day VRP = (IV/100)^2 - realized variance over next horizon days."""
    iv = implied_vol_pts.sort_index().astype(float)
    r = underlying_returns.sort_index().astype(float)
    common = iv.index.intersection(r.index)
    iv = iv.loc[common]
    r = r.loc[common]
    vals = {}
    rvals = r.to_numpy()
    for i, t in enumerate(iv.index):
        window = rvals[i + 1: i + 1 + horizon]
        if len(window) < max(5, horizon // 2):
            continue
        vals[t] = (iv.iloc[i] / 100.0) ** 2 - realized_var_annualized(window)
    return pd.Series(vals).sort_index()


def mean_block_ci(
    x: np.ndarray,
    *,
    iters: int,
    seed: int,
    ci: float = 0.90,
) -> tuple[float, float, float]:
    """Stationary-block-bootstrap CI for the mean of an autocorrelated series."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 2:
        return float("nan"), float("nan"), float("nan")
    block = auto_block_length(x)
    rng = np.random.default_rng(seed)
    nblocks = int(np.ceil(n / block))
    draws = []
    for _ in range(iters):
        starts = rng.integers(0, max(1, n - block + 1), size=nblocks)
        idx = np.concatenate([np.arange(s, s + block) for s in starts])[:n]
        draws.append(float(np.mean(x[idx])))
    lo = float(np.percentile(draws, (1 - ci) / 2 * 100))
    hi = float(np.percentile(draws, (1 + ci) / 2 * 100))
    return lo, hi, float(np.mean(x))


def _ols_fit_predict(x_tr: np.ndarray, y_tr: np.ndarray, x_te: np.ndarray) -> np.ndarray:
    A = np.column_stack([np.ones(len(x_tr)), x_tr])
    beta, *_ = np.linalg.lstsq(A, y_tr, rcond=None)
    return np.column_stack([np.ones(len(x_te)), x_te]) @ beta


def _oos_sse(features_tr, y_tr, features_te, y_te) -> float:
    pred = _ols_fit_predict(features_tr, y_tr, features_te)
    return float(np.sum((y_te - pred) ** 2))


def incremental_oos_r2(
    *,
    iv: pd.Series,
    fwd_rv: pd.Series,
    lag_rv: pd.Series,
    test_days: int,
    step_days: int,
    init_train_frac: float,
) -> float:
    """OOS R2 improvement of (IV + lagged RV) vs lagged RV at forecasting fwd RV."""
    df = pd.concat([iv.rename("iv"), fwd_rv.rename("y"), lag_rv.rename("lag")], axis=1)
    df = df.dropna()
    if len(df) < 4 * test_days:
        return float("nan")
    folds = walk_forward_folds(
        df.index,
        test_days=test_days,
        step_days=step_days,
        init_train_frac=init_train_frac,
        embargo=0,
    )
    sse_full, sse_base = 0.0, 0.0
    for tr_idx, te_idx in folds:
        tr, te = df.loc[tr_idx], df.loc[te_idx]
        y_tr, y_te = tr["y"].to_numpy(), te["y"].to_numpy()
        sse_base += _oos_sse(tr[["lag"]].to_numpy(), y_tr, te[["lag"]].to_numpy(), y_te)
        sse_full += _oos_sse(
            tr[["lag", "iv"]].to_numpy(),
            y_tr,
            te[["lag", "iv"]].to_numpy(),
            y_te,
        )
    if sse_base == 0:
        return float("nan")
    return float(1.0 - sse_full / sse_base)


def _forward_rv_series(returns: pd.Series, horizon: int) -> pd.Series:
    r = returns.sort_index()
    vals = {}
    rvals = r.to_numpy()
    for i, t in enumerate(r.index):
        window = rvals[i + 1: i + 1 + horizon]
        if len(window) >= max(5, horizon // 2):
            vals[t] = realized_var_annualized(window)
    return pd.Series(vals).sort_index()


def vol_premium_table(
    vol: pd.DataFrame,
    returns: pd.DataFrame,
    *,
    pairs: tuple[tuple[str, str], ...],
    horizon: int,
    iters: int,
    seed: int,
) -> pd.DataFrame:
    """One row per implied/underlying pair: VRP mean+CI and IV information content."""
    iv_by = {s: g.set_index("date")["close"].sort_index() for s, g in vol.groupby("series")}
    ret_by = {
        t: g.set_index("date")["log_return"].sort_index()
        for t, g in returns.groupby("ticker")
    }
    rows = []
    for implied, under in pairs:
        if implied not in iv_by or under not in ret_by:
            continue
        iv = iv_by[implied]
        r = ret_by[under]
        vrp = vrp_series(iv, r, horizon=horizon)
        if vrp.empty:
            continue
        lo, hi, mean = mean_block_ci(vrp.to_numpy(), iters=iters, seed=seed)
        fwd_rv = _forward_rv_series(r, horizon).reindex(iv.index).dropna()
        aligned_iv = iv.reindex(fwd_rv.index)
        r2 = incremental_oos_r2(
            iv=aligned_iv,
            fwd_rv=fwd_rv,
            lag_rv=fwd_rv.shift(horizon),
            test_days=252,
            step_days=252,
            init_train_frac=0.5,
        )
        rows.append(
            {
                "pair": f"{implied}~{under}",
                "implied": implied,
                "underlying": under,
                "mean_vrp": mean,
                "vrp_lo": lo,
                "vrp_hi": hi,
                "incremental_oos_r2": r2,
                "n_obs": int(len(vrp)),
            }
        )
    return pd.DataFrame(rows)
