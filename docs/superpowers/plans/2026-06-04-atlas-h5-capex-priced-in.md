# H5 Capex Priced-In Test — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add H5 to the Signal Lab — test whether upstream capex growth (known at its SEC filing date) predicts downstream forward de-beta'd equity returns over 1–2 quarters ("Confirmed = not-yet-priced-in", "Null = priced in").

**Architecture:** A new pure module `analysis/capex_price.py` computes the statistic by reusing H1/H0 machinery (YoY growth, M2 residualization, bootstrap slope CI, BH-FDR) plus two new pieces: point-in-time forward-return windows aligned to the filing date, and a horizon-selection-aware p-value. `analysis/signals.py` adds `h5_record` (inverted verdict). One new Signal Lab card.

**Tech Stack:** Python 3.13, NumPy, pandas, DuckDB; Svelte 5; pytest, vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-06-04-atlas-h5-capex-priced-in.md`

**Conventions:**
- Python tests from `atlas/`: `uv run --extra dev python -m pytest <path> -v`
- Web tests from `atlas/web/`: `npm run test`, `npm run build`
- Never commit `data/`, `dist/`, `node_modules/`, caches.
- Reuse, do not duplicate: `yoy_growth`, `residual_for_spec`, `bootstrap_slope_ci`, `bh_fdr`, `block_resample_one`, `circular_rotate`.

---

## File Structure

| File | Responsibility |
|---|---|
| `atlas/config.py` (modify) | `H5_FORWARD_HORIZONS = (63, 126)` trading days (~1Q, ~2Q) |
| `atlas/analysis/capex_price.py` (create) | `capex_growth_at_filed`, `forward_excess_return`, `horizon_selection_pvalue`, `capex_price_edge`, `capex_price_edges` |
| `atlas/analysis/leadlag.py` (modify) | `run()` writes a `capex_price` table |
| `atlas/analysis/signals.py` (modify) | `h5_record` (inverted verdict) + append in `build_signal_records` |
| `atlas/web/src/components/SignalCard.svelte` (modify) | `capex_price` chart branch + priced-in legend |
| `atlas/tests/test_capex_price.py` (create) | Unit tests |
| `atlas/tests/test_signals.py` (modify) | `h5_record` tests |

---

## Task 1: Config — forward horizons

**Files:** Modify `atlas/config.py`; Test `atlas/tests/test_capex_price.py`

- [ ] **Step 1: Write the failing test**

```python
# atlas/tests/test_capex_price.py
from config import H5_FORWARD_HORIZONS


def test_horizons_are_one_and_two_quarters():
    assert H5_FORWARD_HORIZONS == (63, 126)
```

- [ ] **Step 2: Run — fails**

Run: `uv run --extra dev python -m pytest tests/test_capex_price.py -v`
Expected: FAIL `ImportError: cannot import name 'H5_FORWARD_HORIZONS'`

- [ ] **Step 3: Add config**

Append to `atlas/config.py`:

```python
# H5 capex priced-in test: forward-return windows in trading days (~1Q, ~2Q).
H5_FORWARD_HORIZONS: tuple[int, ...] = (63, 126)
```

- [ ] **Step 4: Run — passes**; **Step 5: Commit**

```bash
git add atlas/config.py atlas/tests/test_capex_price.py
git commit -m "feat: H5 forward-horizon config"
```

---

## Task 2: Point-in-time forward excess return

**Files:** Create `atlas/analysis/capex_price.py`; Test `atlas/tests/test_capex_price.py`

- [ ] **Step 1: Write the failing tests**

```python
# append to atlas/tests/test_capex_price.py
import numpy as np
import pandas as pd
from analysis.capex_price import forward_excess_return


def _daily(start, n, vals):
    return pd.Series(vals, index=pd.bdate_range(start, periods=n))


def test_forward_excess_return_starts_strictly_after_filed():
    # Flat in train (alpha≈0), positive drift AFTER filed -> forward residual > 0.
    # (M2 residual subtracts fitted alpha, so a constant-everywhere series → ~0.)
    idx = pd.bdate_range("2020-01-01", periods=400)
    vals = np.where(np.arange(400) <= 100, 0.0, 0.001)        # 0 up to filed, +0.1%/day after
    asset = pd.Series(vals, index=idx)
    factors = {"SPY": pd.Series(0.0, index=idx), "SOXX": pd.Series(0.0, index=idx)}
    filed = idx[100]
    r = forward_excess_return(asset, factors, sector="SOXX", filed=filed, horizon_days=63)
    assert r > 0
    assert abs(r - 0.063) < 0.01                              # ~63 days of +0.001, none ≤ filed


