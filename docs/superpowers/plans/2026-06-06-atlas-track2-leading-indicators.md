# Atlas Track 2 — Leading Indicators Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. **Phase 2 runs via Codex CLI (gpt-5.4)** per the user's model-routing rules: strict TDD (RED→GREEN), per-task path-scoped commits, reuse existing thresholds, report verdicts honestly with NO tuning, do NOT push.

**Goal:** Add two Signal Lab cards — **H8** (chip-cycle leading indicators lead chip-maker revenue; economic) and **H4** (that same cycle is priced into semis equity returns; efficiency) — from free FRED series, reusing the existing macro ingest.

**Architecture:** Add FRED indicator ids to `config.FRED_SERIES` (no new ingest module — `ingest/macro.py` + dbt `macro_daily` already expose them). Two pure-function analysis modules (`analysis/leading_indicators.py` for H8, `analysis/macro_sector.py` for H4) compute the tables; `analysis/leadlag.py::run()` writes `leading_revenue`/`macro_sector` to DuckDB; `analysis/signals.py` turns them into card records; `SignalCard.svelte` renders two chart types. Each indicator is YoY-growth-transformed and publication-lagged (point-in-time guard). H8 uses effect-size + bootstrap CI + FDR (small quarterly sample, no walk-forward, like H1); H4 uses monthly walk-forward + selection-aware FDR (like H5/H7).

**Tech Stack:** Python 3.13, pandas, numpy, duckdb, dbt-duckdb, pytest. Run via `uv run` from `atlas/`.

**Non-negotiables:** reuse `FDR_ALPHA=0.10`, `OOS_SIGN_RATE_FLOOR=0.6`, `RANDOM_SEED`, `BOOTSTRAP_ITERS`, the single-series perturbation null, `bh_fdr`, `bootstrap_slope_ci`, `walk_forward_folds`, and the generic `vol_termstructure` time-series helpers — **invent no new thresholds**. Report verdicts exactly as produced.

---

## Reference: existing signatures this plan reuses (do not redefine)

- `analysis/fundamentals_leadlag.py`: `yoy_growth(level: pd.Series) -> pd.Series` (4-quarter log diff); `bootstrap_slope_ci(x, y, *, block, iters, seed, ci=0.90) -> (lo, hi, point)`.
- `analysis/significance.py`: `block_resample_one(y, *, block, rng)`; `auto_block_length(x, *, fallback=BOOTSTRAP_BLOCK)`.
- `analysis/leadlag.py`: `bh_fdr(pvals: np.ndarray) -> np.ndarray`; orchestrator `run()`.
- `analysis/oos.py`: `walk_forward_folds(index, *, test_days, step_days, init_train_frac, embargo)`.
- `analysis/vol_termstructure.py` (GENERIC time-series helpers, reused by H4): `aligned_forward(slope: pd.Series, log_return: pd.Series, *, horizon) -> (x, y)` (pairs s_t with summed forward return over the next `horizon` index steps); `selection_pvalue_one_series(x, y, *, iters, seed)` (one-sided positive single-series block-resample p); `oos_sign_rate(slope, log_return, *, horizon, test_days, step_days, init_train_frac)`; `_corr_slope(x, y) -> (corr, slope)`.
- `analysis/signals.py`: `FDR_ALPHA=0.10`, `OOS_SIGN_FLOOR=0.6`, `_num(x, ndigits=3)`; record builders are pure (DataFrame → dict); `build_signal_records(con)` presence-guards each table.
- `analysis/leadlag.py::run()` already loads: `returns(ticker,date,log_return)`, `macro(series_id,date,value)` from `macro_daily`, `fundamentals(ticker,period_end,filed,revenue,capex,gross_margin)` from `fundamentals_quarterly`.

---

## File Structure

**New files**
- `atlas/analysis/leading_indicators.py` — H8 pure functions + `leading_revenue_table`.
- `atlas/analysis/macro_sector.py` — H4 pure functions + `macro_sector_table`.
- `atlas/tests/test_leading_indicators.py`, `atlas/tests/test_macro_sector.py`.

**Modified files**
- `atlas/config.py` — `FRED_SERIES` additions + `LEADING_INDICATORS`, `SEMIS_REVENUE_NAMES`, `H8_LEAD_QUARTERS`, `H4_HORIZON_MONTHS`, `INDICATOR_PUB_LAG_MONTHS`.
- `atlas/analysis/signals.py` — `h8_record`, `h4_record`, wire into `build_signal_records`.
- `atlas/analysis/leadlag.py` — compute + write `leading_revenue`, `macro_sector` in `run()`.
- `atlas/web/src/components/SignalCard.svelte` — `leading_revenue`, `macro_sector` chart blocks.
- `atlas/tests/test_signals.py` — H8/H4 record tests.

---

## Conventions

- Work in `atlas/`. Tests: `uv run pytest <path> -v`. Commit only the paths a task touches. Commit format `<type>: <desc>` (no attribution).
- Pure functions: DataFrame/Series in → DataFrame/dict out. No DuckDB reads inside pure functions.

---

## Phase 0 — Config

### Task 1: Config constants

**Files:**
- Modify: `atlas/config.py`
- Test: `atlas/tests/test_leading_indicators.py`

- [ ] **Step 1: Write the failing test**

```python
# atlas/tests/test_leading_indicators.py
def test_config_track2_constants():
    import config
    # leading-indicator FRED ids are present in FRED_SERIES and in LEADING_INDICATORS
    for sid in ("XTEXVA01KRM664S", "IPG3344S", "CAPUTLG3344S", "PCU334413334413", "A34SNO"):
        assert sid in config.FRED_SERIES
        assert sid in config.LEADING_INDICATORS
    assert config.SEMIS_REVENUE_NAMES == ["AMAT", "LRCX", "NVDA", "AMD", "AVGO", "MU"]
    assert config.H8_LEAD_QUARTERS == (1, 2)
    assert config.H4_HORIZON_MONTHS == (1, 2, 3)
    # every indicator has a publication lag (months)
    for sid in config.LEADING_INDICATORS:
        assert config.INDICATOR_PUB_LAG_MONTHS[sid] >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_leading_indicators.py::test_config_track2_constants -v`
