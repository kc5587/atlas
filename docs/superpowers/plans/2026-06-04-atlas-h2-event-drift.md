# H2 Event-Drift — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add H2 to the Signal Lab — does an upstream **capex surprise** (standardized, point-in-time at filing) predict downstream forward de-beta'd drift over 21/42/63 trading days (PEAD-style)? Confirmed = under-reaction; Null = efficient.

**Architecture:** New pure module `analysis/event_drift.py` reuses H5/H1 machinery (`capex_growth_at_filed`, `forward_excess_return`, `bootstrap_slope_ci`, `block_resample_one`, `bh_fdr`) plus a standardized capex surprise and a **pooled** event-study regression (one slope across all edges), with quarter-block bootstrap and horizon selection. One new Signal Lab card.

**Tech Stack:** Python 3.13, NumPy, pandas, DuckDB; Svelte 5; pytest, vitest.

**Spec:** `docs/superpowers/specs/2026-06-04-atlas-h2-event-drift.md`

**Conventions:** Python tests from `atlas/`: `uv run --extra dev python -m pytest <path> -v`. Reuse helpers, do not duplicate. Never commit `data/`, `dist/`, `node_modules/`, caches.

---

## File Structure

| File | Responsibility |
|---|---|
| `atlas/config.py` (modify) | `H2_DRIFT_HORIZONS = (21, 42, 63)`, `H2_SURPRISE_K = 4` |
| `atlas/analysis/event_drift.py` (create) | `capex_surprise`, `pooled_events`, `event_drift` |
| `atlas/analysis/leadlag.py` (modify) | `run()` writes an `event_drift` table |
| `atlas/analysis/signals.py` (modify) | `h2_record` + append in `build_signal_records` |
| `atlas/web/src/components/SignalCard.svelte` (modify) | `event_drift` chart branch |
| `atlas/tests/test_event_drift.py` (create) | Unit tests |
| `atlas/tests/test_signals.py` (modify) | `h2_record` tests |

---

## Task 1: Config

**Files:** Modify `atlas/config.py`; Test `atlas/tests/test_event_drift.py`

- [ ] **Step 1: Failing test**

```python
# atlas/tests/test_event_drift.py
from config import H2_DRIFT_HORIZONS, H2_SURPRISE_K


def test_h2_config():
    assert H2_DRIFT_HORIZONS == (21, 42, 63)
    assert H2_SURPRISE_K == 4
```

- [ ] **Step 2: Run — fails** (`ImportError`)
- [ ] **Step 3:** Append to `atlas/config.py`:

```python
# H2 event-drift: forward drift horizons (trading days) and surprise lookback (quarters).
H2_DRIFT_HORIZONS: tuple[int, ...] = (21, 42, 63)
H2_SURPRISE_K = 4
```

- [ ] **Step 4: Run — passes**; **Step 5: Commit** `feat: H2 config (drift horizons, surprise lookback)`

---

## Task 2: Standardized capex surprise (PIT)

**Files:** Create `atlas/analysis/event_drift.py`; Test `atlas/tests/test_event_drift.py`

- [ ] **Step 1: Failing tests**

```python
# append to atlas/tests/test_event_drift.py
import numpy as np
import pandas as pd
from analysis.event_drift import capex_surprise


def _fund(ticker, n=24, start="2016-03-31"):
    pe = pd.date_range(start, periods=n, freq="QE")
    filed = pe + pd.Timedelta(days=40)
    rng = np.random.default_rng(0)
    capex = np.exp(np.cumsum(0.05 + 0.1 * rng.standard_normal(n)))
    return pd.DataFrame({"ticker": ticker, "period_end": pe, "filed": filed, "capex": capex})


def test_capex_surprise_is_standardized_and_filing_indexed():
    s = capex_surprise(_fund("U"), "U", k=4)
    assert isinstance(s.index, pd.DatetimeIndex)        # indexed by filing date
    assert abs(s.mean()) < 1.0 and 0.3 < s.std() < 3.0  # roughly standardized
    # point-in-time: a spike in the LAST quarter does not change earlier surprises
    f2 = _fund("U")
    base = capex_surprise(f2, "U", k=4)
    f2.loc[f2.index[-1], "capex"] *= 5
    after = capex_surprise(f2, "U", k=4)
    assert np.allclose(base.iloc[:-1].to_numpy(), after.iloc[:-1].to_numpy())
```