def test_forward_excess_return_nan_when_no_future_data():
    idx = pd.bdate_range("2020-01-01", periods=100)
    asset = pd.Series(0.001, index=idx)
    factors = {"SPY": pd.Series(0.0, index=idx), "SOXX": pd.Series(0.0, index=idx)}
    r = forward_excess_return(asset, factors, sector="SOXX", filed=idx[-1], horizon_days=63)
    assert np.isnan(r)                                        # train ≥ 60 but no data after filed
```

- [ ] **Step 2: Run — fails** (`ModuleNotFoundError`)

- [ ] **Step 3: Implement**

```python
# atlas/analysis/capex_price.py
"""H5: is upstream capex priced into downstream equity?

Capex growth (known at the SEC FILING date) vs downstream forward de-beta'd
returns over 1-2 quarters. Point-in-time on the filing date — the forward window
opens strictly AFTER filed, and the de-beta betas use only data up to filed —
so this is a tradeability test, not look-ahead. Sample is small (~25 filings/
edge): effect sizes + bootstrap CIs + FDR, NO walk-forward.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analysis.fundamentals_leadlag import bootstrap_slope_ci, yoy_growth
from analysis.residualize import residual_for_spec
from analysis.significance import block_resample_one


def forward_excess_return(asset_daily: pd.Series, factors: dict[str, pd.Series], *,
                          sector: str | None, filed: pd.Timestamp,
                          horizon_days: int) -> float:
    """Sum of D's M2 residual daily returns over (filed, filed+horizon_days].

    Betas are fit point-in-time on data up to and including `filed` (train_index),
    so the forward window carries no look-ahead in either the signal or the control.
    """
    filed = pd.Timestamp(filed)
    train = asset_daily.index[asset_daily.index <= filed]
    if len(train) < 60:
        return float("nan")
    resid = residual_for_spec(asset_daily, factors, sector=sector, spec="M2",
                              train_index=train)
    fwd = resid[(resid.index > filed)]
    if fwd.empty:
        return float("nan")
    window = fwd.iloc[:horizon_days]
    if len(window) < max(5, horizon_days // 2):
        return float("nan")
    return float(window.sum())
```

- [ ] **Step 4: Run — passes**; **Step 5: Commit**

```bash
git add atlas/analysis/capex_price.py atlas/tests/test_capex_price.py
git commit -m "feat: H5 point-in-time forward excess return"
```

---

## Task 3: Capex growth indexed by filing date

**Files:** Modify `atlas/analysis/capex_price.py`; Test `atlas/tests/test_capex_price.py`

- [ ] **Step 1: Write the failing test**

```python
# append to atlas/tests/test_capex_price.py
from analysis.capex_price import capex_growth_at_filed


def test_capex_growth_indexed_by_filed_date():
    pe = pd.date_range("2018-03-31", periods=12, freq="QE")
    filed = pe + pd.Timedelta(days=40)                 # filed ~40d after quarter-end
    fund = pd.DataFrame({"ticker": "U", "period_end": pe, "filed": filed,
                         "capex": np.linspace(100, 210, 12)})
    g = capex_growth_at_filed(fund, "U")
    assert len(g) == 8                                  # 12 - 4 (YoY) = 8
    # index is filed dates, not period_end
    assert (g.index == pd.DatetimeIndex(filed[4:])).all()
```

- [ ] **Step 2: Run — fails**

- [ ] **Step 3: Implement** — append to `capex_price.py`:

```python
def capex_growth_at_filed(fundamentals: pd.DataFrame, ticker: str) -> pd.Series:
    """Upstream capex YoY growth, re-indexed onto the FILING date of each quarter."""
    sub = fundamentals.loc[fundamentals["ticker"] == ticker,
                           ["period_end", "filed", "capex"]].dropna()
    if sub.empty:
        return pd.Series(dtype=float)
    q = pd.to_datetime(sub["period_end"]).dt.to_period("Q")
    level = pd.Series(sub["capex"].to_numpy(float), index=q).sort_index()
    level = level[~level.index.duplicated(keep="last")]
    filed_by_q = (pd.Series(pd.to_datetime(sub["filed"]).to_numpy(), index=q)
                  .sort_index())
    filed_by_q = filed_by_q[~filed_by_q.index.duplicated(keep="last")]
    growth = yoy_growth(level)                          # PeriodIndex (Q), first 4 dropped
    filed_idx = pd.DatetimeIndex([filed_by_q.loc[qi] for qi in growth.index])
    return pd.Series(growth.to_numpy(), index=filed_idx).sort_index()
```

- [ ] **Step 4: Run — passes**; **Step 5: Commit**

```bash
git add atlas/analysis/capex_price.py atlas/tests/test_capex_price.py
git commit -m "feat: H5 capex growth re-indexed to filing date"
```

---

## Task 4: Horizon-selection-aware p + per-edge estimator

**Files:** Modify `atlas/analysis/capex_price.py`; Test `atlas/tests/test_capex_price.py`

- [ ] **Step 1: Write the failing tests**

```python
# append to atlas/tests/test_capex_price.py
from analysis.capex_price import capex_price_edge


def test_capex_price_edge_detects_forward_predictability():
    # capex growth at filing predicts the NEXT ~quarter of downstream residual return
    rng = np.random.default_rng(0)
    pe = pd.date_range("2016-03-31", periods=28, freq="QE")
    filed = pe + pd.Timedelta(days=40)
    g = rng.standard_normal(28)
    capex_level = np.exp(np.cumsum(0.05 + 0.02 * np.concatenate([np.zeros(4), g[:-4]])))
    fund = pd.DataFrame({"ticker": "U", "period_end": pe, "filed": filed, "capex": capex_level})
    # downstream daily returns: a drift in the quarter AFTER each filing proportional to capex growth
    idx = pd.bdate_range("2015-06-01", periods=3000)
    daily = pd.Series(0.0, index=idx)
    cg = capex_growth_at_filed(fund, "U")
    for f, val in cg.items():
        win = daily.index[(daily.index > f)][:63]
        daily.loc[win] += 0.0008 * val
    daily += 0.0001 * pd.Series(rng.standard_normal(len(idx)), index=idx)
    factors = {"SPY": pd.Series(0.0, index=idx), "SOXX": pd.Series(0.0, index=idx)}
    out = capex_price_edge(cg, daily, factors, sector="SOXX",
                           horizons=(63, 126), iters=200, seed=1)
    assert out["slope"] > 0
    assert out["horizon"] in (63, 126)
    assert out["n_obs"] >= 10
    assert out["contradicts_thesis"] is False


def test_capex_price_edge_null_for_unrelated_returns():
    rng = np.random.default_rng(2)
    pe = pd.date_range("2016-03-31", periods=28, freq="QE")
    filed = pe + pd.Timedelta(days=40)
    fund = pd.DataFrame({"ticker": "U", "period_end": pe, "filed": filed,
                         "capex": np.exp(np.cumsum(0.05 + 0.1 * rng.standard_normal(28)))})
    idx = pd.bdate_range("2015-06-01", periods=3000)
    daily = 0.0002 * pd.Series(rng.standard_normal(len(idx)), index=idx)   # pure noise
    factors = {"SPY": pd.Series(0.0, index=idx), "SOXX": pd.Series(0.0, index=idx)}
    cg = capex_growth_at_filed(fund, "U")
    out = capex_price_edge(cg, daily, factors, sector="SOXX",
                           horizons=(63, 126), iters=200, seed=3)
    assert out["p_selection"] > 0.1
```

- [ ] **Step 2: Run — fails**

- [ ] **Step 3: Implement** — append to `capex_price.py`:

```python
def _corr_slope(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return np.nan, np.nan
    corr = float(np.corrcoef(x, y)[0, 1])
    slope = float(np.polyfit(x, y, 1)[0])
    return corr, slope


def _aligned_forward(capex_growth: pd.Series, down_daily, factors, sector,
                     horizon: int) -> tuple[np.ndarray, np.ndarray]:
    xs, ys = [], []
    for filed, g in capex_growth.items():
        fwd = forward_excess_return(down_daily, factors, sector=sector,
                                    filed=filed, horizon_days=horizon)
        if np.isfinite(fwd):
            xs.append(float(g)); ys.append(fwd)
    return np.asarray(xs), np.asarray(ys)


def horizon_selection_pvalue(capex_growth: pd.Series, down_daily, factors, sector, *,
                             horizons, iters: int, seed: int) -> dict:
    """Best (signed-corr) horizon + selection-aware p over the horizon set.

    Null perturbs the capex-growth series (single series; block bootstrap),
    breaking its link to forward returns while preserving its own structure,
    then recomputes the max signed corr across horizons.
    """
    per_h = {h: _aligned_forward(capex_growth, down_daily, factors, sector, h)
             for h in horizons}
    best_h, best_corr, best = None, -np.inf, None
    for h, (x, y) in per_h.items():
        c, s = _corr_slope(x, y)
        if np.isfinite(c) and c > best_corr:
            best_h, best_corr, best = h, c, (x, y, s)
    if best is None:
        return {"horizon": horizons[0], "corr": np.nan, "slope": np.nan,
                "p_selection": 1.0, "n_obs": 0}
    x, y, slope = best
    rng = np.random.default_rng(seed)
    block = 2
    count = 0
    for _ in range(iters):
        null_max = -np.inf
        for h, (xh, yh) in per_h.items():
            if len(xh) < 3:
                continue
            xb = block_resample_one(xh, block=block, rng=rng)
            c, _ = _corr_slope(xb, yh)
            if np.isfinite(c):
                null_max = max(null_max, c)
        if null_max >= best_corr:
            count += 1
    return {"horizon": best_h, "corr": best_corr, "slope": slope,
            "p_selection": (count + 1) / (iters + 1), "n_obs": int(len(x))}


def capex_price_edge(capex_growth: pd.Series, down_daily: pd.Series,
                     factors: dict[str, pd.Series], *, sector: str | None,
                     horizons, iters: int, seed: int) -> dict:
    sel = horizon_selection_pvalue(capex_growth, down_daily, factors, sector,
                                   horizons=horizons, iters=iters, seed=seed)
    if sel["n_obs"] < 10:
        return {"horizon": sel["horizon"], "corr": float("nan"), "slope": float("nan"),
                "slope_lo": float("nan"), "slope_hi": float("nan"),
                "p_selection": 1.0, "contradicts_thesis": False, "n_obs": sel["n_obs"]}
    x, y = _aligned_forward(capex_growth, down_daily, factors, sector, sel["horizon"])
    lo, hi, slope = bootstrap_slope_ci(x, y, block=2, iters=iters, seed=seed)
    # contradicts: the strongest forward relationship is negative (reversal)
    neg = any(_corr_slope(*_aligned_forward(capex_growth, down_daily, factors, sector, h))[0] < -abs(sel["corr"])
              for h in horizons)
    return {"horizon": int(sel["horizon"]), "corr": float(sel["corr"]), "slope": slope,
            "slope_lo": lo, "slope_hi": hi, "p_selection": sel["p_selection"],
            "contradicts_thesis": bool(slope < 0 or neg), "n_obs": int(sel["n_obs"])}
```

- [ ] **Step 4: Run — passes**; **Step 5: Commit**

```bash
git add atlas/analysis/capex_price.py atlas/tests/test_capex_price.py
git commit -m "feat: H5 horizon-selection-aware p and per-edge priced-in estimator"
```

---

## Task 5: Driver over edges + FDR

**Files:** Modify `atlas/analysis/capex_price.py`; Test `atlas/tests/test_capex_price.py`

- [ ] **Step 1: Write the failing test**

```python
# append to atlas/tests/test_capex_price.py
import json
from analysis.capex_price import capex_price_edges


def test_capex_price_edges_fdr_over_eligible():
    rng = np.random.default_rng(4)
    pe = pd.date_range("2016-03-31", periods=28, freq="QE")
    filed = pe + pd.Timedelta(days=40)
    fund = pd.DataFrame({"ticker": "U", "period_end": pe, "filed": filed,
                         "capex": np.exp(np.cumsum(0.05 + 0.1 * rng.standard_normal(28)))})
    ridx = pd.bdate_range("2015-06-01", periods=3000)
    returns = pd.DataFrame({"ticker": "D", "date": ridx,
                            "log_return": 0.0002 * rng.standard_normal(len(ridx))})
    factors = {"SPY": pd.Series(0.0, index=ridx), "SOXX": pd.Series(0.0, index=ridx)}
    nodes = pd.DataFrame([{"id": "u", "tickers": json.dumps(["U"]), "stage": "chips"},
                          {"id": "d", "tickers": json.dumps(["D"]), "stage": "cloud"}])
    edges = pd.DataFrame([{"from_id": "u", "to_id": "d"}])
    out = capex_price_edges(fund, returns, factors, nodes, edges,
                            horizons=(63, 126), iters=100, seed=1)
    assert len(out) == 1
    assert {"horizon", "slope", "q_value", "n_obs"}.issubset(out.columns)
```

- [ ] **Step 2: Run — fails**

- [ ] **Step 3: Implement** — append to `capex_price.py`:

```python
def capex_price_edges(fundamentals: pd.DataFrame, returns: pd.DataFrame,
                      factors: dict[str, pd.Series], nodes: pd.DataFrame,
                      edges: pd.DataFrame, *, horizons, iters: int, seed: int) -> pd.DataFrame:
    """Per cross-edge: upstream capex growth (at filing) vs downstream forward
    de-beta'd return. FDR over eligible (finite-slope) edges."""
    import json as _json
    from analysis.leadlag import bh_fdr

    ret = {t: g.set_index("date")["log_return"].sort_index()
           for t, g in returns.groupby("ticker")}
    stage = {r.id: r.stage for r in nodes.itertuples()}
    from config import STAGE_SECTOR, FACTOR_TICKERS

    def ticker_of(node_id):
        row = nodes.loc[nodes["id"] == node_id]
        return _json.loads(row["tickers"].iloc[0])[0] if not row.empty else ""

    rows = []
    for e in edges.itertuples():
        ut, dt = ticker_of(e.from_id), ticker_of(e.to_id)
        cg = capex_growth_at_filed(fundamentals, ut)
        if cg.empty or dt not in ret:
            continue
        sec_d = FACTOR_TICKERS.get(STAGE_SECTOR.get(stage.get(e.to_id), ""))
        out = capex_price_edge(cg, ret[dt], factors, sector=sec_d,
                               horizons=horizons, iters=iters, seed=seed)
        out.update({"left": e.from_id, "right": e.to_id})
        rows.append(out)
    df = pd.DataFrame(rows)
    if not df.empty:
        elig = df["slope"].notna()
        df["q_value"] = np.nan
        if elig.any():
            df.loc[elig, "q_value"] = bh_fdr(df.loc[elig, "p_selection"].to_numpy())
    return df