Expected: FAIL (`AttributeError: module 'config' has no attribute 'LEADING_INDICATORS'`).

- [ ] **Step 3: Write minimal implementation**

In `atlas/config.py`, extend the existing `FRED_SERIES` dict with the four new ids (keep `IPG3344S`), then append the Track 2 block:

```python
# (extend the existing FRED_SERIES dict — keep current entries, add these)
FRED_SERIES.update({
    "XTEXVA01KRM664S": "Korea Total Exports (OECD MEI, monthly)",
    "CAPUTLG3344S": "Capacity Utilization: Semiconductors & Electronic Components",
    "PCU334413334413": "PPI: Semiconductor & Related Device Manufacturing",
    "A34SNO": "New Orders: Computers & Electronic Products",
})

# Track 2: leading economic indicators (chip-cycle canary). Exact ids verified at
# ingest; macro.run() skips an unreachable/invalid series gracefully.
LEADING_INDICATORS: tuple[str, ...] = (
    "XTEXVA01KRM664S", "IPG3344S", "CAPUTLG3344S", "PCU334413334413", "A34SNO",
)
# US semis filers with SEC revenue (ASML/TSM excluded — foreign filers).
SEMIS_REVENUE_NAMES: list[str] = ["AMAT", "LRCX", "NVDA", "AMD", "AVGO", "MU"]
H8_LEAD_QUARTERS: tuple[int, ...] = (1, 2)         # indicator leads revenue by 1-2Q
H4_HORIZON_MONTHS: tuple[int, ...] = (1, 2, 3)     # forward SOXX return horizons
# Conservative publication delay (months) applied BEFORE alignment (PIT guard).
INDICATOR_PUB_LAG_MONTHS: dict[str, int] = {
    "XTEXVA01KRM664S": 1, "IPG3344S": 1, "CAPUTLG3344S": 1,
    "PCU334413334413": 1, "A34SNO": 2,
}
```

> If `FRED_SERIES` is defined as a literal dict, add the four keys inline instead of `.update(...)`. Open `config.py` first to match the existing style.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_leading_indicators.py::test_config_track2_constants -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add config.py tests/test_leading_indicators.py
git commit -m "feat: Track 2 config (leading indicators, semis revenue names, params)"
```

---

## Phase 1 — Shared indicator prep

### Task 2: Monthly YoY growth + point-in-time lag

**Files:**
- Create: `atlas/analysis/leading_indicators.py`
- Test: `atlas/tests/test_leading_indicators.py` (extend)

- [ ] **Step 1: Write the failing test**

```python
# append to atlas/tests/test_leading_indicators.py
import numpy as np
import pandas as pd

def test_indicator_yoy_pit_lag():
    from analysis.leading_indicators import indicator_yoy
    idx = pd.date_range("2018-01-01", periods=36, freq="MS")
    level = pd.Series(np.exp(np.linspace(0, 0.36, 36)), index=idx)  # ~1%/mo growth
    yoy = indicator_yoy(level, pub_lag_months=1)
    # first 12 months drop (no YoY base) AND the series is shifted forward 1 month:
    # the value computed for ref month 2019-01 becomes available 2019-02.
    assert yoy.index.min() == pd.Timestamp("2019-02-01")
    # ~12 months of ~1%/mo compounding => YoY ~ ln(e^0.12) = 0.12
    assert abs(yoy.iloc[0] - 0.12) < 0.02
    assert yoy.isna().sum() == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_leading_indicators.py::test_indicator_yoy_pit_lag -v`
Expected: FAIL (`ModuleNotFoundError: analysis.leading_indicators`).

- [ ] **Step 3: Write minimal implementation**

```python
# atlas/analysis/leading_indicators.py
"""H8: do chip-cycle leading indicators lead chip-maker revenue? (pure functions)

Each indicator is YoY-log-growth transformed and shifted forward by a conservative
publication lag (point-in-time guard) before any alignment. Small quarterly sample =>
effect sizes + block-bootstrap CIs + selection-aware p + BH-FDR, NO walk-forward
(mirrors H1, analysis/fundamentals_leadlag.py)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from analysis.fundamentals_leadlag import bootstrap_slope_ci
from analysis.significance import block_resample_one


def indicator_yoy(level: pd.Series, *, pub_lag_months: int) -> pd.Series:
    """Year-over-year log growth (12-month diff) of a monthly series, then shifted
    forward `pub_lag_months` so a reference month's value is only available later."""
    s = level.sort_index().astype(float)
    g = (np.log(s) - np.log(s.shift(12))).dropna()
    if pub_lag_months:
        g = g.shift(pub_lag_months).dropna()
    return g
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_leading_indicators.py::test_indicator_yoy_pit_lag -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add analysis/leading_indicators.py tests/test_leading_indicators.py
git commit -m "feat: H8 monthly YoY indicator with point-in-time publication lag"
```

---

## Phase 2 — H8: indicators → revenue

### Task 3: Sector revenue YoY (quarterly aggregate)

**Files:**
- Modify: `atlas/analysis/leading_indicators.py`
- Test: `atlas/tests/test_leading_indicators.py` (extend)

- [ ] **Step 1: Write the failing test**

```python
# append to atlas/tests/test_leading_indicators.py
def test_sector_revenue_yoy_median():
    from analysis.leading_indicators import sector_revenue_yoy
    rows = []
    for tkr, base in [("NVDA", 100.0), ("AMD", 50.0)]:
        for i, q in enumerate(pd.period_range("2018Q1", periods=12, freq="Q")):
            rows.append({"ticker": tkr, "period_end": q.to_timestamp(how="end"),
                         "revenue": base * (1.10 ** i)})  # +10%/quarter
    fund = pd.DataFrame(rows)
    agg = sector_revenue_yoy(fund, names=["NVDA", "AMD"])
    # 4 quarters of +10% => YoY ln(1.1^4) ~= 0.381; both names identical => median same
    assert abs(agg.dropna().iloc[0] - np.log(1.10 ** 4)) < 1e-6
    assert isinstance(agg.index, pd.PeriodIndex)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_leading_indicators.py::test_sector_revenue_yoy_median -v`
Expected: FAIL (`AttributeError: sector_revenue_yoy`).

- [ ] **Step 3: Write minimal implementation**

Append to `atlas/analysis/leading_indicators.py`:

```python
def sector_revenue_yoy(fundamentals: pd.DataFrame, *, names: list[str]) -> pd.Series:
    """Cross-sectional MEDIAN YoY revenue growth across `names`, indexed by calendar
    quarter (PeriodIndex 'Q'). Bins period_end to its calendar quarter so different
    fiscal calendars align (same convention as H1)."""
    per_name = {}
    for t in names:
        sub = fundamentals.loc[fundamentals["ticker"] == t, ["period_end", "revenue"]].dropna()
        if sub.empty:
            continue
        q = pd.to_datetime(sub["period_end"]).dt.to_period("Q")
        lvl = pd.Series(sub["revenue"].to_numpy(float), index=q).sort_index()
        lvl = lvl[~lvl.index.duplicated(keep="last")]
        g = (np.log(lvl) - np.log(lvl.shift(4))).dropna()
        if not g.empty:
            per_name[t] = g
    if not per_name:
        return pd.Series(dtype=float)
    wide = pd.concat(per_name, axis=1)
    return wide.median(axis=1).dropna()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_leading_indicators.py::test_sector_revenue_yoy_median -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add analysis/leading_indicators.py tests/test_leading_indicators.py
