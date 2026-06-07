"""H15: customer -> supplier monthly link momentum (Cohen-Frazzini).

A node's customers' prior-month idiosyncratic (M2-residual) return predicts the
node's forward idiosyncratic return. Pure functions: DataFrame in, dict/DataFrame
out. Uses the full graph because this is returns-based, not fundamentals-based.
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from analysis.fundamentals_leadlag import bootstrap_slope_ci
from analysis.oos import walk_forward_folds
from analysis.residualize import residual_for_spec
from analysis.significance import auto_block_length, circular_rotate
from config import (
    BOOTSTRAP_ITERS,
    FACTOR_TICKERS,
    H15_OOS_STEP_MONTHS,
    H15_OOS_TEST_MONTHS,
    RANDOM_SEED,
    STAGE_SECTOR,
)

FACTOR_ETFS = ("SPY", "SOXX", "IGV")


def monthly_returns(returns: pd.DataFrame) -> pd.DataFrame:
    """Daily log returns -> wide month-end DataFrame, columns=tickers."""
    df = returns.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["month"] = df["date"].dt.to_period("M").dt.to_timestamp("M")
    return df.groupby(["month", "ticker"])["log_return"].sum().unstack("ticker").sort_index()


def _sector_etf(stage: str) -> str | None:
    return FACTOR_TICKERS.get(STAGE_SECTOR.get(stage, ""))


def residual_monthly_returns(monthly: pd.DataFrame, nodes: pd.DataFrame) -> pd.DataFrame:
    """M2-residual monthly return per node ticker, with betas fit on full sample."""
    factors = {etf: monthly[etf] for etf in FACTOR_ETFS if etf in monthly.columns}
    stage_of = {}
    for row in nodes.itertuples():
        for ticker in json.loads(row.tickers):
            stage_of[ticker] = row.stage

    out = {}
    for ticker in monthly.columns:
        if ticker in FACTOR_ETFS or ticker not in stage_of:
            continue
        sector = _sector_etf(stage_of[ticker])
        sector = sector if sector and sector in factors else None
        out[ticker] = residual_for_spec(
            monthly[ticker],
            factors,
            sector=sector,
            spec="M2",
            train_index=monthly.index,
        )
    return pd.DataFrame(out)


def _ticker_of(nodes: pd.DataFrame, node_id: str) -> str | None:
    row = nodes.loc[nodes["id"] == node_id]
    if row.empty:
        return None
    return json.loads(row["tickers"].iloc[0])[0]


def link_signal_panel(
    resid: pd.DataFrame,
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    *,
    min_months: int,
) -> pd.DataFrame:
    """Long panel [node, month, signal, fwd_target] for customer->supplier links.

    signal[S,t] = equal-weight mean of S's customers' residual return at t.
    fwd_target[S,t] = S's residual return at t+1.
    """
    rows = []
    for supplier in nodes["id"]:
        supplier_ticker = _ticker_of(nodes, supplier)
        if supplier_ticker is None or supplier_ticker not in resid.columns:
            continue
        customers = edges.loc[edges["from_id"] == supplier, "to_id"]
        customer_tickers = [
            ticker
            for ticker in (_ticker_of(nodes, customer) for customer in customers)
            if ticker and ticker in resid.columns
        ]
        if not customer_tickers:
            continue
        signal = resid[customer_tickers].mean(axis=1)
        target = resid[supplier_ticker].shift(-1)
        paired = pd.concat([signal.rename("signal"), target.rename("fwd_target")], axis=1).dropna()
        if len(paired) < min_months:
            continue
        rows.extend(
            {
                "node": supplier,
                "month": month,
                "signal": float(row["signal"]),
                "fwd_target": float(row["fwd_target"]),
            }
            for month, row in paired.iterrows()
        )
    return pd.DataFrame(rows, columns=["node", "month", "signal", "fwd_target"])


def _pooled_slope(signal: np.ndarray, target: np.ndarray) -> float:
    if len(signal) < 3 or np.std(signal) == 0:
        return float("nan")
    return float(np.polyfit(signal, target, 1)[0])


def _oos_sign_rate(panel: pd.DataFrame) -> tuple[float, int]:
    """Walk-forward monthly sign agreement of train vs test pooled slope."""
    months = pd.DatetimeIndex(sorted(panel["month"].unique()))
    if len(months) < 2 * H15_OOS_TEST_MONTHS:
        return 0.0, 0
    folds = walk_forward_folds(
        months,
        test_days=H15_OOS_TEST_MONTHS,
        step_days=H15_OOS_STEP_MONTHS,
        init_train_frac=0.5,
        embargo=0,
    )
    signs = []
    for train_idx, test_idx in folds:
        train = panel[panel["month"].isin(set(train_idx))]
        test = panel[panel["month"].isin(set(test_idx))]
        train_slope = _pooled_slope(train["signal"].to_numpy(), train["fwd_target"].to_numpy())
        test_slope = _pooled_slope(test["signal"].to_numpy(), test["fwd_target"].to_numpy())
        if np.isfinite(train_slope) and np.isfinite(test_slope) and train_slope != 0:
            signs.append(np.sign(train_slope) == np.sign(test_slope))
    return (float(np.mean(signs)) if signs else 0.0), len(signs)


def link_predictability(
    panel: pd.DataFrame,
    *,
    iters: int = BOOTSTRAP_ITERS,
    seed: int = RANDOM_SEED,
) -> dict:
    """Pooled fwd_target~signal test with CI, circular p-value, and OOS sign rate."""
    if panel.empty:
        return {
            "slope": float("nan"),
            "slope_lo": float("nan"),
            "slope_hi": float("nan"),
            "p_value": 1.0,
            "q_value": 1.0,
            "oos_sign_rate": 0.0,
            "n_obs": 0,
            "n_nodes": 0,
            "n_months": 0,
            "n_folds": 0,
        }

    signal = panel["signal"].to_numpy()
    target = panel["fwd_target"].to_numpy()
    observed = _pooled_slope(signal, target)
    lo, hi, _ = bootstrap_slope_ci(
        signal,
        target,
        block=auto_block_length(target),
        iters=iters,
        seed=seed,
    )

    rng = np.random.default_rng(seed)
    null = []
    for _ in range(iters):
        parts = []
        for _, group in panel.groupby("node", sort=False):
            shifted = group.copy()
            shift = int(rng.integers(1, max(2, len(group))))
            shifted["signal"] = circular_rotate(group["signal"].to_numpy(), shift)
            parts.append(shifted)
        permuted = pd.concat(parts)
        null.append(
            _pooled_slope(
                permuted["signal"].to_numpy(),
                permuted["fwd_target"].to_numpy(),
            )
        )
    null_values = np.array([value for value in null if np.isfinite(value)])
    if observed > 0:
        p_value = float((np.sum(null_values >= observed) + 1) / (len(null_values) + 1))
    else:
        p_value = float(
            (np.sum(np.abs(null_values) >= abs(observed)) + 1) / (len(null_values) + 1)
        )
    sign_rate, n_folds = _oos_sign_rate(panel)
    return {
        "slope": observed,
        "slope_lo": float(lo),
        "slope_hi": float(hi),
        "p_value": p_value,
        "q_value": p_value,
        "oos_sign_rate": sign_rate,
        "n_obs": int(len(panel)),
        "n_nodes": int(panel["node"].nunique()),
        "n_months": int(panel["month"].nunique()),
        "n_folds": n_folds,
    }