```

- [ ] **Step 4: Run — passes**; **Step 5: Commit**

```bash
git add atlas/analysis/capex_price.py atlas/tests/test_capex_price.py
git commit -m "feat: H5 driver over cross-edges with FDR over eligible"
```

---

## Task 6: `h5_record` (inverted verdict) + table + build_signal_records

**Files:** Modify `atlas/analysis/signals.py`, `atlas/analysis/leadlag.py`; Test `atlas/tests/test_signals.py`

- [ ] **Step 1: Write the failing test** — append to `atlas/tests/test_signals.py`:

```python
from analysis.signals import h5_record


def _h5_rows(slope=0.6, q=0.05, contra=False):
    return pd.DataFrame([
        {"left": "broadcom", "right": "google", "horizon": 63, "corr": 0.5,
         "slope": slope, "slope_lo": 0.2, "slope_hi": 1.0, "p_selection": 0.02,
         "q_value": q, "contradicts_thesis": contra, "n_obs": 25},
    ])


def test_h5_confirmed_means_not_priced_in():
    rec = h5_record(_h5_rows(slope=0.6, q=0.05))
    assert rec["id"] == "H5"
    assert rec["verdict"] == "confirmed"        # forward-predictive => not priced in
    assert rec["chart"]["type"] == "capex_price"