git commit -m "feat: H8 sector revenue YoY aggregate (cross-sectional median)"
```

---

### Task 4: Indicator→revenue lead estimator (selection-aware, no walk-forward)

**Files:**
- Modify: `atlas/analysis/leading_indicators.py`
- Test: `atlas/tests/test_leading_indicators.py` (extend)

- [ ] **Step 1: Write the failing test**

```python
# append to atlas/tests/test_leading_indicators.py
def test_indicator_revenue_lead_detects_planted_lead():
    from analysis.leading_indicators import indicator_revenue_lead
    rng = np.random.default_rng(0)
    q = pd.period_range("2008Q1", periods=60, freq="Q")
    ind = pd.Series(rng.normal(0, 0.05, 60), index=q)          # quarterly indicator YoY
    # revenue YoY = indicator led by 1 quarter + small noise
    rev = pd.Series(0.8 * ind.shift(1).fillna(0).to_numpy() + rng.normal(0, 0.01, 60), index=q)
    out = indicator_revenue_lead(ind, rev, leads=(1, 2), iters=300, seed=1)
    assert out["best_lead"] == 1
    assert out["slope"] > 0.5
    assert out["p_selection"] < 0.05
    assert out["slope_lo"] > 0
    assert out["n_obs"] >= 40
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_leading_indicators.py::test_indicator_revenue_lead_detects_planted_lead -v`
Expected: FAIL (`AttributeError: indicator_revenue_lead`).

- [ ] **Step 3: Write minimal implementation**

Append to `atlas/analysis/leading_indicators.py`:

```python
def _corr_slope(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return np.nan, np.nan
    return float(np.corrcoef(x, y)[0, 1]), float(np.polyfit(x, y, 1)[0])


def _aligned_lead(indicator_q: pd.Series, revenue_q: pd.Series, lead: int
                  ) -> tuple[np.ndarray, np.ndarray]:
    """Indicator at quarter t vs revenue YoY at quarter t+lead, on the PeriodIndex."""
    shifted = indicator_q.copy()
    shifted.index = shifted.index + lead          # PeriodIndex + int shifts quarters
    paired = pd.concat([shifted.rename("x"), revenue_q.rename("y")],
                       axis=1, join="inner").dropna()
    return paired["x"].to_numpy(), paired["y"].to_numpy()


def indicator_revenue_lead(indicator_q: pd.Series, revenue_q: pd.Series, *,
                           leads: tuple[int, ...], iters: int, seed: int) -> dict:
    """Best one-sided lead of a quarterly indicator over revenue YoY, with a
    single-series block-resample selection-aware p and a block-bootstrap slope CI."""
    per_l = {l: _aligned_lead(indicator_q, revenue_q, l) for l in leads}
    best_l, best_corr, best = None, -np.inf, None
    for l, (x, y) in per_l.items():
        c, s = _corr_slope(x, y)
        if np.isfinite(c) and c > best_corr:
            best_l, best_corr, best = l, c, (x, y, s)
    if best is None:
        return {"best_lead": leads[0], "corr": np.nan, "slope": np.nan,
                "slope_lo": np.nan, "slope_hi": np.nan, "p_selection": 1.0,
                "n_obs": 0, "contradicts_thesis": False}
    x, y, slope = best
    rng = np.random.default_rng(seed)
    count = 0
    for _ in range(iters):
        null_max = -np.inf
        for xl, yl in per_l.values():
            if len(xl) < 3:
                continue
            xb = block_resample_one(xl, block=2, rng=rng)
            c, _ = _corr_slope(xb, yl)
            if np.isfinite(c):
                null_max = max(null_max, c)
        if null_max >= best_corr:
            count += 1
    lo, hi, _ = bootstrap_slope_ci(x, y, block=2, iters=iters, seed=seed)
    return {"best_lead": int(best_l), "corr": float(best_corr), "slope": float(slope),
            "slope_lo": lo, "slope_hi": hi, "p_selection": (count + 1) / (iters + 1),
            "n_obs": int(len(x)), "contradicts_thesis": bool(slope < 0)}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_leading_indicators.py::test_indicator_revenue_lead_detects_planted_lead -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add analysis/leading_indicators.py tests/test_leading_indicators.py
git commit -m "feat: H8 indicator->revenue lead estimator (selection-aware + CI)"
```

---

### Task 5: H8 driver table

**Files:**
- Modify: `atlas/analysis/leading_indicators.py`
- Test: `atlas/tests/test_leading_indicators.py` (extend)

- [ ] **Step 1: Write the failing test**

```python
# append to atlas/tests/test_leading_indicators.py
def _macro_long(series_levels, start="2008-01-01", n=120):
    idx = pd.date_range(start, periods=n, freq="MS")
    frames = []
    for sid, lvl in series_levels.items():
        frames.append(pd.DataFrame({"series_id": sid, "date": idx, "value": lvl(idx)}))
    return pd.concat(frames, ignore_index=True)

def test_leading_revenue_table_shapes_and_fdr():
    from analysis.leading_indicators import leading_revenue_table
    rng = np.random.default_rng(2)
    macro = _macro_long({
        "IPG3344S": lambda i: np.exp(np.linspace(0, 0.6, len(i))) * (1 + rng.normal(0, 0.01, len(i))),
        "A34SNO": lambda i: np.exp(np.linspace(0, 0.3, len(i))) * (1 + rng.normal(0, 0.01, len(i))),
    })
    rows = []
    for tkr in ["NVDA", "AMD"]:
        for k, q in enumerate(pd.period_range("2008Q1", periods=40, freq="Q")):
            rows.append({"ticker": tkr, "period_end": q.to_timestamp(how="end"),
                         "revenue": 100 * (1.05 ** k)})
    fund = pd.DataFrame(rows)
    out = leading_revenue_table(
        macro, fund, indicators=("IPG3344S", "A34SNO"), names=["NVDA", "AMD"],
        leads=(1, 2), pub_lag={"IPG3344S": 1, "A34SNO": 2}, iters=200, seed=7)
    assert set(out["indicator"]) == {"IPG3344S", "A34SNO"}
    for col in ("best_lead", "slope", "slope_lo", "slope_hi", "p_selection",
                "q_value", "n_obs", "contradicts_thesis"):
        assert col in out.columns
    assert out["q_value"].notna().any()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_leading_indicators.py::test_leading_revenue_table_shapes_and_fdr -v`
Expected: FAIL (`AttributeError: leading_revenue_table`).

- [ ] **Step 3: Write minimal implementation**

Append to `atlas/analysis/leading_indicators.py`:

```python
def _quarterly_indicator(macro: pd.DataFrame, sid: str, pub_lag_months: int) -> pd.Series:
    """Monthly FRED series -> PIT-lagged YoY -> calendar-quarter mean (PeriodIndex 'Q')."""
    sub = macro.loc[macro["series_id"] == sid, ["date", "value"]].dropna()
    if sub.empty:
        return pd.Series(dtype=float)
    s = pd.Series(sub["value"].to_numpy(float),
                  index=pd.to_datetime(sub["date"])).sort_index()
    yoy = indicator_yoy(s, pub_lag_months=pub_lag_months)
    if yoy.empty:
        return pd.Series(dtype=float)
    return yoy.groupby(yoy.index.to_period("Q")).mean()


def leading_revenue_table(macro: pd.DataFrame, fundamentals: pd.DataFrame, *,
                          indicators: tuple[str, ...], names: list[str],
                          leads: tuple[int, ...], pub_lag: dict[str, int],
                          iters: int, seed: int) -> pd.DataFrame:
    """One row per indicator: best lead of indicator YoY over sector revenue YoY,
    BH-FDR over eligible (finite-slope) indicators."""
    from analysis.leadlag import bh_fdr

    revenue_q = sector_revenue_yoy(fundamentals, names=names)
    rows = []
    for sid in indicators:
        ind_q = _quarterly_indicator(macro, sid, pub_lag.get(sid, 1))
        if ind_q.empty or revenue_q.empty:
            rows.append({"indicator": sid, "best_lead": leads[0], "corr": np.nan,
                         "slope": np.nan, "slope_lo": np.nan, "slope_hi": np.nan,
                         "p_selection": 1.0, "n_obs": 0, "contradicts_thesis": False})
            continue
        out = indicator_revenue_lead(ind_q, revenue_q, leads=leads, iters=iters, seed=seed)
        out["indicator"] = sid
        rows.append(out)
    df = pd.DataFrame(rows)
    if not df.empty:
        elig = df["slope"].notna()
        df["q_value"] = np.nan
        if elig.any():
            df.loc[elig, "q_value"] = bh_fdr(df.loc[elig, "p_selection"].to_numpy())
    return df
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_leading_indicators.py::test_leading_revenue_table_shapes_and_fdr -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add analysis/leading_indicators.py tests/test_leading_indicators.py
git commit -m "feat: H8 leading_revenue_table driver (BH-FDR over indicators)"
```

---

### Task 6: `h8_record` + wiring

**Files:**
- Modify: `atlas/analysis/signals.py`
- Test: `atlas/tests/test_signals.py` (extend)

- [ ] **Step 1: Write the failing test**

```python
# append to atlas/tests/test_signals.py
def test_h8_record_confirmed_and_null():
    from analysis.signals import h8_record
    confirmed = pd.DataFrame([
        {"indicator": "IPG3344S", "best_lead": 1, "corr": 0.5, "slope": 0.8,
         "slope_lo": 0.3, "slope_hi": 1.2, "p_selection": 0.001, "q_value": 0.004,
         "n_obs": 45, "contradicts_thesis": False},
        {"indicator": "A34SNO", "best_lead": 2, "corr": 0.2, "slope": 0.3,
         "slope_lo": -0.1, "slope_hi": 0.7, "p_selection": 0.2, "q_value": 0.2,
         "n_obs": 45, "contradicts_thesis": False},
    ])
    rec = h8_record(confirmed)
    assert rec["id"] == "H8" and rec["verdict"] == "confirmed"
    assert rec["chart"]["type"] == "leading_revenue"

    nullish = pd.DataFrame([
        {"indicator": "IPG3344S", "best_lead": 1, "corr": 0.05, "slope": 0.1,
         "slope_lo": -0.2, "slope_hi": 0.4, "p_selection": 0.4, "q_value": 0.6,
         "n_obs": 45, "contradicts_thesis": False},
    ])
    assert h8_record(nullish)["verdict"] == "null"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_signals.py -k h8 -v`
Expected: FAIL (`ImportError: cannot import name 'h8_record'`).

- [ ] **Step 3: Write minimal implementation**

Add to `atlas/analysis/signals.py` (after `h7_record`), mirroring `h5_record`'s select-then-classify:

```python
def h8_record(rows: pd.DataFrame) -> dict:
    """H8: do chip-cycle leading indicators lead chip-maker revenue?"""
    elig = rows[(rows["n_obs"] > 0) & rows["slope"].notna()]
    confirmed = elig[(elig["q_value"] <= FDR_ALPHA) & (elig["slope"] > 0)
                     & (~elig["contradicts_thesis"])]
    suggestive = elig[(elig["q_value"] <= 0.25) & (elig["slope"] > 0)
                      & (elig["slope_lo"] > 0) & (~elig["contradicts_thesis"])]
    contradicting = elig[(elig["q_value"] <= FDR_ALPHA) & (elig["slope"] < 0)]
    if len(confirmed):
        verdict, best = "confirmed", confirmed.sort_values("q_value").iloc[0]
    elif len(suggestive):
        verdict, best = "suggestive", suggestive.sort_values("p_selection").iloc[0]
    elif len(contradicting):
        verdict, best = "contradicts", contradicting.sort_values("q_value").iloc[0]
    elif len(elig):
        verdict, best = "null", elig.sort_values("q_value").iloc[0]
    else:
        verdict, best = "null", (rows.iloc[0] if len(rows) else pd.Series(dtype=float))
    interp = {
        "confirmed": "the canary leads the fundamental (economic propagation)",
        "suggestive": "weak lead",
        "null": "no measurable lead over the sector's revenue",
        "contradicts": "indicator moves opposite to revenue",
    }[verdict]
    n = int(best.get("n_obs")) if len(elig) else 0
    return {
        "id": "H8", "title": "Does the chip-cycle canary lead chip-maker revenue?",
        "horizon": "1-2 quarters", "claim": "Leading indicators lead semis-sector revenue",
        "mechanism": f"Physical chip cycle leads the fundamental -- {interp}",
        "verdict": verdict,
        "evidence_chain": [
            {"stage": "best indicator corr", "metric": "corr", "value": _num(best.get("corr"))},
            {"stage": "best indicator slope", "metric": "slope", "value": _num(best.get("slope"))},
            {"stage": "selection-aware q", "metric": "q", "value": _num(best.get("q_value"))},
        ],
        "stat": {"name": "slope", "value": _num(best.get("slope")),
                 "ci": [_num(best.get("slope_lo")), _num(best.get("slope_hi"))],
                 "q_value": _num(best.get("q_value")), "n": n},
        "caveats": [
            "Target = cross-sectional median revenue YoY of 6 US semis filers (ASML/TSM excluded).",
            "Korea exports are TOTAL, not semis-only; indicators publication-lagged (PIT). No walk-forward (small sample).",
        ],
        "chart": {"type": "leading_revenue", "ref": "h8"},
        "detail_rows": elig[["indicator", "best_lead", "corr", "slope", "slope_lo",
                             "slope_hi", "q_value", "n_obs"]].to_dict("records"),
    }
```

In `build_signal_records`, after the H7 block, add:

```python
    has_h8 = con.execute("SELECT count(*) FROM information_schema.tables "
                         "WHERE table_name='leading_revenue'").fetchone()[0] > 0
    if has_h8:
        h8 = con.execute('SELECT * FROM leading_revenue').df()
        if len(h8):
            records.append(h8_record(h8))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_signals.py -k h8 -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add analysis/signals.py tests/test_signals.py
git commit -m "feat: H8 signal record + build_signal_records wiring"
```

---

## Phase 3 — H4: indicators → semis returns (efficiency)

### Task 7: Monthly SOXX returns + driver table

**Files:**
- Create: `atlas/analysis/macro_sector.py`
- Test: `atlas/tests/test_macro_sector.py`

- [ ] **Step 1: Write the failing test**

```python
# atlas/tests/test_macro_sector.py
import numpy as np
import pandas as pd

def _macro_long(series_levels, start="2008-01-01", n=180):
    idx = pd.date_range(start, periods=n, freq="MS")
    frames = [pd.DataFrame({"series_id": s, "date": idx, "value": f(idx)})
              for s, f in series_levels.items()]
    return pd.concat(frames, ignore_index=True)

def _daily_returns(ticker, start="2008-01-01", n=4000, seed=3):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=n)
    return pd.DataFrame({"ticker": ticker, "date": idx, "log_return": rng.normal(0, 0.01, n)})

