"""H10: electricity demand growth vs power-layer forward returns."""
from __future__ import annotations

import numpy as np
import pandas as pd

from analysis.leading_indicators import indicator_yoy
from analysis.macro_sector import monthly_returns
from analysis.vol_termstructure import (
    _corr_slope,
    aligned_forward,
    oos_sign_rate,
    selection_pvalue_one_series,
)


def _demand_monthly(macro: pd.DataFrame, sid: str, pub_lag_months: int) -> pd.Series:
    sub = macro.loc[macro["series_id"] == sid, ["date", "value"]].dropna()
    if sub.empty:
        return pd.Series(dtype=float)
    series = pd.Series(
        sub["value"].to_numpy(float),
        index=pd.to_datetime(sub["date"]),
    ).sort_index()
    yoy = indicator_yoy(series, pub_lag_months=pub_lag_months)
    return pd.Series(yoy.to_numpy(), index=yoy.index.to_period("M").to_timestamp())


def _empty_power_demand_row(name: str, horizon: int, n_obs: int = 0) -> dict:
    return {
        "name": name,
        "horizon": horizon,
        "corr": np.nan,
        "slope": np.nan,
        "slope_lo": np.nan,
        "slope_hi": np.nan,
        "p_selection": 1.0,
        "oos_sign_rate": 0.0,
        "n_obs": int(n_obs),
        "contradicts_thesis": False,
    }


def power_demand_table(
    macro: pd.DataFrame,
    returns: pd.DataFrame,
    *,
    demand_series: tuple[str, ...],
    names: list[str],
    horizons: tuple[int, ...],
    pub_lag: dict[str, int],
    iters: int,
    seed: int,
) -> pd.DataFrame:
    """One row per name/horizon for demand YoY vs forward power-name return."""
    from analysis.fundamentals_leadlag import bootstrap_slope_ci
    from analysis.leadlag import bh_fdr

    sid = next(
        (series for series in demand_series if not macro.loc[macro["series_id"] == series].empty),
        None,
    )
    demand = (
        _demand_monthly(macro, sid, pub_lag.get(sid, 1))
        if sid is not None
        else pd.Series(dtype=float)
    )
    rows = []
    for name in names:
        target = monthly_returns(returns, name)
        for horizon in horizons:
            if demand.empty or target.empty:
                rows.append(_empty_power_demand_row(name, horizon))
                continue
            x, y = aligned_forward(demand, target, horizon=horizon)
            corr, slope = _corr_slope(x, y)
            if not np.isfinite(corr) or len(x) < 10:
                rows.append(_empty_power_demand_row(name, horizon, len(x)))
                continue
            p_selection = selection_pvalue_one_series(x, y, iters=iters, seed=seed)
            lo, hi, _ = bootstrap_slope_ci(x, y, block=3, iters=iters, seed=seed)
            sign_rate = oos_sign_rate(
                demand,
                target,
                horizon=horizon,
                test_days=24,
                step_days=24,
                init_train_frac=0.5,
            )
            rows.append(
                {
                    "name": name,
                    "horizon": horizon,
                    "corr": float(corr),
                    "slope": float(slope),
                    "slope_lo": lo,
                    "slope_hi": hi,
                    "p_selection": p_selection,
                    "oos_sign_rate": sign_rate,
                    "n_obs": int(len(x)),
                    "contradicts_thesis": bool(slope < 0),
                }
            )
    df = pd.DataFrame(rows)
    if not df.empty:
        eligible = df["slope"].notna()
        df["q_value"] = np.nan
        if eligible.any():
            df.loc[eligible, "q_value"] = bh_fdr(df.loc[eligible, "p_selection"].to_numpy())
    return df