def test_h5_null_means_priced_in():
    rec = h5_record(_h5_rows(slope=0.05, q=0.8))
    assert rec["verdict"] == "null"             # no forward predictability => priced in
```

- [ ] **Step 2: Run — fails**

- [ ] **Step 3: Implement** — append to `atlas/analysis/signals.py` (reuse `_num` from H1):

```python
def h5_record(rows: pd.DataFrame) -> dict:
    elig = rows[(rows["n_obs"] > 0) & rows["slope"].notna()]
    n = int(len(elig))
    confirmed = elig[(elig["q_value"] <= FDR_ALPHA) & (elig["slope"] > 0)
                     & (~elig["contradicts_thesis"])]
    suggestive = elig[(elig["slope"] > 0) & (elig["slope_lo"] > 0)
                      & (~elig["contradicts_thesis"])]
    contradicting = elig[elig["contradicts_thesis"]]
    if len(confirmed):
        verdict, best = "confirmed", confirmed.sort_values("q_value").iloc[0]
    elif len(suggestive):
        verdict, best = "suggestive", suggestive.sort_values("p_selection").iloc[0]
    elif len(contradicting):
        verdict, best = "contradicts", contradicting.iloc[0]
    elif len(elig):
        verdict, best = "null", elig.iloc[0]
    else:
        verdict, best = "null", rows.iloc[0] if len(rows) else pd.Series(dtype=float)
    interp = {"confirmed": "not yet priced in", "suggestive": "weak under-pricing signal",
              "null": "priced in", "contradicts": "over-reaction / reversal"}[verdict]
    return {
        "id": "H5", "title": "Is upstream capex priced into downstream equity?",
        "horizon": "1–2 quarters forward",
        "claim": "Upstream capex growth predicts downstream forward returns",
        "mechanism": f"Under-reaction to a slow real signal — verdict: {interp}",
        "verdict": verdict,
        "evidence_chain": [
            {"stage": "best edge corr", "metric": "corr", "value": _num(best.get("corr"))},
            {"stage": "best edge slope", "metric": "slope", "value": _num(best.get("slope"))},
            {"stage": "selected horizon (days)", "metric": "days", "value": _num(best.get("horizon"), 0)},
        ],
        "stat": {"name": "slope", "value": _num(best.get("slope")),
                 "ci": [_num(best.get("slope_lo")), _num(best.get("slope_hi"))],
                 "q_value": _num(best.get("q_value")), "n": n},
        "caveats": [f"~{int(elig['n_obs'].median()) if len(elig) else 0} filings/edge; overlapping forward windows",
                    "Confirmed ⇒ not-yet-priced-in; Null ⇒ priced in",
                    "Observational, point-in-time on filing date; no costs/turnover"],
        "chart": {"type": "capex_price", "ref": "h5"},
        "detail_rows": elig[["left", "right", "horizon", "corr", "slope", "slope_lo",
                             "slope_hi", "q_value", "n_obs"]].to_dict("records"),
    }
