"""H9: does electricity cost compress cloud gross margins?"""
from __future__ import annotations

import pandas as pd

from analysis.leading_indicators import _quarterly_indicator, indicator_revenue_lead


def sector_margin_delta(fundamentals: pd.DataFrame, *, names: list[str]) -> pd.Series:
    """Cross-sectional median quarter-over-quarter gross-margin change."""
    per_name = {}
    for ticker in names:
        sub = fundamentals.loc[
            fundamentals["ticker"] == ticker,
            ["period_end", "gross_margin"],
        ].dropna()
        if sub.empty:
            continue
        quarter = pd.to_datetime(sub["period_end"]).dt.to_period("Q")
        level = pd.Series(sub["gross_margin"].to_numpy(float), index=quarter).sort_index()
        level = level[~level.index.duplicated(keep="last")]
        delta = level.diff().dropna()
        if not delta.empty:
            per_name[ticker] = delta
    if not per_name:
        return pd.Series(dtype=float)
    return pd.concat(per_name, axis=1).median(axis=1).dropna()


def _empty_power_margin_row(sid: str, lead: int) -> dict:
    return {
        "indicator": sid,
        "best_lead": lead,
        "corr": float("nan"),
        "slope": float("nan"),
        "slope_lo": float("nan"),
        "slope_hi": float("nan"),
        "p_selection": 1.0,
        "n_obs": 0,
        "contradicts_thesis": False,
    }


def power_margins_table(
    macro: pd.DataFrame,
    fundamentals: pd.DataFrame,
    *,
    price_series: tuple[str, ...],
    names: list[str],
    leads: tuple[int, ...],
    pub_lag: dict[str, int],
    iters: int,
    seed: int,
) -> pd.DataFrame:
    """One row per electricity-price series for cloud-margin compression."""
    from analysis.leadlag import bh_fdr

    margin = sector_margin_delta(fundamentals, names=names)
    rows = []
    for sid in price_series:
        price_q = _quarterly_indicator(macro, sid, pub_lag.get(sid, 1))
        if price_q.empty or margin.empty:
            rows.append(_empty_power_margin_row(sid, leads[0]))
            continue
        out = indicator_revenue_lead(
            -price_q,
            margin,
            leads=leads,
            iters=iters,
            seed=seed,
        )
        out["indicator"] = sid
        rows.append(out)
    df = pd.DataFrame(rows)
    if not df.empty:
        eligible = df["slope"].notna()
        df["q_value"] = float("nan")
        if eligible.any():
            df.loc[eligible, "q_value"] = bh_fdr(df.loc[eligible, "p_selection"].to_numpy())
    return df
