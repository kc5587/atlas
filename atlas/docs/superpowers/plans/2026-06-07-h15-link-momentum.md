# H15 Link-Momentum Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Signal Lab card H15 — does a node's customers' prior-month M2-residual return predict the node's forward M2-residual return (Cohen–Frazzini link momentum)? — and a long-short backtest shown only if the test survives.

**Architecture:** New `analysis/link_momentum.py` builds monthly M2-residual returns (reusing `residualize.residual_for_spec`), a customer→supplier signal panel, a pooled predictability test (slope + block-bootstrap CI + circular-permutation p + BH-FDR + walk-forward OOS sign-rate), and a gated equal-weight L/S backtest. `analysis/leadlag.py::run()` persists one `link_momentum` table; `h15_record` renders it via a new `link_momentum` chart type. H15 adds no edges and triggers no re-ingest, so all H0–H12 records stay byte-identical.

**Tech Stack:** Python 3.13 (pandas, numpy, duckdb, pytest); Svelte 5 + TS frontend.

**Reference spec:** `docs/superpowers/specs/2026-06-07-h15-link-momentum-design.md`

**Env:** venv python at `/Users/kaushalchitturu/Data_Quant_project/atlas/.venv/bin/python`. Work from `/Users/kaushalchitturu/Data_Quant_project/atlas` on a feature branch. Repo root is the parent dir, so `git add` paths are `atlas/...`.

---

## Established facts (do not re-derive)

- **M2 de-beta:** `analysis.residualize.residual_for_spec(asset, factors, *, sector, spec, train_index)` — `factors` is a dict keyed by ETF ticker incl `"SPY"`; `sector` is the sector ETF ticker (e.g. `"SOXX"`/`"IGV"`) or `None`; `spec="M2"` residualizes on SPY + sector-orthogonalized-on-SPY. Betas fit on `train_index` only.
- **Sector map:** `config.STAGE_SECTOR` (stage→sector key) and `config.FACTOR_TICKERS` (`{"market":"SPY","semis":"SOXX","cloud":"IGV"}`). A node's sector ETF = `FACTOR_TICKERS.get(STAGE_SECTOR.get(stage))`; may be `None` for stages without a mapping (eda/foundry→semis is mapped; networking→semis mapped; power/packaging/grid unmapped → `None` → M1 fallback inside `residual_for_spec`).
- **Walk-forward:** `analysis.oos.walk_forward_folds(index, *, test_days, step_days, init_train_frac, embargo)` is position-based → pass a monthly DatetimeIndex with month counts.
- **Permutation helpers:** `analysis.significance.circular_rotate(y, shift)` (autocorr-preserving) and `auto_block_length(x)`.
- **Bootstrap CI:** `analysis.fundamentals_leadlag.bootstrap_slope_ci(x, y, *, block, iters, seed)` → `(lo, hi, point)`.
- **Returns table:** duckdb `returns(ticker, date, log_return)`. **Edges** point supplier→customer; a supplier `S`'s customers = `to_id` of edges `from_id==S`.
- **Record/registration pattern:** analysis tables are persisted in `analysis/leadlag.py::run()` via `CREATE OR REPLACE TABLE`, and `analysis/signals.py::build_signal_records` reads them (guarded by `_has_table`) and appends `hN_record(df)`.

---

## File structure

| File | Responsibility | Action |
|---|---|---|
| `config.py` | H15 constants | Modify |
| `analysis/link_momentum.py` | residual months → panel → predictability → gated backtest | **Create** |
| `analysis/leadlag.py` | `run()` persists `link_momentum` | Modify |
| `analysis/signals.py` | `h15_record` + wiring | Modify |
| `web/src/components/SignalCard.svelte` | `link_momentum` chart block | Modify |
| `tests/test_link_momentum.py` | unit tests | **Create** |
| `tests/test_signals.py` | `h15_record` tests | Modify |

---

## Task 1: Config constants

**Files:** Modify `config.py`; Test `tests/test_link_momentum.py` (created here).

- [ ] **Step 1: Write the failing test**

Create `tests/test_link_momentum.py`:

```python
def test_h15_constants_exist():
    import config
    assert config.H15_MIN_MONTHS == 36
    assert config.H15_OOS_TEST_MONTHS == 12
    assert config.H15_OOS_STEP_MONTHS == 12
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd /Users/kaushalchitturu/Data_Quant_project/atlas && .venv/bin/python -m pytest tests/test_link_momentum.py::test_h15_constants_exist -v`
Expected: FAIL (AttributeError).

- [ ] **Step 3: Add constants**

In `config.py`, after the existing OOS constants block (near `OOS_SIGN_RATE_FLOOR`), add:

```python
# H15 link-momentum: min monthly history per testable node + monthly walk-forward.
H15_MIN_MONTHS = 36
H15_OOS_TEST_MONTHS = 12
H15_OOS_STEP_MONTHS = 12
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_link_momentum.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/kaushalchitturu/Data_Quant_project
git add atlas/config.py atlas/tests/test_link_momentum.py
git commit -m "feat: H15 link-momentum config constants"
```