- [ ] **Step 2: Run — fails**
- [ ] **Step 3: Implement** — create `atlas/analysis/event_drift.py`:

```python
"""H2: does an upstream capex SURPRISE predict downstream forward drift?

Standardized, point-in-time capex surprise (deviation from the company's own
trailing trend) at the filing date, vs downstream forward de-beta'd returns,
pooled across edges as an event study. Sample is event-clustered -> quarter-block
bootstrap; no walk-forward.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analysis.capex_price import capex_growth_at_filed, forward_excess_return
from analysis.fundamentals_leadlag import bootstrap_slope_ci
from analysis.significance import block_resample_one


def capex_surprise(fundamentals: pd.DataFrame, ticker: str, *, k: int = 4) -> pd.Series:
    """Standardized capex-growth surprise, indexed by filing date (PIT).

    surprise_t = (g_t - mean(g over prior k)) / std(g over prior k), using only
    quarters strictly before t (shift(1)).
    """
    g = capex_growth_at_filed(fundamentals, ticker)        # filing-indexed YoY growth
    if len(g) < k + 1:
        return pd.Series(dtype=float)
    prior = g.shift(1)
    exp = prior.rolling(k).mean()
    sig = prior.rolling(k).std()
    s = (g - exp) / sig.replace(0.0, np.nan)
    return s.dropna()
```

- [ ] **Step 4: Run — passes**; **Step 5: Commit** `feat: H2 standardized PIT capex surprise`

---

## Task 3: Pooled events

**Files:** Modify `atlas/analysis/event_drift.py`; Test `atlas/tests/test_event_drift.py`

- [ ] **Step 1: Failing test**

```python
# append to atlas/tests/test_event_drift.py
import json
from analysis.event_drift import pooled_events


def test_pooled_events_pools_across_edges_after_filing():
    fund = pd.concat([_fund("U"), _fund("V")], ignore_index=True)
    ridx = pd.bdate_range("2015-06-01", periods=3000)
    rng = np.random.default_rng(1)
    returns = pd.concat([
        pd.DataFrame({"ticker": "D", "date": ridx, "log_return": 0.0002 * rng.standard_normal(len(ridx))}),
    ], ignore_index=True)
    factors = {"SPY": pd.Series(0.0, index=ridx), "SOXX": pd.Series(0.0, index=ridx)}
    nodes = pd.DataFrame([{"id": "u", "tickers": json.dumps(["U"]), "stage": "chips"},
                          {"id": "v", "tickers": json.dumps(["V"]), "stage": "chips"},
                          {"id": "d", "tickers": json.dumps(["D"]), "stage": "cloud"}])
    edges = pd.DataFrame([{"from_id": "u", "to_id": "d"}, {"from_id": "v", "to_id": "d"}])
    ev = pooled_events(fund, returns, factors, nodes, edges, horizon=42, k=4)
    assert {"date", "surprise", "fwd"}.issubset(ev.columns)
    assert len(ev) > 20                                   # both edges pooled
    assert ev["date"].is_monotonic_increasing
```

- [ ] **Step 2: Run — fails**
- [ ] **Step 3: Implement** — append:

```python
def pooled_events(fundamentals: pd.DataFrame, returns: pd.DataFrame,
                  factors: dict[str, pd.Series], nodes: pd.DataFrame,
                  edges: pd.DataFrame, *, horizon: int, k: int) -> pd.DataFrame:
    import json as _json
    from config import STAGE_SECTOR, FACTOR_TICKERS

    ret = {t: g.set_index("date")["log_return"].sort_index()
           for t, g in returns.groupby("ticker")}
    stage = {r.id: r.stage for r in nodes.itertuples()}

    def ticker_of(node_id):
        row = nodes.loc[nodes["id"] == node_id]
        return _json.loads(row["tickers"].iloc[0])[0] if not row.empty else ""

    rows = []
    for e in edges.itertuples():
        ut, dt = ticker_of(e.from_id), ticker_of(e.to_id)
        s = capex_surprise(fundamentals, ut, k=k)
        if s.empty or dt not in ret:
            continue
        sec_d = FACTOR_TICKERS.get(STAGE_SECTOR.get(stage.get(e.to_id), ""))
        for f, sv in s.items():
            if not np.isfinite(sv):
                continue
            fr = forward_excess_return(ret[dt], factors, sector=sec_d, filed=f,
                                       horizon_days=horizon)
            if np.isfinite(fr):
                rows.append({"date": pd.Timestamp(f), "surprise": float(sv), "fwd": fr})
    return pd.DataFrame(rows, columns=["date", "surprise", "fwd"]).sort_values("date").reset_index(drop=True)
```

