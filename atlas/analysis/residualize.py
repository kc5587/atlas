"""De-beta returns against market (M1) and market + orthogonalized sector (M2).

Betas (and the sector orthogonalization) are fit on the TRAIN index only, then
applied to the full series, so out-of-sample residuals carry no look-ahead.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _design(X: pd.DataFrame) -> np.ndarray:
    return np.column_stack([np.ones(len(X)), X.to_numpy(dtype=float)])


def _fit_betas(y: pd.Series, X: pd.DataFrame) -> np.ndarray:
    df = pd.concat([y.rename("y"), X], axis=1, join="inner").dropna()
    A = _design(df.drop(columns="y"))
    beta, *_ = np.linalg.lstsq(A, df["y"].to_numpy(dtype=float), rcond=None)
    return beta


def ols_residual(y: pd.Series, X: pd.DataFrame, *, train_index=None) -> pd.Series:
    """Residual of y on [const, X]; betas fit on train_index (default: all).

    train_index is intersected with the dates actually available in y and X, so a
    train window that extends beyond either series (e.g. a pair-overlap window
    applied to a shorter constituent) does not raise — it simply fits on the
    overlap.
    """
    if train_index is not None:
        fit_idx = y.index.intersection(X.index).intersection(train_index)
        fit_y, fit_X = y.loc[fit_idx], X.loc[fit_idx]
    else:
        fit_y, fit_X = y, X
    beta = _fit_betas(fit_y, fit_X)
    full = pd.concat([y.rename("y"), X], axis=1, join="inner").dropna()
    pred = _design(full.drop(columns="y")) @ beta
    resid = full["y"].to_numpy() - pred
    return pd.Series(resid, index=full.index)


def leave_one_out_sector(
    name_ticker: str, peer_tickers: list[str], returns: dict[str, pd.Series]
) -> pd.Series:
    """Equal-weight mean return of same-stage peers EXCLUDING the name itself.

    Robustness variant for heavy ETF constituents (spec §5): avoids a name
    sitting inside its own sector factor. Peers are the other universe tickers
    sharing the name's stage.
    """
    cols = [returns[t] for t in peer_tickers if t != name_ticker and t in returns]
    if not cols:
        return pd.Series(dtype=float)
    return pd.concat(cols, axis=1, join="inner").dropna().mean(axis=1)


def orthogonalize(target: pd.Series, base: pd.Series, *, train_index=None) -> pd.Series:
    """Return target residualized on base (the 'pure' factor)."""
    return ols_residual(target, pd.DataFrame({"base": base}), train_index=train_index)


def residual_for_spec(
    asset: pd.Series,
    factors: dict[str, pd.Series],
    *,
    sector: str | None,
    spec: str,
    train_index,
) -> pd.Series:
    """Idiosyncratic return for one spec.

    M1: residual on SPY only.
    M2: residual on SPY + sector_pure (sector orthogonalized on SPY, train-only).
    """
    spy = factors["SPY"]
    if spec == "M1" or sector is None:
        return ols_residual(asset, pd.DataFrame({"SPY": spy}), train_index=train_index)
    sector_pure = orthogonalize(factors[sector], spy, train_index=train_index)
    X = pd.DataFrame({"SPY": spy, "SEC": sector_pure}).dropna()
    return ols_residual(asset, X, train_index=train_index)