def test_monthly_returns_sum():
    from analysis.macro_sector import monthly_returns
    r = _daily_returns("SOXX")
    m = monthly_returns(r, "SOXX")
    assert isinstance(m.index, pd.DatetimeIndex)
    assert len(m) > 100  # ~ n/21 months
    assert abs(m.iloc[0]) < 0.5

def test_macro_sector_table_shapes_and_fdr():
    from analysis.macro_sector import macro_sector_table
    rng = np.random.default_rng(4)
    macro = _macro_long({
        "IPG3344S": lambda i: np.exp(np.linspace(0, 0.6, len(i))) * (1 + rng.normal(0, 0.01, len(i))),
        "A34SNO": lambda i: np.exp(np.linspace(0, 0.3, len(i))) * (1 + rng.normal(0, 0.01, len(i))),
    })
    returns = _daily_returns("SOXX")
    out = macro_sector_table(
        macro, returns, indicators=("IPG3344S", "A34SNO"), target="SOXX",
        horizons=(1, 2, 3), pub_lag={"IPG3344S": 1, "A34SNO": 2}, iters=150, seed=5)
    assert len(out) == 2 * 3
    for col in ("indicator", "horizon", "corr", "slope", "slope_lo", "slope_hi",
                "p_selection", "q_value", "oos_sign_rate", "n_obs", "contradicts_thesis"):
        assert col in out.columns
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_macro_sector.py -v`
Expected: FAIL (`ModuleNotFoundError: analysis.macro_sector`).

- [ ] **Step 3: Write minimal implementation**

```python
# atlas/analysis/macro_sector.py
"""H4: is the chip cycle already priced into semis equity returns? (pure functions)

Monthly indicator YoY (PIT-lagged) vs forward SOXX monthly returns over {1,2,3}-month
horizons. Selection-aware single-series null + anchored walk-forward OOS + BH-FDR over
the indicator x horizon family (mirrors H5/H7). Reuses the generic time-series helpers
from analysis.vol_termstructure."""
from __future__ import annotations