- [ ] **Step 4: Run — passes**; **Step 5: Commit** `feat: H2 pooled event collection`

---

## Task 4: Pooled drift estimator

**Files:** Modify `atlas/analysis/event_drift.py`; Test `atlas/tests/test_event_drift.py`

- [ ] **Step 1: Failing tests**

```python
# append to atlas/tests/test_event_drift.py
from analysis.event_drift import event_drift


def _nodes_edges():
    nodes = pd.DataFrame([{"id": "u", "tickers": json.dumps(["U"]), "stage": "chips"},
                          {"id": "d", "tickers": json.dumps(["D"]), "stage": "cloud"}])
    edges = pd.DataFrame([{"from_id": "u", "to_id": "d"}])
    return nodes, edges


def test_event_drift_detects_positive_under_reaction():
    fund = _fund("U", n=28)
    s = capex_surprise(fund, "U", k=4)
    ridx = pd.bdate_range("2015-06-01", periods=3200)
    daily = pd.Series(0.0, index=ridx)
    for f, sv in s.items():
        win = daily.index[daily.index > f][:42]
        daily.loc[win] += 0.0006 * sv                    # drift proportional to surprise
    rng = np.random.default_rng(3)
    daily += 0.0001 * pd.Series(rng.standard_normal(len(ridx)), index=ridx)
    returns = pd.DataFrame({"ticker": "D", "date": ridx, "log_return": daily.to_numpy()})
    factors = {"SPY": pd.Series(0.0, index=ridx), "SOXX": pd.Series(0.0, index=ridx)}
    nodes, edges = _nodes_edges()
    out = event_drift(fund, returns, factors, nodes, edges,
                      horizons=(21, 42, 63), iters=200, seed=1)
    assert out["slope"] > 0
    assert out["n_events"] > 10
    assert out["pos_drift"] > out["neg_drift"]


def test_event_drift_null_for_noise():
    fund = _fund("U", n=28)
    ridx = pd.bdate_range("2015-06-01", periods=3200)
    rng = np.random.default_rng(5)
    returns = pd.DataFrame({"ticker": "D", "date": ridx,
                            "log_return": 0.0002 * rng.standard_normal(len(ridx))})
    factors = {"SPY": pd.Series(0.0, index=ridx), "SOXX": pd.Series(0.0, index=ridx)}
    nodes, edges = _nodes_edges()
    out = event_drift(fund, returns, factors, nodes, edges,
                      horizons=(21, 42, 63), iters=200, seed=2)
    assert out["p_selection"] > 0.1
```

- [ ] **Step 2: Run — fails**
- [ ] **Step 3: Implement** — append:

```python
def _ols_slope_corr(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return np.nan, np.nan
    slope = float(np.polyfit(x, y, 1)[0])
    corr = float(np.corrcoef(x, y)[0, 1])
    return slope, corr


def event_drift(fundamentals, returns, factors, nodes, edges, *,
                horizons, iters: int, seed: int, k: int = 4) -> dict:
    """Pooled capex-surprise -> downstream forward-drift, selection-aware over
    horizons, quarter-block bootstrap CI. Returns a single summary dict."""
    per_h = {h: pooled_events(fundamentals, returns, factors, nodes, edges,
                              horizon=h, k=k) for h in horizons}
    best_h, best_slope, best_corr = None, 0.0, -np.inf
    for h, ev in per_h.items():
        if len(ev) < 10:
            continue
        slope, corr = _ols_slope_corr(ev["surprise"].to_numpy(), ev["fwd"].to_numpy())
        if np.isfinite(corr) and corr > best_corr:
            best_h, best_slope, best_corr = h, slope, corr
    if best_h is None:
        return {"horizon": horizons[0], "slope": np.nan, "slope_lo": np.nan,
                "slope_hi": np.nan, "p_selection": 1.0, "n_events": 0,
                "pos_drift": np.nan, "neg_drift": np.nan, "contradicts_thesis": False}
    ev = per_h[best_h]
    x, y = ev["surprise"].to_numpy(), ev["fwd"].to_numpy()
    # selection-aware over horizons: perturb the surprise vector (block, time-ordered)
    rng = np.random.default_rng(seed)
    count = 0
    for _ in range(iters):
        null_max = -np.inf
        for h, e2 in per_h.items():
            if len(e2) < 10:
                continue
            xb = block_resample_one(e2["surprise"].to_numpy(), block=8, rng=rng)
            _, c = _ols_slope_corr(xb, e2["fwd"].to_numpy())
            if np.isfinite(c):
                null_max = max(null_max, c)
        if null_max >= best_corr:
            count += 1
    p_sel = (count + 1) / (iters + 1)
    lo, hi, _ = bootstrap_slope_ci(x, y, block=8, iters=iters, seed=seed)  # date-sorted -> quarter-ish blocks
    pos = float(np.mean(y[x > 0])) if (x > 0).any() else np.nan
    neg = float(np.mean(y[x < 0])) if (x < 0).any() else np.nan
    return {"horizon": int(best_h), "slope": float(best_slope), "slope_lo": lo, "slope_hi": hi,
            "p_selection": p_sel, "n_events": int(len(ev)),
            "pos_drift": pos, "neg_drift": neg,
            "contradicts_thesis": bool(best_slope < 0)}
```