```

In `atlas/analysis/leadlag.py` `run()`, after the H1 (`fundamentals_leadlag`) write, add:

```python
    from analysis.capex_price import capex_price_edges
    from config import H5_FORWARD_HORIZONS
    # factors dict from the returns table (same tickers H1 uses)
    _ret = {t: g.set_index("date")["log_return"].sort_index()
            for t, g in returns.groupby("ticker")}
    _factors = {etf: _ret[etf] for etf in FACTOR_TICKERS.values() if etf in _ret}
    h5 = capex_price_edges(fundamentals, returns, _factors, nodes, edges,
                           horizons=H5_FORWARD_HORIZONS, iters=BOOTSTRAP_ITERS, seed=RANDOM_SEED)
    con.register("h5t", h5)
    con.execute("CREATE OR REPLACE TABLE capex_price AS SELECT * FROM h5t")
    con.unregister("h5t")
    print(f"capex_price: wrote {len(h5)} capex->price edge rows")
```

In `atlas/analysis/signals.py` `build_signal_records`, after the H1 append:

```python
    has_h5 = con.execute("SELECT count(*) FROM information_schema.tables "
                         "WHERE table_name='capex_price'").fetchone()[0] > 0
    if has_h5:
        h5 = con.execute('SELECT * FROM capex_price').df()
        if len(h5):
            records.append(h5_record(h5))
