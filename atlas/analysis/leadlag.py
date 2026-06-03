from __future__ import annotations

import json

import numpy as np
import pandas as pd

from config import (
    BOOTSTRAP_BLOCK,
    BOOTSTRAP_ITERS,
    DUCKDB_PATH,
    FDR_ALPHA,
    FUND_MAX_LAG_QUARTERS,
    FUND_NMIN,
    MACRO_NMIN,
    MAX_LAG_DAYS,
    PRICE_NMIN,
    RANDOM_SEED,
)


def log_returns(prices: pd.Series) -> pd.Series:
    """Daily log returns; index preserved, first obs dropped."""
    return np.log(prices / prices.shift(1)).dropna()


def align_pair(a: pd.Series, b: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Inner-join two series on index. No forward-fill across gaps."""
    df = pd.concat([a.rename("a"), b.rename("b")], axis=1, join="inner").dropna()
    return df["a"], df["b"]


def infer_period_freq(index: pd.DatetimeIndex) -> str:
    """Classify a series' native frequency from median spacing in days."""
    if len(index) < 3:
        return "D"
    median_days = pd.Series(index).sort_values().diff().dt.days.median()
    if median_days >= 20:
        return "ME"
    if median_days >= 5:
        return "W"
    return "D"


def resample_returns_to_freq(daily_returns: pd.Series, freq: str) -> pd.Series:
    """Aggregate daily log-returns into the target frequency by summing (log-additive)."""
    if freq == "D":
        return daily_returns
    return daily_returns.resample(freq).sum().dropna()


def macro_changes(values: pd.Series, freq: str) -> pd.Series:
    """First-difference the macro level at its native frequency for stationarity."""
    return values.resample(freq).last().diff().dropna()


def cross_correlations(left: pd.Series, right: pd.Series, max_lag: int) -> pd.DataFrame:
    """Pearson corr of left_t vs right_{t+lag} for lag in [-max_lag, max_lag].

    Positive lag => `left` leads `right`.
    """
    rows = []
    lv = left.to_numpy()
    rv = right.to_numpy()
    n = len(lv)
    for lag in range(-max_lag, max_lag + 1):
        if lag >= 0:
            x, y = lv[: n - lag], rv[lag:]
        else:
            x, y = lv[-lag:], rv[: n + lag]
        if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
            corr = np.nan
        else:
            corr = float(np.corrcoef(x, y)[0, 1])
        rows.append({"lag": lag, "corr": corr, "n": len(x)})
    return pd.DataFrame(rows)


def _abs_corr(x: np.ndarray, y: np.ndarray) -> float:
    if np.std(x) == 0 or np.std(y) == 0:
        return 0.0
    return abs(float(np.corrcoef(x, y)[0, 1]))


def stationary_bootstrap_pvalue(
    x: np.ndarray, y: np.ndarray, *, iters: int, block: int, seed: int
) -> float:
    """Two-sided p-value for |corr(x, y)| via stationary block bootstrap of y.

    Resamples y in random-length blocks (preserving serial structure) to build
    a null distribution of |corr| under broken cross-dependence.
    """
    rng = np.random.default_rng(seed)
    n = len(x)
    observed = _abs_corr(x, y)
    p_geom = 1.0 / block
    count = 0
    for _ in range(iters):
        idx = np.empty(n, dtype=int)
        i = 0
        while i < n:
            start = rng.integers(0, n)
            length = rng.geometric(p_geom)
            for k in range(length):
                if i >= n:
                    break
                idx[i] = (start + k) % n
                i += 1
        if _abs_corr(x, y[idx]) >= observed:
            count += 1
    return (count + 1) / (iters + 1)


def bh_fdr(pvalues: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg adjusted q-values."""
    p = np.asarray(pvalues, dtype=float)
    n = len(p)
    order = np.argsort(p)
    ranked = p[order] * n / (np.arange(n) + 1)
    q_sorted = np.minimum.accumulate(ranked[::-1])[::-1]
    q = np.empty(n)
    q[order] = np.clip(q_sorted, 0, 1)
    return q


_LEADLAG_COLUMNS = [
    "pair_type", "left", "right", "lag", "corr", "p_value", "q_value", "n_eff", "stable",
]


def _ticker_for_node(nodes: pd.DataFrame, node_id: str) -> str:
    row = nodes.loc[nodes["id"] == node_id]
    if row.empty:
        return ""
    return json.loads(row["tickers"].iloc[0])[0]


def _fund_series(fundamentals: pd.DataFrame, ticker: str, col: str) -> pd.Series:
    """Point-in-time quarterly series for one ticker, indexed by filed date."""
    sub = fundamentals.loc[fundamentals["ticker"] == ticker, ["filed", col]].dropna()
    if sub.empty:
        return pd.Series(dtype=float)
    filed = pd.to_datetime(sub["filed"])
    series = pd.Series(sub[col].to_numpy(dtype=float), index=filed).sort_index()
    return series[~series.index.duplicated(keep="first")]


def _returns_on_filed_dates(
    daily_returns: pd.Series, filed_index: pd.DatetimeIndex
) -> pd.Series:
    """Aggregate returns over filed-date quarterly intervals."""
    if daily_returns.empty or filed_index.empty:
        return pd.Series(dtype=float)
    returns = daily_returns.sort_index()
    dates = pd.DatetimeIndex(filed_index).sort_values().unique()
    rows = []
    previous: pd.Timestamp | None = None
    for date in dates:
        start = date - pd.DateOffset(months=3) if previous is None else previous
        window = returns.loc[(returns.index > start) & (returns.index <= date)]
        rows.append({"date": date, "value": window.sum() if not window.empty else np.nan})
        previous = date
    series = pd.DataFrame(rows).set_index("date")["value"].dropna()
    return series.astype(float)


def _stable_across_halves(left: pd.Series, right: pd.Series, lag: int) -> bool:
    half = len(left) // 2
    if half < 30:
        return False
    peaks = []
    for sl in (slice(0, half), slice(half, None)):
        t = cross_correlations(left.iloc[sl], right.iloc[sl], max_lag=abs(lag) + 5)
        t = t.dropna(subset=["corr"])
        if t.empty:
            return False
        peaks.append(int(t.loc[t["corr"].abs().idxmax(), "lag"]))
    return all(np.sign(p) == np.sign(lag) for p in peaks) if lag != 0 else all(p == 0 for p in peaks)


def _lagged_arrays(left: pd.Series, right: pd.Series, lag: int) -> tuple[np.ndarray, np.ndarray]:
    if lag >= 0:
        return left.to_numpy()[: len(left) - lag], right.to_numpy()[lag:]
    return left.to_numpy()[-lag:], right.to_numpy()[: len(right) + lag]


def _peak_for_pair(left: pd.Series, right: pd.Series, max_lag: int) -> pd.Series | None:
    table = cross_correlations(left, right, max_lag=max_lag).dropna(subset=["corr"])
    if table.empty:
        return None
    return table.loc[table["corr"].abs().idxmax()]


def _fund_capex_revenue_rows(
    fundamentals: pd.DataFrame,
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    *,
    iters: int,
) -> list[dict]:
    rows = []
    for _, edge in edges.iterrows():
        up = _fund_series(fundamentals, _ticker_for_node(nodes, edge["from_id"]), "capex")
        down = _fund_series(fundamentals, _ticker_for_node(nodes, edge["to_id"]), "revenue")
        left, right = align_pair(up, down)
        if len(left) < FUND_NMIN:
            continue
        peak = _peak_for_pair(left, right, FUND_MAX_LAG_QUARTERS)
        if peak is None:
            continue
        lag = int(peak["lag"])
        x, y = _lagged_arrays(left, right, lag)
        p = stationary_bootstrap_pvalue(x, y, iters=iters, block=2, seed=RANDOM_SEED)
        rows.append(_leadlag_row("fund_capex_rev", edge["from_id"], edge["to_id"], peak, p, left, right))
    return rows


def _fund_capex_price_rows(
    fundamentals: pd.DataFrame,
    nodes: pd.DataFrame,
    ret_by_ticker: dict[str, pd.Series],
    *,
    iters: int,
) -> list[dict]:
    rows = []
    for _, node in nodes.iterrows():
        ticker = json.loads(node["tickers"])[0]
        if ticker not in ret_by_ticker:
            continue
        capex = _fund_series(fundamentals, ticker, "capex")
        returns_q = _returns_on_filed_dates(ret_by_ticker[ticker], pd.DatetimeIndex(capex.index))
        left, right = align_pair(capex, returns_q)
        if len(left) < FUND_NMIN:
            continue
        peak = _peak_for_pair(left, right, FUND_MAX_LAG_QUARTERS)
        if peak is None:
            continue
        lag = int(peak["lag"])
        x, y = _lagged_arrays(left, right, lag)
        p = stationary_bootstrap_pvalue(x, y, iters=iters, block=2, seed=RANDOM_SEED)
        rows.append(_leadlag_row("fund_capex_price", node["id"], node["id"], peak, p, left, right))
    return rows


def _leadlag_row(
    pair_type: str,
    left_id: str,
    right_id: str,
    peak: pd.Series,
    p_value: float,
    left: pd.Series,
    right: pd.Series,
) -> dict:
    lag = int(peak["lag"])
    return {
        "pair_type": pair_type,
        "left": left_id,
        "right": right_id,
        "lag": lag,
        "corr": float(peak["corr"]),
        "p_value": p_value,
        "q_value": np.nan,
        "n_eff": int(peak["n"]),
        "stable": _stable_across_halves(left, right, lag),
    }


def build_leadlag_table(
    returns: pd.DataFrame,
    macro: pd.DataFrame,
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    *,
    max_lag: int = MAX_LAG_DAYS,
    price_nmin: int = PRICE_NMIN,
    iters: int = BOOTSTRAP_ITERS,
    fundamentals: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Compute lead/lag rows for supplier->customer edges (price pairs).

    `returns` columns: ticker, date, log_return. Macro pairs use native frequency
    (handled by the caller resampling); here macro is left for extension and
    contributes no rows when empty.
    """
    rows: list[dict] = []
    ret_by_ticker = {t: g.set_index("date")["log_return"] for t, g in returns.groupby("ticker")}

    for _, e in edges.iterrows():
        lt = _ticker_for_node(nodes, e["from_id"])
        rt = _ticker_for_node(nodes, e["to_id"])
        if lt not in ret_by_ticker or rt not in ret_by_ticker:
            continue
        left, right = align_pair(ret_by_ticker[lt], ret_by_ticker[rt])
        if len(left) < price_nmin:
            continue
        table = cross_correlations(left, right, max_lag=max_lag).dropna(subset=["corr"])
        if table.empty:
            continue
        peak = table.loc[table["corr"].abs().idxmax()]
        lag = int(peak["lag"])
        if lag >= 0:
            x, y = left.to_numpy()[: len(left) - lag], right.to_numpy()[lag:]
        else:
            x, y = left.to_numpy()[-lag:], right.to_numpy()[: len(right) + lag]
        p = stationary_bootstrap_pvalue(
            x, y, iters=iters, block=BOOTSTRAP_BLOCK, seed=RANDOM_SEED
        )
        rows.append(
            {
                "pair_type": "edge",
                "left": e["from_id"],
                "right": e["to_id"],
                "lag": lag,
                "corr": float(peak["corr"]),
                "p_value": p,
                "q_value": np.nan,
                "n_eff": int(peak["n"]),
                "stable": _stable_across_halves(left, right, lag),
            }
        )

    if not macro.empty and not nodes.empty:
        macro_by_id = {sid: g.set_index("date")["value"] for sid, g in macro.groupby("series_id")}
        for sid, mser in macro_by_id.items():
            mser = mser.sort_index()
            freq = infer_period_freq(pd.DatetimeIndex(mser.index))
            m_chg = macro_changes(mser, freq)
            for _, node in nodes.iterrows():
                tkr = json.loads(node["tickers"])[0]
                if tkr not in ret_by_ticker:
                    continue
                pr = resample_returns_to_freq(ret_by_ticker[tkr], freq)
                left, right = align_pair(pr, m_chg)
                if len(left) < MACRO_NMIN:
                    continue
                table = cross_correlations(left, right, max_lag=12).dropna(subset=["corr"])
                if table.empty:
                    continue
                peak = table.loc[table["corr"].abs().idxmax()]
                lag = int(peak["lag"])
                if lag >= 0:
                    x, y = left.to_numpy()[: len(left) - lag], right.to_numpy()[lag:]
                else:
                    x, y = left.to_numpy()[-lag:], right.to_numpy()[: len(right) + lag]
                p = stationary_bootstrap_pvalue(x, y, iters=iters, block=4, seed=RANDOM_SEED)
                rows.append(
                    {
                        "pair_type": "macro",
                        "left": node["id"],
                        "right": sid,
                        "lag": lag,
                        "corr": float(peak["corr"]),
                        "p_value": p,
                        "q_value": np.nan,
                        "n_eff": int(peak["n"]),
                        "stable": _stable_across_halves(left, right, lag),
                    }
                )

    if fundamentals is not None and not fundamentals.empty and not nodes.empty:
        rows.extend(_fund_capex_revenue_rows(fundamentals, nodes, edges, iters=iters))
        rows.extend(_fund_capex_price_rows(fundamentals, nodes, ret_by_ticker, iters=iters))

    df = pd.DataFrame(rows, columns=_LEADLAG_COLUMNS)
    if not df.empty:
        df["q_value"] = bh_fdr(df["p_value"].to_numpy())
    return df


def run() -> None:  # pragma: no cover
    import duckdb

    con = duckdb.connect(str(DUCKDB_PATH))
    returns = con.execute("SELECT ticker, date, log_return FROM returns").fetchdf()
    macro = con.execute("SELECT series_id, date, value FROM macro_daily").fetchdf()
    nodes = con.execute("SELECT * FROM graph_nodes").fetchdf()
    edges = con.execute("SELECT * FROM graph_edges").fetchdf()
    try:
        fundamentals = con.execute(
            "SELECT ticker, period_end, filed, revenue, capex, gross_margin "
            "FROM fundamentals_quarterly"
        ).fetchdf()
    except duckdb.CatalogException:
        fundamentals = pd.DataFrame(
            columns=["ticker", "period_end", "filed", "revenue", "capex", "gross_margin"]
        )
    table = build_leadlag_table(returns, macro, nodes, edges, fundamentals=fundamentals)
    con.register("ll", table)
    con.execute("CREATE OR REPLACE TABLE leadlag AS SELECT * FROM ll")
    con.unregister("ll")
    con.close()
    print(f"leadlag: wrote {len(table)} rows (alpha={FDR_ALPHA})")


if __name__ == "__main__":
    run()