import numpy as np
import pandas as pd

from analysis.leading_indicators import indicator_yoy
from analysis.vol_termstructure import (
    _corr_slope, aligned_forward, oos_sign_rate, selection_pvalue_one_series,
)


def monthly_returns(returns: pd.DataFrame, ticker: str) -> pd.Series:
    """Sum daily log returns into calendar-month log returns (month-start indexed)."""
    sub = returns.loc[returns["ticker"] == ticker, ["date", "log_return"]].dropna()
    if sub.empty:
        return pd.Series(dtype=float)
    s = pd.Series(sub["log_return"].to_numpy(float),
                  index=pd.to_datetime(sub["date"])).sort_index()
    return s.groupby(s.index.to_period("M")).sum().rename_axis(None).pipe(
        lambda x: pd.Series(x.to_numpy(), index=x.index.to_timestamp()))


def _indicator_monthly(macro: pd.DataFrame, sid: str, pub_lag_months: int) -> pd.Series:
    sub = macro.loc[macro["series_id"] == sid, ["date", "value"]].dropna()
    if sub.empty:
        return pd.Series(dtype=float)
    s = pd.Series(sub["value"].to_numpy(float),
                  index=pd.to_datetime(sub["date"])).sort_index()
    yoy = indicator_yoy(s, pub_lag_months=pub_lag_months)
    # normalize index to month-start timestamps to match monthly_returns
    return pd.Series(yoy.to_numpy(), index=yoy.index.to_period("M").to_timestamp())


