from __future__ import annotations

import json

import numpy as np
import pandas as pd

from config import (
    BOOTSTRAP_BLOCK,
    BOOTSTRAP_ITERS,
    DUCKDB_PATH,
    FACTOR_TICKERS,
    FDR_ALPHA,
    FUND_MAX_LAG_QUARTERS,
    FUND_NMIN,
    H5_FORWARD_HORIZONS,
    LAG_MAX,
    LAG_MIN,
    MACRO_NMIN,
    MAX_LAG_DAYS,
    OOS_EMBARGO_DAYS,
    OOS_INIT_TRAIN_FRAC,
    OOS_MIN_FOLDS,
    OOS_SIGN_RATE_FLOOR,
    OOS_STEP_DAYS,
    OOS_TEST_DAYS,
    PRICE_NMIN,
    RANDOM_SEED,
    STAGE_SECTOR,
)
from analysis.oos import oos_stability
from analysis.residualize import residual_for_spec
from analysis.significance import _corr_at_lag, _signed_peak, selection_aware


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

SPECS = {"M1_market": "M1", "M2_market_sector": "M2"}


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


def build_hardened_edges(returns, nodes, edges, *, iters, seed) -> list[dict]:
    ret = {t: g.set_index("date")["log_return"].sort_index()
           for t, g in returns.groupby("ticker")}
    factors = {etf: ret[etf] for etf in FACTOR_TICKERS.values() if etf in ret}
    stage = {r.id: r.stage for r in nodes.itertuples()}
    rows: list[dict] = []
    for spec_label, spec in SPECS.items():
        spec_rows = []
        for e in edges.itertuples():
            lt = _ticker_for_node(nodes, e.from_id)
            rt = _ticker_for_node(nodes, e.to_id)
            if lt not in ret or rt not in ret:
                continue
            sec_l = FACTOR_TICKERS.get(STAGE_SECTOR.get(stage.get(e.from_id), ""))
            sec_r = FACTOR_TICKERS.get(STAGE_SECTOR.get(stage.get(e.to_id), ""))
            # Train window = first 50% of the PAIR's overlap (spec §3), so the
            # same train_index is valid for residualizing both series even when
            # their histories differ in length/start (e.g. nvidia -> dell).
            pair_idx = ret[lt].index.intersection(ret[rt].index)
            train = pair_idx[: int(len(pair_idx) * OOS_INIT_TRAIN_FRAC)]
            left = residual_for_spec(ret[lt], factors, sector=sec_l, spec=spec, train_index=train)
            right = residual_for_spec(ret[rt], factors, sector=sec_r, spec=spec, train_index=train)
            paired = pd.concat([left.rename("l"), right.rename("r")], axis=1, join="inner").dropna()
            if len(paired) < PRICE_NMIN:
                continue
            raw = _corr_at_lag(ret[lt].reindex(paired.index).to_numpy(),
                               ret[rt].reindex(paired.index).to_numpy(), LAG_MIN)
            sig = selection_aware(paired["l"].to_numpy(), paired["r"].to_numpy(),
                                  lag_min=LAG_MIN, lag_max=LAG_MAX, iters=iters, seed=seed)
            oos = oos_stability(left, right, lag_min=LAG_MIN, lag_max=LAG_MAX,
                                test_days=OOS_TEST_DAYS, step_days=OOS_STEP_DAYS,
                                init_train_frac=OOS_INIT_TRAIN_FRAC, embargo=OOS_EMBARGO_DAYS)
            spec_rows.append({
                "pair_type": "edge", "left": e.from_id, "right": e.to_id,
                # Legacy-compatible aliases so existing Zod schema + map keep working:
                "corr": sig["corr"], "p_value": sig["p_selection"],
                "factor_model": spec_label, "corr_raw": raw, "corr_resid": sig["corr"],
                "lag": sig["lag"], "corr_contemporaneous": sig["corr_contemporaneous"],
                "p_selection": sig["p_selection"], "block_len": sig["block_len"],
                "best_neg_lag_corr": sig["best_neg_lag_corr"],
                "contradicts_thesis": sig["contradicts_thesis"], "inverse_lead": sig["inverse_lead"],
                "n_eff": len(paired), "n_folds": oos["n_folds"],
                "oos_corr_median": oos["oos_corr_median"], "oos_corr_iqr": oos["oos_corr_iqr"],
                "oos_sign_rate": oos["oos_sign_rate"], "fold_date_ranges": json.dumps(oos["fold_date_ranges"]),
            })
        # Per-spec BH-FDR over this family.
        if spec_rows:
            q = bh_fdr(np.array([r["p_selection"] for r in spec_rows]))
            for r, qv in zip(spec_rows, q):
                r["q_value"] = float(qv)
                r["m"] = len(spec_rows)
                r["confirmed"] = bool(
                    qv <= FDR_ALPHA and not r["contradicts_thesis"]
                    and not r["inverse_lead"] and r["corr_resid"] > 0
                    and r["n_folds"] >= OOS_MIN_FOLDS and r["oos_sign_rate"] >= OOS_SIGN_RATE_FLOOR
                )
                r["stable"] = r["confirmed"]  # legacy alias consumed by the map's edgeStyle
        rows.extend(spec_rows)
    # survives_sector_control: confirmed under M2.
    m2 = {(r["left"], r["right"]) for r in rows if r["factor_model"] == "M2_market_sector" and r["confirmed"]}
    for r in rows:
        r["survives_sector_control"] = (r["left"], r["right"]) in m2
    return rows


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
    legacy = build_leadlag_table(returns, macro, nodes, edges, fundamentals=fundamentals)
    non_edge = legacy[legacy["pair_type"] != "edge"]
    hardened = pd.DataFrame(build_hardened_edges(
        returns, nodes, edges, iters=BOOTSTRAP_ITERS, seed=RANDOM_SEED))
    combined = pd.concat([non_edge, hardened], ignore_index=True)
    con.register("ll", combined)
    con.execute("CREATE OR REPLACE TABLE leadlag AS SELECT * FROM ll")
    con.unregister("ll")
    from analysis.fundamentals_leadlag import capex_revenue_edges
    h1 = capex_revenue_edges(fundamentals, nodes, edges,
                             iters=BOOTSTRAP_ITERS, seed=RANDOM_SEED)
    con.register("h1t", h1)
    con.execute("CREATE OR REPLACE TABLE fundamentals_leadlag AS SELECT * FROM h1t")
    con.unregister("h1t")
    print(f"fundamentals_leadlag: wrote {len(h1)} capex->revenue edge rows")
    from analysis.capex_price import capex_price_edges
    _ret = {
        t: g.set_index("date")["log_return"].sort_index()
        for t, g in returns.groupby("ticker")
    }
    _factors = {etf: _ret[etf] for etf in FACTOR_TICKERS.values() if etf in _ret}
    h5 = capex_price_edges(
        fundamentals,
        returns,
        _factors,
        nodes,
        edges,
        horizons=H5_FORWARD_HORIZONS,
        iters=BOOTSTRAP_ITERS,
        seed=RANDOM_SEED,
    )
    con.register("h5t", h5)
    con.execute("CREATE OR REPLACE TABLE capex_price AS SELECT * FROM h5t")
    con.unregister("h5t")
    print(f"capex_price: wrote {len(h5)} capex->price edge rows")
    con.close()
    print(f"leadlag: {len(non_edge)} non-edge + {len(hardened)} hardened edge rows")


if __name__ == "__main__":
    run()