```

- [ ] **Step 4: Run — passes** (`uv run --extra dev python -m pytest tests/test_signals.py -v`)

- [ ] **Step 5: Commit**

```bash
git add atlas/analysis/signals.py atlas/analysis/leadlag.py atlas/tests/test_signals.py
git commit -m "feat: H5 record (inverted priced-in verdict) + capex_price table"
```

---

## Task 7: Web card chart + legend

**Files:** Modify `atlas/web/src/components/SignalCard.svelte`

- [ ] **Step 1: Add the `capex_price` chart branch**

In `SignalCard.svelte`, after the existing `capex_revenue_overlay` block, add a near-identical per-edge bar list keyed on `chart.type === "capex_price"`, plus a one-line legend so the inverted verdict reads clearly:

```svelte
  {#if signal.chart.type === "capex_price"}
    <p class="legend">Confirmed = <b>not yet priced in</b> · Null = priced in</p>
    <ul class="edges">
      {#each signal.detail_rows as r}
        <li><span>{r.left} → {r.right}</span>
          <b>slope {Number(r.slope).toFixed(2)}</b>
          <span class="ci">[{Number(r.slope_lo).toFixed(2)}, {Number(r.slope_hi).toFixed(2)}]</span>
          <span class="lag">{r.horizon}d · n={r.n_obs}</span></li>
      {/each}
    </ul>
  {/if}
```

Add to the `<style>`:

```css
  .legend { font-size:.74rem; opacity:.7; margin:.4rem 0 .2rem; }
```

- [ ] **Step 2: Type-check + build**

Run (from `atlas/web/`): `npx svelte-check --tsconfig ./tsconfig.json && npm run build`
Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add atlas/web/src/components/SignalCard.svelte
git commit -m "feat: H5 capex-price card chart + priced-in legend"
```

---

## Task 8: End-to-end smoke + coverage + report

**Files:** none (verification)

- [ ] **Step 1: Run analysis end-to-end**

Run from `atlas/`:
```bash
uv run make analyze
uv run python web/export_data.py --db data/atlas.duckdb --out /tmp/atlas_h5
uv run python -c "import json; r={x['id']:x for x in json.load(open('/tmp/atlas_h5/signals.json'))}; print('H5', r['H5']['verdict'], r['H5']['stat'])"
```
Expected: prints `H5 <verdict>` with slope/CI/q. **Report the verdict as-is** — Null ("priced in") is an expected, acceptable result; do not tune to force Confirmed.

- [ ] **Step 2: Coverage gate**

Run from `atlas/`:
```bash
uv run --extra dev python -m pytest --cov=analysis --cov-report=term-missing tests/test_capex_price.py tests/test_signals.py
```
Expected: pass; `analysis/capex_price.py` ≥ 80%.

- [ ] **Step 3: Full suites**

`uv run --extra dev python -m pytest -q` (from `atlas/`) and `npm run test && npm run build` (from `atlas/web/`). All green.

- [ ] **Step 4: Commit (note the verdict)**

```bash
git add -A -- ':!atlas/data' ':!atlas/web/static/data'
git commit -m "chore: H5 capex priced-in verified (verdict: <fill in>)" || echo "nothing to commit"
```

---

## Self-Review Notes

- **Filing-date PIT (spec §2)** enforced in `forward_excess_return` (window strictly `> filed`; betas fit on `index <= filed`) — the headline rigor.
- **Horizon selection-aware** p perturbs the single capex series and recomputes max corr across horizons — mirrors the Priority-1 single-series-perturbation invariant.
- **Overlapping windows (spec §4):** block bootstrap (block ≥ 2) for both the selection null and the slope CI.
- **Verdict inversion** lives only in `h5_record` interpretation + the card legend; the gate logic matches H1 (selection-aware q + sign; CI only for suggestive).
- **Eligibility/FDR** restricted to finite-slope edges (H1 review fix carried forward).
- **Reuses** `yoy_growth`, `residual_for_spec`, `bootstrap_slope_ci`, `bh_fdr`, `block_resample_one` — no duplication.
- **Not in this plan:** a trading backtest (costs/turnover) — only warranted if H5 returns Confirmed; that would be a separate Priority-2 spec.