def macro_sector_table(macro: pd.DataFrame, returns: pd.DataFrame, *,
                       indicators: tuple[str, ...], target: str,
                       horizons: tuple[int, ...], pub_lag: dict[str, int],
                       iters: int, seed: int) -> pd.DataFrame:
    """One row per (indicator, horizon): slope of forward `target` monthly return on
    indicator YoY, with selection-aware p, block-bootstrap CI, OOS sign-rate, BH-FDR."""
    from analysis.fundamentals_leadlag import bootstrap_slope_ci
    from analysis.leadlag import bh_fdr

    tgt = monthly_returns(returns, target)
    rows = []
    for sid in indicators:
        ind = _indicator_monthly(macro, sid, pub_lag.get(sid, 1))
        for h in horizons:
            x, y = aligned_forward(ind, tgt, horizon=h) if (not ind.empty and not tgt.empty) else (np.array([]), np.array([]))
            corr, slope = _corr_slope(x, y)
            if not np.isfinite(corr) or len(x) < 10:
                rows.append({"indicator": sid, "horizon": h, "corr": np.nan,
                             "slope": np.nan, "slope_lo": np.nan, "slope_hi": np.nan,
                             "p_selection": 1.0, "oos_sign_rate": 0.0,
                             "n_obs": int(len(x)), "contradicts_thesis": False})
                continue
            p = selection_pvalue_one_series(x, y, iters=iters, seed=seed)
            lo, hi, _ = bootstrap_slope_ci(x, y, block=3, iters=iters, seed=seed)
            sign = oos_sign_rate(ind, tgt, horizon=h, test_days=24, step_days=24,
                                 init_train_frac=0.5)
            rows.append({"indicator": sid, "horizon": h, "corr": float(corr),
                         "slope": float(slope), "slope_lo": lo, "slope_hi": hi,
                         "p_selection": p, "oos_sign_rate": sign, "n_obs": int(len(x)),
                         "contradicts_thesis": bool(slope < 0)})
    df = pd.DataFrame(rows)
    if not df.empty:
        elig = df["slope"].notna()
        df["q_value"] = np.nan
        if elig.any():
            df.loc[elig, "q_value"] = bh_fdr(df.loc[elig, "p_selection"].to_numpy())
    return df
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_macro_sector.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add analysis/macro_sector.py tests/test_macro_sector.py
git commit -m "feat: H4 macro_sector_table (monthly indicator -> forward SOXX returns)"
```

---

### Task 8: `h4_record` + wiring

**Files:**
- Modify: `atlas/analysis/signals.py`
- Test: `atlas/tests/test_signals.py` (extend)

- [ ] **Step 1: Write the failing test**

```python
# append to atlas/tests/test_signals.py
def test_h4_record_null_surfaces_min_q():
    from analysis.signals import h4_record
    rows = pd.DataFrame([
        {"indicator": "IPG3344S", "horizon": 1, "corr": 0.05, "slope": 0.4,
         "slope_lo": -0.3, "slope_hi": 1.1, "p_selection": 0.3, "q_value": 0.5,
         "oos_sign_rate": 0.5, "n_obs": 150, "contradicts_thesis": False},
        {"indicator": "A34SNO", "horizon": 3, "corr": 0.07, "slope": 0.6,
         "slope_lo": -0.1, "slope_hi": 1.3, "p_selection": 0.12, "q_value": 0.3,
         "oos_sign_rate": 0.55, "n_obs": 150, "contradicts_thesis": False},
    ])
    rec = h4_record(rows)
    assert rec["id"] == "H4" and rec["verdict"] == "null"
    assert rec["chart"]["type"] == "macro_sector"
    assert rec["stat"]["q_value"] == 0.3