- [ ] **Step 4: Run — passes**; **Step 5: Commit** `feat: H2 pooled drift estimator with horizon selection`

---

## Task 5: `h2_record` + table + build_signal_records

**Files:** Modify `atlas/analysis/signals.py`, `atlas/analysis/leadlag.py`; Test `atlas/tests/test_signals.py`

- [ ] **Step 1: Failing test** — append to `atlas/tests/test_signals.py`:

```python
from analysis.signals import h2_record


def _h2_row(slope=0.01, q=0.05, neg=False):
    return pd.DataFrame([{"horizon": 42, "slope": slope, "slope_lo": 0.004,
        "slope_hi": 0.02, "p_selection": 0.02, "q_value": q, "n_events": 120,
        "pos_drift": 0.01, "neg_drift": -0.008, "contradicts_thesis": neg}])


def test_h2_confirmed_when_significant_positive_drift():
    assert h2_record(_h2_row(slope=0.01, q=0.05))["verdict"] == "confirmed"


def test_h2_null_when_insignificant():
    assert h2_record(_h2_row(slope=0.001, q=0.8))["verdict"] == "null"
```

- [ ] **Step 2: Run — fails**
- [ ] **Step 3: Implement** — append to `atlas/analysis/signals.py` (reuse `_num`):

```python
def h2_record(rows: pd.DataFrame) -> dict:
    elig = rows[rows["slope"].notna()]
    n = int(elig["n_events"].iloc[0]) if len(elig) else 0
    if not len(elig):
        verdict, best = "null", pd.Series(dtype=float)
    else:
        best = elig.iloc[0]
        q, slope, lo = float(best["q_value"]), float(best["slope"]), float(best["slope_lo"])
        if q <= FDR_ALPHA and slope > 0:
            verdict = "confirmed"
        elif q <= FDR_ALPHA and slope < 0:
            verdict = "contradicts"
        elif slope > 0 and lo > 0:
            verdict = "suggestive"
        else:
            verdict = "null"
    interp = {"confirmed": "under-reaction (drift exists)", "suggestive": "weak drift",
              "null": "no drift (efficient)", "contradicts": "over-reaction / reversal"}[verdict]
    return {
        "id": "H2", "title": "Does a capex surprise drift into downstream returns?",
        "horizon": "weeks (event study)",
        "claim": "An upstream capex surprise predicts downstream forward drift",
        "mechanism": f"Post-announcement under-reaction — verdict: {interp}",
        "verdict": verdict,
        "evidence_chain": [
            {"stage": "drift | positive surprise", "metric": "ret", "value": _num(best.get("pos_drift"))},
            {"stage": "drift | negative surprise", "metric": "ret", "value": _num(best.get("neg_drift"))},
            {"stage": "pooled slope", "metric": "slope", "value": _num(best.get("slope"))},
        ],
        "stat": {"name": "pooled_slope", "value": _num(best.get("slope")),
                 "ci": [_num(best.get("slope_lo")), _num(best.get("slope_hi"))],
                 "q_value": _num(best.get("q_value")), "n": n},
        "caveats": [f"horizon {int(best.get('horizon')) if len(elig) else 0}d; event-clustered (quarter-block bootstrap)",
                    "effective n ≪ event count; observational; no costs"],
        "chart": {"type": "event_drift", "ref": "h2"},
        "detail_rows": elig[["horizon", "slope", "slope_lo", "slope_hi", "q_value",
                             "n_events", "pos_drift", "neg_drift"]].to_dict("records"),
    }
```