---

## Task 2: Monthly returns + M2 residual months

**Files:** Create `analysis/link_momentum.py`; Test `tests/test_link_momentum.py`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_link_momentum.py`:

```python
import numpy as np
import pandas as pd

from analysis.link_momentum import monthly_returns, residual_monthly_returns


def test_monthly_returns_sums_daily_logs_per_month():
    dates = pd.date_range("2020-01-01", "2020-02-29", freq="D")
    df = pd.DataFrame({"ticker": "AAA", "date": dates, "log_return": 0.001})
    m = monthly_returns(df)
    # two month-end rows, each ~ (days in month)*0.001
    assert list(m.columns) == ["AAA"]
    assert len(m) == 2
    assert abs(m["AAA"].iloc[0] - 31 * 0.001) < 1e-9


def test_residual_monthly_returns_removes_market_beta():
    idx = pd.date_range("2018-01-31", periods=48, freq="ME")
    rng = np.random.default_rng(0)
    spy = pd.Series(rng.normal(0, 0.04, 48), index=idx)
    # AAA = 1.5*SPY + idiosyncratic noise -> residual must be ~uncorrelated with SPY
    aaa = 1.5 * spy + pd.Series(rng.normal(0, 0.02, 48), index=idx)
    monthly = pd.DataFrame({"AAA": aaa, "SPY": spy, "SOXX": spy * 0.9})
    nodes = pd.DataFrame([{"id": "a", "tickers": '["AAA"]', "stage": "chips"}])
    resid = residual_monthly_returns(monthly, nodes)
    corr = np.corrcoef(resid["AAA"].dropna(), spy.loc[resid["AAA"].dropna().index])[0, 1]
    assert abs(corr) < 0.2
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_link_momentum.py -k "monthly" -v`
Expected: FAIL — module/functions absent.

- [ ] **Step 3: Implement**

Create `analysis/link_momentum.py`:

```python
"""H15: customer -> supplier monthly link momentum (Cohen-Frazzini).

A node's customers' prior-month idiosyncratic (M2-residual) return predicts the
node's forward idiosyncratic return. Pure functions: DataFrame in, dict/DataFrame
out. Uses the FULL graph (returns-based; no fundamentals partition needed).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from config import FACTOR_TICKERS, STAGE_SECTOR
from analysis.residualize import residual_for_spec

FACTOR_ETFS = ("SPY", "SOXX", "IGV")


def monthly_returns(returns: pd.DataFrame) -> pd.DataFrame:
    """Daily log returns -> wide month-end DataFrame (sum of logs), columns=tickers."""
    df = returns.copy()
    df["date"] = pd.to_datetime(df["date"])
    df["month"] = df["date"].dt.to_period("M").dt.to_timestamp("M")
    wide = (df.groupby(["month", "ticker"])["log_return"].sum()
              .unstack("ticker").sort_index())
    return wide


def _sector_etf(stage: str) -> str | None:
    return FACTOR_TICKERS.get(STAGE_SECTOR.get(stage, ""))


def residual_monthly_returns(monthly: pd.DataFrame, nodes: pd.DataFrame) -> pd.DataFrame:
    """M2-residual monthly return per node ticker (betas fit on full sample).

    The fold-specific (train-only) residuals are recomputed inside the OOS loop;
    this full-sample version is the point-estimate input for the pooled test.
    """
    factors = {etf: monthly[etf] for etf in FACTOR_ETFS if etf in monthly.columns}
    stage_of = {}
    for r in nodes.itertuples():
        for t in json.loads(r.tickers):
            stage_of[t] = r.stage
    out = {}
    for ticker in monthly.columns:
        if ticker in FACTOR_ETFS or ticker not in stage_of:
            continue
        sector = _sector_etf(stage_of[ticker])
        sec = sector if (sector and sector in factors) else None
        out[ticker] = residual_for_spec(
            monthly[ticker], factors, sector=sec, spec="M2",
            train_index=monthly.index,
        )
    return pd.DataFrame(out)
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_link_momentum.py -k "monthly" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/kaushalchitturu/Data_Quant_project
git add atlas/analysis/link_momentum.py atlas/tests/test_link_momentum.py
git commit -m "feat: H15 monthly returns + M2 residual months"
```

---

## Task 3: Customer→supplier signal panel

**Files:** Modify `analysis/link_momentum.py`; Test `tests/test_link_momentum.py`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_link_momentum.py`:

```python
from analysis.link_momentum import link_signal_panel

_NODES = pd.DataFrame([
    {"id": "nvidia", "tickers": '["NVDA"]', "stage": "chips"},
    {"id": "microsoft", "tickers": '["MSFT"]', "stage": "cloud"},
    {"id": "meta", "tickers": '["META"]', "stage": "cloud"},
])
_EDGES = pd.DataFrame([
    {"from_id": "nvidia", "to_id": "microsoft", "relationship": "supplies"},
    {"from_id": "nvidia", "to_id": "meta", "relationship": "supplies"},
])


def test_link_signal_panel_builds_customer_signal_and_forward_target():
    idx = pd.date_range("2020-01-31", periods=6, freq="ME")
    resid = pd.DataFrame({
        "NVDA": [0.0, 0.1, 0.2, -0.1, 0.05, 0.0],
        "MSFT": [0.02, 0.04, -0.01, 0.03, 0.0, 0.01],
        "META": [0.00, 0.02, 0.01, 0.05, 0.0, -0.02],
    }, index=idx)
    panel = link_signal_panel(resid, _NODES, _EDGES, min_months=3)
    # supplier is NVDA; signal = mean(MSFT,META) at t; target = NVDA at t+1
    row = panel[(panel["node"] == "nvidia") & (panel["month"] == idx[0])].iloc[0]
    assert abs(row["signal"] - np.mean([0.02, 0.00])) < 1e-9
    assert abs(row["fwd_target"] - 0.1) < 1e-9  # NVDA at t+1
    # last month has no t+1 target -> dropped
    assert panel["month"].max() < idx[-1]
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_link_momentum.py -k panel -v`
Expected: FAIL — `link_signal_panel` absent.

- [ ] **Step 3: Implement**

Append to `analysis/link_momentum.py`:

```python
def _ticker_of(nodes: pd.DataFrame, node_id: str) -> str | None:
    row = nodes.loc[nodes["id"] == node_id]
    if row.empty:
        return None
    return json.loads(row["tickers"].iloc[0])[0]


def link_signal_panel(resid: pd.DataFrame, nodes: pd.DataFrame, edges: pd.DataFrame,
                      *, min_months: int) -> pd.DataFrame:
    """Long panel [node, month, signal, fwd_target] for customer->supplier links.

    signal[S,t] = equal-weight mean of S's customers' residual return at t.
    fwd_target[S,t] = S's residual return at t+1.
    Suppliers need >= min_months of overlapping observations to be included.
    """
    rows = []
    for sup in nodes["id"]:
        st = _ticker_of(nodes, sup)
        if st is None or st not in resid.columns:
            continue
        customers = edges.loc[edges["from_id"] == sup, "to_id"]
        ct = [t for t in (_ticker_of(nodes, c) for c in customers) if t and t in resid.columns]
        if not ct:
            continue
        sig = resid[ct].mean(axis=1)
        tgt = resid[st].shift(-1)  # t+1
        paired = pd.concat([sig.rename("signal"), tgt.rename("fwd_target")],
                           axis=1).dropna()
        if len(paired) < min_months:
            continue
        for month, r in paired.iterrows():
            rows.append({"node": sup, "month": month,
                         "signal": float(r["signal"]), "fwd_target": float(r["fwd_target"])})
    return pd.DataFrame(rows, columns=["node", "month", "signal", "fwd_target"])
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_link_momentum.py -k panel -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/kaushalchitturu/Data_Quant_project
git add atlas/analysis/link_momentum.py atlas/tests/test_link_momentum.py
git commit -m "feat: H15 customer->supplier signal panel"
```

---

## Task 4: Predictability test (slope + CI + permutation p + FDR + OOS)

**Files:** Modify `analysis/link_momentum.py`; Test `tests/test_link_momentum.py`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_link_momentum.py`:

```python
from analysis.link_momentum import link_predictability


def _panel_with_signal(beta, n_nodes=8, n_months=60, noise=0.02, seed=0):
    rng = np.random.default_rng(seed)
    months = pd.date_range("2016-01-31", periods=n_months, freq="ME")
    rows = []
    for k in range(n_nodes):
        sig = rng.normal(0, 0.03, n_months)
        tgt = beta * sig + rng.normal(0, noise, n_months)
        for i, m in enumerate(months):
            rows.append({"node": f"n{k}", "month": m,
                         "signal": sig[i], "fwd_target": tgt[i]})
    return pd.DataFrame(rows)


def test_link_predictability_detects_positive_slope():
    out = link_predictability(_panel_with_signal(0.5), iters=300, seed=1)
    assert out["slope"] > 0
    assert out["p_value"] < 0.05
    assert 0.0 <= out["oos_sign_rate"] <= 1.0
    assert out["n_obs"] == 8 * 60


def test_link_predictability_null_on_noise():
    out = link_predictability(_panel_with_signal(0.0), iters=300, seed=2)
    assert out["p_value"] > 0.05
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_link_momentum.py -k predictability -v`
Expected: FAIL — `link_predictability` absent.

- [ ] **Step 3: Implement**

Append to `analysis/link_momentum.py`:

```python
from analysis.fundamentals_leadlag import bootstrap_slope_ci
from analysis.oos import walk_forward_folds
from analysis.significance import auto_block_length, circular_rotate
from config import (
    BOOTSTRAP_ITERS, FDR_ALPHA, H15_OOS_STEP_MONTHS, H15_OOS_TEST_MONTHS,
    OOS_SIGN_RATE_FLOOR, RANDOM_SEED,
)


def _pooled_slope(signal: np.ndarray, target: np.ndarray) -> float:
    if len(signal) < 3 or np.std(signal) == 0:
        return float("nan")
    return float(np.polyfit(signal, target, 1)[0])


def _oos_sign_rate(panel: pd.DataFrame) -> tuple[float, int]:
    """Walk-forward (monthly): sign agreement of train vs test pooled slope."""
    months = pd.DatetimeIndex(sorted(panel["month"].unique()))
    if len(months) < 2 * H15_OOS_TEST_MONTHS:
        return 0.0, 0
    folds = walk_forward_folds(
        months, test_days=H15_OOS_TEST_MONTHS, step_days=H15_OOS_STEP_MONTHS,
        init_train_frac=0.5, embargo=0,
    )
    signs = []
    for train_idx, test_idx in folds:
        tr = panel[panel["month"].isin(set(train_idx))]
        te = panel[panel["month"].isin(set(test_idx))]
        bt = _pooled_slope(tr["signal"].to_numpy(), tr["fwd_target"].to_numpy())
        bv = _pooled_slope(te["signal"].to_numpy(), te["fwd_target"].to_numpy())
        if np.isfinite(bt) and np.isfinite(bv) and bt != 0:
            signs.append(np.sign(bt) == np.sign(bv))
    return (float(np.mean(signs)) if signs else 0.0), len(signs)


def link_predictability(panel: pd.DataFrame, *, iters: int = BOOTSTRAP_ITERS,
                        seed: int = RANDOM_SEED) -> dict:
    """Pooled slope of fwd_target ~ signal with bootstrap CI, circular-permutation
    p (rotate each node's signal series, preserving autocorrelation), and a
    monthly walk-forward OOS sign-rate."""
    if panel.empty:
        return {"slope": float("nan"), "slope_lo": float("nan"), "slope_hi": float("nan"),
                "p_value": 1.0, "q_value": 1.0, "oos_sign_rate": 0.0,
                "n_obs": 0, "n_nodes": 0, "n_months": 0, "n_folds": 0}
    sig = panel["signal"].to_numpy()
    tgt = panel["fwd_target"].to_numpy()
    obs = _pooled_slope(sig, tgt)
    lo, hi, _ = bootstrap_slope_ci(sig, tgt, block=auto_block_length(tgt),
                                   iters=iters, seed=seed)
    rng = np.random.default_rng(seed)
    null = []
    for _ in range(iters):
        perm = panel.copy()
        parts = []
        for _, grp in perm.groupby("node", sort=False):
            shift = int(rng.integers(1, max(2, len(grp))))
            g = grp.copy()
            g["signal"] = circular_rotate(g["signal"].to_numpy(), shift)
            parts.append(g)
        pp = pd.concat(parts)
        null.append(_pooled_slope(pp["signal"].to_numpy(), pp["fwd_target"].to_numpy()))
    null = np.array([v for v in null if np.isfinite(v)])
    p = float((np.sum(null >= obs) + 1) / (len(null) + 1)) if obs > 0 else \
        float((np.sum(np.abs(null) >= abs(obs)) + 1) / (len(null) + 1))
    sign_rate, n_folds = _oos_sign_rate(panel)
    return {
        "slope": obs, "slope_lo": float(lo), "slope_hi": float(hi),
        "p_value": p, "q_value": p,  # single declared hypothesis -> q == p
        "oos_sign_rate": sign_rate,
        "n_obs": int(len(panel)), "n_nodes": int(panel["node"].nunique()),
        "n_months": int(panel["month"].nunique()), "n_folds": n_folds,
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_link_momentum.py -k predictability -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/kaushalchitturu/Data_Quant_project
git add atlas/analysis/link_momentum.py atlas/tests/test_link_momentum.py
git commit -m "feat: H15 pooled predictability test (CI + permutation p + OOS)"
```

---

## Task 5: Gated long-short backtest

**Files:** Modify `analysis/link_momentum.py`; Test `tests/test_link_momentum.py`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_link_momentum.py`:

```python
from analysis.link_momentum import link_backtest


def test_link_backtest_profits_when_signal_predicts():
    # signal sign predicts next-month raw return -> positive Sharpe
    rng = np.random.default_rng(0)
    months = pd.date_range("2016-01-31", periods=48, freq="ME")
    raw = {}
    rows = []
    for k in range(6):
        sig = rng.choice([-1.0, 1.0], 48) * 0.02
        ret = np.concatenate([[0.0], (np.sign(sig) * 0.03 + rng.normal(0, 0.01, 48))[:-1]])
        raw[f"T{k}"] = pd.Series(ret, index=months)
        for i, m in enumerate(months[:-1]):
            rows.append({"node": f"n{k}", "ticker": f"T{k}", "month": m,
                         "signal": sig[i], "fwd_target": ret[i + 1]})
    panel = pd.DataFrame(rows)
    raw_wide = pd.DataFrame(raw)
    out = link_backtest(panel, raw_wide)
    assert out["sharpe"] > 0
    assert out["n_months_bt"] > 10
    assert -1.0 <= out["max_drawdown"] <= 0.0
```

The backtest trades **raw** forward returns (looked up from `raw_monthly`, not the panel's residual `fwd_target`), and returns `n_months_bt` (not `n_months`) so it does not collide with the predictability `n_months` when the two dicts are merged in Task 6.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/test_link_momentum.py -k backtest -v`
Expected: FAIL — `link_backtest` absent.

- [ ] **Step 3: Implement**

The panel needs the supplier's own ticker to look up its raw forward return. Update `link_signal_panel` to also emit `ticker` (the supplier ticker), then add the backtest.

First, in `link_signal_panel`, change the appended row dict to include the ticker:

```python
            rows.append({"node": sup, "ticker": st, "month": month,
                         "signal": float(r["signal"]), "fwd_target": float(r["fwd_target"])})
```

and update its `columns=` to `["node", "ticker", "month", "signal", "fwd_target"]`. (Adjust the Task 3 panel test if it asserts column order — it does not.)

Then append to `analysis/link_momentum.py`:

```python
def _max_drawdown(equity: np.ndarray) -> float:
    peak = np.maximum.accumulate(equity)
    dd = equity / peak - 1.0
    return float(dd.min()) if len(dd) else 0.0


def link_backtest(panel: pd.DataFrame, raw_monthly: pd.DataFrame) -> dict:
    """Equal-weight sign-based L/S of supplier RAW forward returns, monthly.

    Each month t: long suppliers with signal>0, short signal<0; the realized
    return is the supplier's RAW return over t->t+1 (looked up from raw_monthly,
    not the panel's residual fwd_target). Gross of costs.
    """
    raw_fwd = raw_monthly.shift(-1)  # raw return over t->t+1, indexed at t
    months = pd.DatetimeIndex(sorted(panel["month"].unique()))
    port = []
    for m in months:
        if m not in raw_fwd.index:
            continue
        cur = panel[panel["month"] == m]
        longs, shorts = [], []
        for row in cur.itertuples():
            tk = row.ticker
            if tk not in raw_fwd.columns:
                continue
            fr = raw_fwd.at[m, tk]
            if not np.isfinite(fr) or row.signal == 0:
                continue
            (longs if row.signal > 0 else shorts).append(float(fr))
        if not longs and not shorts:
            continue
        r = (np.mean(longs) if longs else 0.0) - (np.mean(shorts) if shorts else 0.0)
        port.append((m, float(r)))
    if len(port) < 6:
        return {"sharpe": float("nan"), "ann_return": float("nan"),
                "ann_vol": float("nan"), "alpha": float("nan"), "t_stat": float("nan"),
                "max_drawdown": 0.0, "n_months_bt": len(port)}
    pr = pd.Series([r for _, r in port], index=[m for m, _ in port])
    ann_return = float(pr.mean() * 12)
    ann_vol = float(pr.std(ddof=1) * np.sqrt(12))
    sharpe = float(ann_return / ann_vol) if ann_vol > 0 else float("nan")
    # alpha vs available factor ETFs (Newey-West lag 3), if present in raw_monthly
    etfs = [e for e in FACTOR_ETFS if e in raw_monthly.columns]
    alpha, t_stat = _alpha_tstat(pr, raw_monthly[etfs]) if etfs else (float("nan"), float("nan"))
    equity = (1.0 + pr).cumprod().to_numpy()
    return {"sharpe": sharpe, "ann_return": ann_return, "ann_vol": ann_vol,
            "alpha": alpha, "t_stat": t_stat,
            "max_drawdown": _max_drawdown(equity), "n_months_bt": int(len(pr))}


def _alpha_tstat(port: pd.Series, factors: pd.DataFrame, *, nw_lag: int = 3) -> tuple[float, float]:
    df = pd.concat([port.rename("p"), factors], axis=1, join="inner").dropna()
    if len(df) < 12:
        return float("nan"), float("nan")
    y = df["p"].to_numpy()
    X = np.column_stack([np.ones(len(df)), df[factors.columns].to_numpy()])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    n, k = X.shape
    XtX_inv = np.linalg.inv(X.T @ X)
    # Newey-West HAC covariance
    S = (resid[:, None] * X).T @ (resid[:, None] * X)
    for L in range(1, nw_lag + 1):
        w = 1.0 - L / (nw_lag + 1)
        G = (resid[L:, None] * X[L:]).T @ (resid[:-L, None] * X[:-L])
        S += w * (G + G.T)
    cov = XtX_inv @ S @ XtX_inv
    alpha = float(beta[0])
    se = float(np.sqrt(cov[0, 0]))
    return alpha * 12, (alpha / se if se > 0 else float("nan"))
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/test_link_momentum.py -v`
Expected: PASS (all link_momentum tests, including the updated panel test).

- [ ] **Step 5: Commit**

```bash
cd /Users/kaushalchitturu/Data_Quant_project
git add atlas/analysis/link_momentum.py atlas/tests/test_link_momentum.py
git commit -m "feat: H15 gated long-short backtest (Sharpe, NW alpha, max DD)"
```

---

## Task 6: Wire into `run()` — compute + persist `link_momentum`

**Files:** Modify `analysis/leadlag.py` (`run()`, near the H12 block ~line 560).

`run()` is `# pragma: no cover`; verified by the pipeline in Task 9.

- [ ] **Step 1: Add the H15 block**

In `analysis/leadlag.py`, after the `networking_pricing` persistence block (the `print(f"networking_pricing: ...")` line), insert:

```python
    from analysis.link_momentum import (
        monthly_returns, residual_monthly_returns, link_signal_panel,
        link_predictability, link_backtest,
    )
    from config import H15_MIN_MONTHS
    _monthly = monthly_returns(returns)
    _resid_m = residual_monthly_returns(_monthly, nodes)
    _panel = link_signal_panel(_resid_m, nodes, edges, min_months=H15_MIN_MONTHS)
    _pred = link_predictability(_panel, iters=BOOTSTRAP_ITERS, seed=RANDOM_SEED)
    # Backtest is GATED: only run it if the test is at least suggestive (slope>0
    # and CI lower bound > 0). A null card carries no backtest.
    _gated = (_pred["slope"] > 0) and (_pred["slope_lo"] > 0)
    _bt = link_backtest(_panel, _monthly) if _gated else {}
    h15 = pd.DataFrame([{**_pred, **_bt, "gated": bool(_gated)}])
    con.register("h15t", h15)
    con.execute("CREATE OR REPLACE TABLE link_momentum AS SELECT * FROM h15t")
    con.unregister("h15t")
    print(f"link_momentum: slope={_pred['slope']:.4f} p={_pred['p_value']:.3f} "
          f"oos={_pred['oos_sign_rate']:.2f} gated={_gated}")
```

(`returns`, `nodes`, `edges`, `BOOTSTRAP_ITERS`, `RANDOM_SEED` are already in scope.)

- [ ] **Step 2: Sanity-compile**

Run: `.venv/bin/python -c "import analysis.leadlag"`
Expected: imports cleanly.

- [ ] **Step 3: Commit**

```bash
cd /Users/kaushalchitturu/Data_Quant_project
git add atlas/analysis/leadlag.py
git commit -m "feat: compute + persist link_momentum (H15) in analysis run()"
```

---

## Task 7: `h15_record` + wire into `build_signal_records`

**Files:** Modify `analysis/signals.py`; Test `tests/test_signals.py`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_signals.py`:

```python
def test_h15_record_confirmed_includes_backtest():
    from analysis.signals import h15_record
    row = pd.DataFrame([{
        "slope": 0.12, "slope_lo": 0.03, "slope_hi": 0.21, "p_value": 0.01,
        "q_value": 0.01, "oos_sign_rate": 0.72, "n_obs": 480, "n_nodes": 8,
        "n_months": 60, "n_folds": 4, "gated": True,
        "sharpe": 0.9, "ann_return": 0.11, "ann_vol": 0.12, "alpha": 0.08,
        "t_stat": 2.3, "max_drawdown": -0.18, "n_months_bt": 48,
    }])
    rec = h15_record(row)
    assert rec["id"] == "H15"
    assert rec["verdict"] == "confirmed"
    assert rec["chart"]["type"] == "link_momentum"
    assert any("sharpe" in str(d).lower() or "Sharpe" in str(d) for d in [rec["detail_rows"]])


def test_h15_record_null_has_no_backtest_row():
    from analysis.signals import h15_record
    row = pd.DataFrame([{
        "slope": 0.01, "slope_lo": -0.05, "slope_hi": 0.07, "p_value": 0.6,
        "q_value": 0.6, "oos_sign_rate": 0.5, "n_obs": 400, "n_nodes": 8,
        "n_months": 55, "n_folds": 4, "gated": False,
    }])
    rec = h15_record(row)
    assert rec["verdict"] == "null"
    assert rec["detail_rows"] == []
```

- [ ] **Step 2: Run to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_signals.py -k h15 -v`
Expected: FAIL — `h15_record` absent.

- [ ] **Step 3: Implement `h15_record`**

Add to `analysis/signals.py` (near the other record builders). Uses the existing `FDR_ALPHA`, `OOS_SIGN_FLOOR`, `_num` already in the module:

```python
def h15_record(rows: pd.DataFrame) -> dict:
    r = rows.iloc[0]
    slope = float(r["slope"]) if pd.notna(r["slope"]) else float("nan")
    q = float(r["q_value"]) if pd.notna(r["q_value"]) else 1.0
    oos = float(r["oos_sign_rate"]) if pd.notna(r["oos_sign_rate"]) else 0.0
    lo = float(r["slope_lo"]) if pd.notna(r["slope_lo"]) else float("nan")
    if slope > 0 and q <= FDR_ALPHA and oos >= OOS_SIGN_FLOOR:
        verdict = "confirmed"
    elif slope > 0 and lo > 0:
        verdict = "suggestive"
    elif slope < 0 and q <= FDR_ALPHA:
        verdict = "contradicts"
    else:
        verdict = "null"
    gated = bool(r.get("gated", False)) and verdict in ("confirmed", "suggestive")
    detail = []
    if gated:
        detail = [{
            "sharpe": _num(r.get("sharpe")), "ann_return": _num(r.get("ann_return")),
            "ann_vol": _num(r.get("ann_vol")), "alpha": _num(r.get("alpha")),
            "t_stat": _num(r.get("t_stat")), "max_drawdown": _num(r.get("max_drawdown")),
            "n_months": int(r.get("n_months_bt") or r.get("n_months") or 0),
        }]
    return {
        "id": "H15", "title": "Does customer news diffuse to suppliers?",
        "horizon": "1 month",
        "claim": "A node's customers' prior-month return predicts its forward return",
        "mechanism": "Limited attention: suppliers under-react to customer news (Cohen-Frazzini)",
        "verdict": verdict,
        "evidence_chain": [
            {"stage": "predictor", "metric": "customers' prior-month resid return", "value": _num(slope)},
            {"stage": "de-beta", "metric": "M2 residual (market + sector)", "value": _num(slope)},
            {"stage": "OOS sign-rate", "metric": "walk-forward", "value": _num(oos, 2)},
        ],
        "stat": {"name": "slope", "value": _num(slope),
                 "ci": [_num(lo), _num(r.get("slope_hi"))],
                 "q_value": _num(q), "n": int(r.get("n_obs") or 0)},
        "caveats": [
            f"{int(r.get('n_nodes') or 0)} suppliers x {int(r.get('n_months') or 0)} months; small cross-section",
            "Backtest (if shown) is GROSS of costs/turnover/borrow; equal-weight; 1-month horizon",
            "De-beta'd M2 returns -> not the H0 sector beta",
        ],
        "chart": {"type": "link_momentum", "ref": "h15"},
        "detail_rows": detail,
    }
```

If `OOS_SIGN_FLOOR` is not the exact constant name in `analysis/signals.py`, grep for the existing sign-floor constant (it is used by `h0_record`) and use that name.

- [ ] **Step 4: Wire into `build_signal_records`**

In `analysis/signals.py::build_signal_records`, next to the other guarded blocks, add:

```python
        if _has_table(con, "link_momentum"):
            h15 = con.execute('SELECT * FROM link_momentum').df()
            records.append(h15_record(h15))
```

- [ ] **Step 5: Run to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_signals.py -v`
Expected: PASS (h15 tests + existing).

- [ ] **Step 6: Commit**

```bash
cd /Users/kaushalchitturu/Data_Quant_project
git add atlas/analysis/signals.py atlas/tests/test_signals.py
git commit -m "feat: h15_record + wire into build_signal_records"
```

---

## Task 8: Frontend `link_momentum` chart block

**Files:** Modify `web/src/components/SignalCard.svelte`.

The H15 card reuses the standard header/claim/mechanism/stat/caveats (already rendered generically). Add a chart block that shows the predictability stat line and, when `detail_rows` is non-empty, the backtest summary.

- [ ] **Step 1: Read the component** to find where other `{#if signal.chart.type === "..."}` blocks live.

Run: `cd /Users/kaushalchitturu/Data_Quant_project/atlas && grep -n 'chart.type ===' web/src/components/SignalCard.svelte`

- [ ] **Step 2: Add the H15 block**

After the last existing `{#if signal.chart.type === "..."}` block in `web/src/components/SignalCard.svelte`, add:

```svelte
  {#if signal.chart.type === "link_momentum"}
    <p class="legend">Customers' prior-month residual return → supplier forward return (M2 de-beta'd, walk-forward)</p>
    {#if signal.detail_rows.length}
      <ul class="edges">
        {#each signal.detail_rows as r}
          <li><span>L/S backtest (gross)</span>
            <b>Sharpe {Number(r.sharpe).toFixed(2)}</b>
            <span class="ci">α {Number(r.alpha).toFixed(3)} (t {Number(r.t_stat).toFixed(1)})</span>
            <span class="lag">maxDD {Number(r.max_drawdown).toFixed(2)} · {r.n_months}m</span></li>
        {/each}
      </ul>
    {:else}
      <p class="legend">No tradeable edge (test did not survive) — backtest withheld.</p>
    {/if}
  {/if}
```

- [ ] **Step 3: Build to verify it compiles**

Run: `cd /Users/kaushalchitturu/Data_Quant_project/atlas/web && npm run build`
Expected: build succeeds.

- [ ] **Step 4: Run web unit tests**

Run: `cd /Users/kaushalchitturu/Data_Quant_project/atlas/web && npm run test`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/kaushalchitturu/Data_Quant_project
git add atlas/web/src/components/SignalCard.svelte
git commit -m "feat: link_momentum (H15) chart block in SignalCard"
```

---

## Task 9: Pipeline regen + H0–H12 byte-identical gate + verify

**Files:** none (regeneration + verification).

- [ ] **Step 1: Snapshot H0–H12 baseline**

Run:
```bash
cd /Users/kaushalchitturu/Data_Quant_project/atlas
.venv/bin/python -c "
import json
s=json.load(open('web/static/data/signals.json'))
base={r['id']:r for r in s if r['id']!='H15'}
json.dump(base, open('/tmp/h0_h12.before.json','w'), sort_keys=True, indent=2)
print('baseline saved:', sorted(base))
"
```

- [ ] **Step 2: Re-run analysis + export (NO re-ingest — H15 uses existing returns)**

Run:
```bash
cd /Users/kaushalchitturu/Data_Quant_project/atlas
.venv/bin/python -m analysis.leadlag 2>&1 | grep -iE "link_momentum|wrote|error"
.venv/bin/python web/export_data.py --db data/atlas.duckdb --out web/static/data
```
Expected: prints the `link_momentum: slope=... p=... oos=... gated=...` line; export succeeds.

- [ ] **Step 3: H0–H12 REGRESSION GATE (hard stop)**

Run:
```bash
cd /Users/kaushalchitturu/Data_Quant_project/atlas && .venv/bin/python -c "
import json
s={r['id']:r for r in json.load(open('web/static/data/signals.json'))}
before=json.load(open('/tmp/h0_h12.before.json'))
diffs=[k for k in before if json.dumps(s[k],sort_keys=True)!=json.dumps(before[k],sort_keys=True)]
assert not diffs, f'CHANGED: {diffs}'
print('H0-H12 UNCHANGED ✓')
"
```
Expected: `H0-H12 UNCHANGED ✓`. **If any card changed, STOP** — H15 is supposed to be additive (it adds no edges and re-ingests nothing). Investigate before continuing.

- [ ] **Step 4: Report H15 verdict (as produced)**

Run:
```bash
cd /Users/kaushalchitturu/Data_Quant_project/atlas && .venv/bin/python -c "
import json
h=next(r for r in json.load(open('web/static/data/signals.json')) if r['id']=='H15')
print('H15 verdict:', h['verdict'], '| slope', h['stat']['value'], 'q', h['stat']['q_value'], 'n', h['stat']['n'])
print('backtest shown:', bool(h['detail_rows']), h['detail_rows'])
"
```
Expected: prints the verdict — report it exactly (likely null given the small sample; confirmed/suggestive would show a backtest). Do not tune anything to change it.

- [ ] **Step 5: Full suites + lint + build**

Run:
```bash
cd /Users/kaushalchitturu/Data_Quant_project/atlas && .venv/bin/python -m pytest -q 2>&1 | tail -1 && .venv/bin/ruff check . && cd web && npm run test 2>&1 | grep -E "Tests " && npm run build 2>&1 | tail -2
```
Expected: all green.

- [ ] **Step 6: Commit any tracked changes**

```bash
cd /Users/kaushalchitturu/Data_Quant_project
git add -A atlas && git commit -m "chore: regenerate for H15 link-momentum" || echo "nothing tracked (web/static/data gitignored)"
```

---

## Self-review notes (for the executor)

- **Spec coverage:** §2 universe/direction → Tasks 3,6; §3 predictability (M2 de-beta, slope, CI, permutation p, FDR, OOS) → Tasks 2,4; §4 gated backtest → Tasks 5,6; §5 code/frontend → Tasks 2–8; §6 testing + additive gate → Tasks 4,5,7,9; §7 non-goals respected (no costs, 1-month, customer→supplier, no equity SVG).
- **Gating lives in two places, intentionally:** `run()` only computes the backtest when slope>0 & lo>0 (Task 6), and `h15_record` only emits the backtest detail row when `gated` AND verdict∈{confirmed,suggestive} (Task 7). Both guard the same invariant.
- **Likely outcome is null** (small cross-section). That is a valid, valuable result — report it; the card simply shows no backtest.
- **Confirmed:** `OOS_SIGN_FLOOR = 0.6` is defined in `analysis/signals.py:11` (used by the H0 family) — `h15_record` reuses it directly. `FDR_ALPHA` and `_num` are likewise already in that module.
- **Confirmed:** the backtest's `n_months_bt` key does not collide with the predictability `n_months` when merged in Task 6; `h15_record` reads `n_months_bt` for the backtest row.
- **`web/static/data` is gitignored** — Task 9 Step 6 no-ops on it.
- **Newey–West alpha** uses factor ETFs present in the monthly frame (SPY/SOXX/IGV); if only SPY is present it degrades to a 1-factor alpha — acceptable.
