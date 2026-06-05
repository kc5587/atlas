"""H7: vol term-structure slope as a forward-return timer."""
from __future__ import annotations

import numpy as np
import pandas as pd

from analysis.fundamentals_leadlag import bootstrap_slope_ci
from analysis.oos import walk_forward_folds
from analysis.significance import auto_block_length, block_resample_one


def termstructure_slope(vix: pd.Series, vix3m: pd.Series) -> pd.Series:
    """VIX / VIX3M ratio on shared dates."""
    df = pd.concat([vix.rename("a"), vix3m.rename("b")], axis=1, join="inner").dropna()
    df = df[df["b"] > 0]
    return (df["a"] / df["b"]).sort_index()


def aligned_forward(
    slope: pd.Series,
    log_return: pd.Series,
    *,
    horizon: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Pair s_t with summed forward log return over (t, t+horizon]."""
    s = slope.sort_index()
    r = log_return.sort_index()
    common = s.index.intersection(r.index)
    s = s.loc[common]
    rvals = r.loc[common].to_numpy()
    xs, ys = [], []
    for i, _ in enumerate(s.index):
        window = rvals[i + 1: i + 1 + horizon]
        if len(window) < max(5, horizon // 2):
            continue
        xs.append(float(s.iloc[i]))
        ys.append(float(np.sum(window)))
    return np.asarray(xs), np.asarray(ys)


def _corr_slope(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return np.nan, np.nan
    return float(np.corrcoef(x, y)[0, 1]), float(np.polyfit(x, y, 1)[0])


def selection_pvalue_one_series(x: np.ndarray, y: np.ndarray, *, iters: int, seed: int) -> float:
    """One-sided positive p-value via single-series block resample of x."""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    obs, _ = _corr_slope(x, y)
    if not np.isfinite(obs):
        return 1.0
    if obs < 0.10:
        return 0.50
    block = auto_block_length(x)
    rng = np.random.default_rng(seed)
    count = 0
    for _ in range(iters):
        xb = block_resample_one(x, block=block, rng=rng)
        c, _ = _corr_slope(xb, y)
        if np.isfinite(c) and c >= obs:
            count += 1
    return (count + 1) / (iters + 1)


def oos_sign_rate(
    slope: pd.Series,
    log_return: pd.Series,
    *,
    horizon: int,
    test_days: int,
    step_days: int,
    init_train_frac: float,
) -> float:
    """Anchored walk-forward fraction whose test slope matches train slope sign."""
    s = slope.sort_index()
    r = log_return.sort_index()
    common = s.index.intersection(r.index)
    paired = pd.concat([s.loc[common].rename("s"), r.loc[common].rename("r")], axis=1).dropna()
    folds = walk_forward_folds(
        paired.index,
        test_days=test_days,
        step_days=step_days,
        init_train_frac=init_train_frac,
        embargo=horizon,
    )
    signs = []
    for tr_idx, te_idx in folds:
        xtr, ytr = aligned_forward(paired.loc[tr_idx, "s"], paired.loc[tr_idx, "r"], horizon=horizon)
        xte, yte = aligned_forward(paired.loc[te_idx, "s"], paired.loc[te_idx, "r"], horizon=horizon)
        _, train_slope = _corr_slope(xtr, ytr)
        _, test_slope = _corr_slope(xte, yte)
        if np.isfinite(train_slope) and np.isfinite(test_slope) and train_slope != 0:
            signs.append(np.sign(train_slope) == np.sign(test_slope))
    return float(np.mean(signs)) if signs else 0.0


def vol_termstructure_table(
    vol: pd.DataFrame,
    returns: pd.DataFrame,
    *,
    predictor: tuple[str, str],
    targets: tuple[str, ...],
    horizons: tuple[int, ...],
    iters: int,
    seed: int,
) -> pd.DataFrame:
    """One row per target/horizon, with family FDR over eligible cells."""
    from analysis.leadlag import bh_fdr

    iv_by = {s: g.set_index("date")["close"].sort_index() for s, g in vol.groupby("series")}
    ret_by = {
        t: g.set_index("date")["log_return"].sort_index()
        for t, g in returns.groupby("ticker")
    }
    front, back = predictor
    if front not in iv_by or back not in iv_by:
        return pd.DataFrame()
    slope = termstructure_slope(iv_by[front], iv_by[back])

    rows = []
    for target in targets:
        if target not in ret_by:
            continue
        r = ret_by[target]
        for horizon in horizons:
            x, y = aligned_forward(slope, r, horizon=horizon)
            corr, coef = _corr_slope(x, y)
            if not np.isfinite(corr) or len(x) < 10:
                rows.append(
                    {
                        "target": target,
                        "horizon": horizon,
                        "corr": np.nan,
                        "slope": np.nan,
                        "slope_lo": np.nan,
                        "slope_hi": np.nan,
                        "p_selection": 1.0,
                        "oos_sign_rate": 0.0,
                        "n_obs": int(len(x)),
                        "contradicts_thesis": False,
                    }
                )
                continue
            p = selection_pvalue_one_series(x, y, iters=iters, seed=seed)
            lo, hi, _ = bootstrap_slope_ci(x, y, block=8, iters=iters, seed=seed)
            sign = oos_sign_rate(
                slope,
                r,
                horizon=horizon,
                test_days=252,
                step_days=252,
                init_train_frac=0.5,
            )
            rows.append(
                {
                    "target": target,
                    "horizon": horizon,
                    "corr": float(corr),
                    "slope": float(coef),
                    "slope_lo": lo,
                    "slope_hi": hi,
                    "p_selection": p,
                    "oos_sign_rate": sign,
                    "n_obs": int(len(x)),
                    "contradicts_thesis": bool(coef < 0),
                }
            )
    df = pd.DataFrame(rows)
    if not df.empty:
        elig = df["slope"].notna()
        df["q_value"] = np.nan
        if elig.any():
            df.loc[elig, "q_value"] = bh_fdr(df.loc[elig, "p_selection"].to_numpy())
        df.loc[~elig, "q_value"] = 1.0
    return df