In `atlas/analysis/leadlag.py` `run()`, after the H5 (`capex_price`) write:

```python
    from analysis.event_drift import event_drift
    from config import H2_DRIFT_HORIZONS, H2_SURPRISE_K
    h2 = event_drift(fundamentals, returns, _factors, nodes, edges,
                     horizons=H2_DRIFT_HORIZONS, iters=BOOTSTRAP_ITERS,
                     seed=RANDOM_SEED, k=H2_SURPRISE_K)
    import pandas as _pd
    h2df = _pd.DataFrame([h2])
    h2df["q_value"] = h2df["p_selection"]   # single pooled test -> q = p (no multiplicity beyond horizons, already in p)
    con.register("h2t", h2df)
    con.execute("CREATE OR REPLACE TABLE event_drift AS SELECT * FROM h2t")
    con.unregister("h2t")
    print(f"event_drift: pooled slope={h2['slope']:.4f} n={h2['n_events']}")
```

In `build_signal_records`, after the H5 append:

```python
    has_h2 = con.execute("SELECT count(*) FROM information_schema.tables "
                         "WHERE table_name='event_drift'").fetchone()[0] > 0
    if has_h2:
        h2 = con.execute('SELECT * FROM event_drift').df()
        if len(h2):
            records.append(h2_record(h2))
```

- [ ] **Step 4: Run — passes** (`uv run --extra dev python -m pytest tests/test_signals.py tests/test_event_drift.py -v`)
- [ ] **Step 5: Commit** `feat: H2 record + event_drift table`

---

## Task 6: Web card + end-to-end

**Files:** Modify `atlas/web/src/components/SignalCard.svelte`; verification.

- [ ] **Step 1: Add the `event_drift` chart branch** in `SignalCard.svelte`:

```svelte
  {#if signal.chart.type === "event_drift"}
    <ul class="edges">
      {#each signal.detail_rows as r}
        <li><span>+surprise drift {Number(r.pos_drift).toFixed(3)}</span>
          <span>−surprise {Number(r.neg_drift).toFixed(3)}</span>
          <b>slope {Number(r.slope).toFixed(3)}</b>
          <span class="lag">{r.horizon}d · n={r.n_events}</span></li>
      {/each}
    </ul>
  {/if}
```

- [ ] **Step 2:** `npx svelte-check --tsconfig ./tsconfig.json && npm run build` (from `atlas/web/`) — 0 errors.
- [ ] **Step 3: Commit** `feat: H2 event-drift card chart`

- [ ] **Step 4: End-to-end + coverage** (from `atlas/`):

```bash
uv run make analyze
uv run python web/export_data.py --db data/atlas.duckdb --out /tmp/atlas_h2
uv run python -c "import json; r={x['id']:x for x in json.load(open('/tmp/atlas_h2/signals.json'))}; print('H2', r['H2']['verdict'], r['H2']['stat'])"
uv run --extra dev python -m pytest --cov=analysis --cov-report=term-missing tests/test_event_drift.py tests/test_signals.py
uv run --extra dev python -m pytest -q
```
Expected: H2 prints a verdict (likely `null` given H5); `analysis/event_drift.py` ≥ 80%; all suites green. **Report the verdict as-is — do not tune.**

- [ ] **Step 5: Commit** `chore: H2 event-drift verified (verdict: <fill in>)`

---

## Self-Review Notes

- **Reuses** `capex_growth_at_filed`, `forward_excess_return`, `bootstrap_slope_ci`, `block_resample_one`, `bh_fdr`, `_num` — no duplication.
- **PIT** preserved: surprise uses only trailing quarters (`shift(1).rolling(k)`); forward windows open strictly after filing (inside `forward_excess_return`).
- **Event-clustering** handled by date-sorting events and block bootstrap (block 8 ≈ a quarter of pooled events) for both the selection null and the slope CI.
- **Contradicts is significance-gated** (q ≤ 0.10 & slope < 0), consistent with the H5 fix — a near-zero negative slope is null, not a reversal.
- **`h2_record` is single-row** (pooled), unlike H1/H5 per-edge; `n` is the event count.
- **Honest prior:** Null is expected after H5; report it plainly.