def test_h4_record_confirmed():
    from analysis.signals import h4_record
    rows = pd.DataFrame([
        {"indicator": "IPG3344S", "horizon": 3, "corr": 0.3, "slope": 0.9,
         "slope_lo": 0.4, "slope_hi": 1.4, "p_selection": 0.001, "q_value": 0.01,
         "oos_sign_rate": 0.8, "n_obs": 150, "contradicts_thesis": False},
    ])
    assert h4_record(rows)["verdict"] == "confirmed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_signals.py -k h4 -v`
Expected: FAIL (`ImportError: cannot import name 'h4_record'`).

- [ ] **Step 3: Write minimal implementation**

Add to `atlas/analysis/signals.py` (after `h8_record`), mirroring `h7_record`:

```python
def h4_record(rows: pd.DataFrame) -> dict:
    """H4: is the chip cycle already priced into semis equity returns?"""
    elig = rows[(rows["n_obs"] > 0) & rows["slope"].notna()]
    confirmed = elig[(elig["q_value"] <= FDR_ALPHA) & (elig["slope"] > 0)
                     & (~elig["contradicts_thesis"]) & (elig["oos_sign_rate"] >= OOS_SIGN_FLOOR)]
    suggestive = elig[(elig["q_value"] <= 0.25) & (elig["slope"] > 0) & (elig["slope_lo"] > 0)
                      & (~elig["contradicts_thesis"])]
    contradicting = elig[(elig["q_value"] <= FDR_ALPHA) & (elig["slope"] < 0)]
    if len(confirmed):
        verdict, best = "confirmed", confirmed.sort_values("q_value").iloc[0]
    elif len(suggestive):
        verdict, best = "suggestive", suggestive.sort_values("p_selection").iloc[0]
    elif len(contradicting):
        verdict, best = "contradicts", contradicting.sort_values("q_value").iloc[0]
    elif len(elig):
        verdict, best = "null", elig.sort_values("q_value").iloc[0]
    else:
        verdict, best = "null", (rows.iloc[0] if len(rows) else pd.Series(dtype=float))
    interp = {
        "confirmed": "the public cycle still predicts forward returns (under-priced)",
        "suggestive": "weak predictive signal",
        "null": "priced in -- a public canary everyone watches",
        "contradicts": "predicts forward returns the wrong way",
    }[verdict]
    n = int(best.get("n_obs")) if len(elig) else 0
    return {
        "id": "H4", "title": "Is the chip cycle already priced into semis equity?",
        "horizon": "1-3 months",
        "claim": "Chip-cycle indicators predict forward semis (SOXX) returns",
        "mechanism": f"A public macro canary; markets should price it -- {interp}",
        "verdict": verdict,
        "evidence_chain": [
            {"stage": "best-cell corr", "metric": "corr", "value": _num(best.get("corr"))},
            {"stage": "best-cell slope", "metric": "slope", "value": _num(best.get("slope"))},
            {"stage": "OOS sign-retention", "metric": "rate",
             "value": _num(best.get("oos_sign_rate"))},
        ],
        "stat": {"name": "slope", "value": _num(best.get("slope")),
                 "ci": [_num(best.get("slope_lo")), _num(best.get("slope_hi"))],
                 "q_value": _num(best.get("q_value")), "n": n},
        "caveats": [
            "Indicators publication-lagged (PIT); monthly walk-forward; observational, no costs.",
            "Family = indicators x {1,2,3}m horizons, BH-FDR corrected; Korea exports are total, not semis-only.",
        ],
        "chart": {"type": "macro_sector", "ref": "h4"},
        "detail_rows": elig[["indicator", "horizon", "corr", "slope", "slope_lo",
                             "slope_hi", "q_value", "oos_sign_rate", "n_obs"]].to_dict("records"),
    }
```

In `build_signal_records`, after the H8 block, add:

```python
    has_h4 = con.execute("SELECT count(*) FROM information_schema.tables "
                         "WHERE table_name='macro_sector'").fetchone()[0] > 0
    if has_h4:
        h4 = con.execute('SELECT * FROM macro_sector').df()
        if len(h4):
            records.append(h4_record(h4))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_signals.py -k h4 -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add analysis/signals.py tests/test_signals.py
git commit -m "feat: H4 signal record + build_signal_records wiring"
```

---

## Phase 4 — Orchestration

### Task 9: Compute + write `leading_revenue` / `macro_sector` in `run()`

**Files:**
- Modify: `atlas/analysis/leadlag.py:run` (`# pragma: no cover` orchestrator)

- [ ] **Step 1: Add the blocks**

In `analysis/leadlag.py::run()`, after the H6/H7 vol block (added in Track 1) and before `con.close()`, add:

```python
    # H8 + H4: leading-indicator cards (only when the indicator series exist in macro).
    from config import (H4_HORIZON_MONTHS, H8_LEAD_QUARTERS, INDICATOR_PUB_LAG_MONTHS,
                        LEADING_INDICATORS, SEMIS_REVENUE_NAMES)
    present = set(macro["series_id"].unique()) if len(macro) else set()
    inds = tuple(s for s in LEADING_INDICATORS if s in present)
    if inds and len(fundamentals):
        from analysis.leading_indicators import leading_revenue_table
        h8 = leading_revenue_table(
            macro, fundamentals, indicators=inds, names=SEMIS_REVENUE_NAMES,
            leads=H8_LEAD_QUARTERS, pub_lag=INDICATOR_PUB_LAG_MONTHS,
            iters=BOOTSTRAP_ITERS, seed=RANDOM_SEED)
        con.register("h8t", h8)
        con.execute("CREATE OR REPLACE TABLE leading_revenue AS SELECT * FROM h8t")
        con.unregister("h8t")
        print(f"leading_revenue: wrote {len(h8)} indicator rows")
    if inds and "SOXX" in set(returns["ticker"].unique()):
        from analysis.macro_sector import macro_sector_table
        h4 = macro_sector_table(
            macro, returns, indicators=inds, target="SOXX",
            horizons=H4_HORIZON_MONTHS, pub_lag=INDICATOR_PUB_LAG_MONTHS,
            iters=BOOTSTRAP_ITERS, seed=RANDOM_SEED)
        con.register("h4t", h4)
        con.execute("CREATE OR REPLACE TABLE macro_sector AS SELECT * FROM h4t")
        con.unregister("h4t")
        print(f"macro_sector: wrote {len(h4)} (indicator x horizon) rows")
```

- [ ] **Step 2: Smoke-run locally (requires ingested data)**

Run: `uv run python -m analysis.leadlag`
Expected: console shows `leading_revenue: wrote N ...` and `macro_sector: wrote M ...` (N≤5, M≤15), or the lines are skipped if the new FRED ids didn't ingest (acceptable; tables simply absent).

- [ ] **Step 3: Commit**

```bash
git add analysis/leadlag.py
git commit -m "feat: compute + persist leading_revenue / macro_sector tables"
```

---

## Phase 5 — Web

### Task 10: SignalCard chart blocks

**Files:**
- Modify: `atlas/web/src/components/SignalCard.svelte`

- [ ] **Step 1: Add the blocks (after the `macro_sector`/`termstructure_timing` blocks, before `{#each signal.caveats ...}`)**

```svelte
  {#if signal.chart.type === "leading_revenue"}
    <p class="legend">Indicator YoY → semis-sector revenue YoY (best lead, FDR-corrected)</p>
    <ul class="edges">
      {#each signal.detail_rows as r}
        <li><span>{r.indicator}</span>
          <b>slope {Number(r.slope).toFixed(2)}</b>
          <span class="ci">[{Number(r.slope_lo).toFixed(2)}, {Number(r.slope_hi).toFixed(2)}]</span>
          <span class="lag">lead {r.best_lead}Q · q={Number(r.q_value).toFixed(2)} · n={r.n_obs}</span></li>
      {/each}
    </ul>
  {/if}
  {#if signal.chart.type === "macro_sector"}
    <p class="legend">Indicator YoY → forward SOXX return (monthly walk-forward, FDR)</p>
    <ul class="edges">
      {#each signal.detail_rows as r}
        <li><span>{r.indicator} · {r.horizon}m</span>
          <b>slope {Number(r.slope).toFixed(2)}</b>
          <span class="ci">[{Number(r.slope_lo).toFixed(2)}, {Number(r.slope_hi).toFixed(2)}]</span>
          <span class="lag">q={Number(r.q_value).toFixed(2)} · sign {Number(r.oos_sign_rate).toFixed(2)}</span></li>
      {/each}
    </ul>
  {/if}
```

- [ ] **Step 2: Verify the web build compiles**

Run: `cd web && npm ci && npm run build`
Expected: build succeeds (the 2 pre-existing a11y warnings may remain).

- [ ] **Step 3: Commit**

```bash
git add web/src/components/SignalCard.svelte
git commit -m "feat: render leading_revenue + macro_sector signal cards"
```

---

## Final verification

- [ ] **Full suite + coverage**

Run: `uv run pytest --cov --cov-report=term-missing`
Expected: all green; `leading_indicators.py` and `macro_sector.py` at 80%+ (network/`run()` excluded).

- [ ] **Lint**

Run: `uv run ruff check .`
Expected: no NEW issues.

- [ ] **End-to-end (if online)**

Run: `uv run make all && uv run python web/export_data.py --db data/atlas.duckdb --out web/static/data`
Expected: `signals.json` contains H8 and H4 (alongside H0/H1/H2/H5/H6/H7). Confirm the four new FRED ids ingested (`uv run python -c "import duckdb;print(duckdb.connect('data/atlas.duckdb',read_only=True).execute(\"SELECT DISTINCT series_id FROM macro_daily\").df())"`); if any id is wrong, fix it in `config.FRED_SERIES`/`LEADING_INDICATORS` and re-run.

- [ ] **Report verdicts honestly** — read H8/H4 out of `signals.json` and report exactly as produced. Do NOT push; hand back for Phase 3 review (esp. the contradicts/null boundary and whether H4's predictive cells, if any, are a genuine signal vs a public-canary artifact).

---

## Self-check (done while writing this plan)

- FRED indicator ingest (reuses macro pipeline) + config family → Task 1, Task 9.
- Monthly YoY + PIT publication lag → Task 2.
- H8 economic lead → revenue (median aggregate, selection-aware, CI, FDR, no walk-forward) → Tasks 3–6.
- H4 efficiency → forward SOXX returns (monthly walk-forward, selection-aware, FDR) → Tasks 7–8.
- Reuse of `bh_fdr`/`bootstrap_slope_ci`/`block_resample_one`/`walk_forward_folds`/`vol_termstructure` helpers, no new thresholds → Tasks 4, 7.
- Orchestration + DuckDB tables + `build_signal_records` wiring → Tasks 6, 8, 9.
- Web chart types `leading_revenue`, `macro_sector` → Task 10.
- Honest caveats (Korea total-not-semis; PIT lag; no walk-forward for H8) → Tasks 6, 8.
- No new thresholds; verdicts reported as produced → Final verification.
