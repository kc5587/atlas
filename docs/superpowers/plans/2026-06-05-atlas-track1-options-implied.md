# Atlas Track 1 — Options-Implied Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **This project executes Phase 2 via Codex CLI (gpt-5.4)** per the user's model-routing rules: strict TDD (RED→GREEN), per-task path-scoped commits, report verdicts honestly with NO threshold tuning, do NOT push.

**Goal:** Add two Signal Lab cards — **H6** (variance risk premium / implied-vol information content) and **H7** (vol term-structure slope as a forward-return timer) — from free index/sector vol data, plus a silent forward-collecting single-name IV snapshot pipeline (**Collector B**).

**Architecture:** Mirror the existing hypothesis pattern exactly. New free data (`^VIX9D/^VIX/^VIX3M/^VIX6M/^VXN` + `QQQ`) is ingested to parquet (`ingest/vol.py`), exposed as DuckDB tables via dbt staging+mart models, analyzed by two pure-function modules (`analysis/vol_premium.py`, `analysis/vol_termstructure.py`), written to tables `vol_premium`/`vol_termstructure` inside `analysis/leadlag.py::run()`, turned into card records by `h6_record`/`h7_record` in `analysis/signals.py`, and rendered by two new `chart.type` blocks in `SignalCard.svelte`. Collector B (`ingest/iv_snapshot.py`) accumulates a per-name panel persisted as a release asset across daily CI runs.

**Tech Stack:** Python 3.13, pandas, numpy, pandera, duckdb, dbt-duckdb, yfinance, pytest (+`--cov`), Svelte 5 (runes), Vite. Run all Python via `uv run` from the `atlas/` directory.

**Non-negotiables (from the spec):** reuse `FDR_ALPHA=0.10`, `OOS_SIGN_RATE_FLOOR=0.6`, `RANDOM_SEED`, `BOOTSTRAP_ITERS`, the single-series perturbation null, and `bh_fdr` — **invent no new thresholds**. Report verdicts exactly as produced. Network fetchers get `# pragma: no cover`.

---

## File Structure

**New files**
- `atlas/ingest/vol.py` — fetch VIX-complex + VXN index history → `data/raw/vol/*.parquet`.
- `atlas/ingest/iv_snapshot.py` — Collector B: daily single-name option-chain snapshot → accumulating panel parquet.
- `atlas/analysis/vol_premium.py` — H6 pure functions + `vol_premium_table` driver.
- `atlas/analysis/vol_termstructure.py` — H7 pure functions + `vol_termstructure_table` driver.
- `atlas/dbt_project/models/staging/stg_vol.sql`, `stg_iv_snapshots.sql`
- `atlas/dbt_project/models/marts/vol_indices.sql`, `iv_snapshots.sql`
- `atlas/tests/test_vol_ingest.py`, `test_vol_premium.py`, `test_vol_termstructure.py`, `test_iv_snapshot.py`

**Modified files**
- `atlas/config.py` — `AUX_TICKERS`, `VOL_SERIES`, `VOL_FRED_FALLBACK`, H6/H7 params.
- `atlas/ingest/schemas.py` — `VOL_SCHEMA`, `IV_SNAPSHOT_SCHEMA`.
- `atlas/ingest/prices.py` — ingest `AUX_TICKERS` (adds QQQ).
- `atlas/analysis/signals.py` — `h6_record`, `h7_record`, wire into `build_signal_records`.
- `atlas/analysis/leadlag.py` — compute + write `vol_premium`, `vol_termstructure` in `run()`.
- `atlas/web/src/components/SignalCard.svelte` — `vrp_term`, `termstructure_timing` chart blocks.
- `atlas/dbt_project/models/staging/schema.yml`, `atlas/dbt_project/models/marts/schema.yml` — register new models.
- `atlas/Makefile` — add `ingest.vol`, `ingest.iv_snapshot` to `ingest` target.
- `atlas/scripts/publish_release.py` — publish/round-trip the IV panel; add `iv_snapshots` to row counts.
- `atlas/tests/test_signals.py` — H6/H7 record tests.

---

## Conventions for every task

- Work in `atlas/`. Run tests with `uv run pytest <path> -v`.
- Commit message format: `<type>: <desc>` (no attribution — disabled globally).
- Commit only the paths a task touches.
- Pure functions take DataFrames/arrays in and return DataFrames/dicts out — **no DuckDB reads inside pure functions**.

---

## Phase 0 — Config & data plumbing

### Task 1: Config constants + VOL_SCHEMA

**Files:**
- Modify: `atlas/config.py`
- Modify: `atlas/ingest/schemas.py`
- Test: `atlas/tests/test_vol_ingest.py`

- [ ] **Step 1: Write the failing test**

```python
# atlas/tests/test_vol_ingest.py
import pandas as pd
import pytest

def test_config_exposes_vol_constants():
    import config
    assert config.AUX_TICKERS == ["QQQ"]
    # implied-vol index symbols we fetch (yfinance ^-prefixed), FRED fallbacks
    assert set(config.VOL_SERIES) == {"^VIX9D", "^VIX", "^VIX3M", "^VIX6M", "^VXN"}
    assert config.VOL_FRED_FALLBACK["^VIX"] == "VIXCLS"
    assert config.VOL_FRED_FALLBACK["^VXN"] == "VXNCLS"
    assert config.H6_RV_HORIZON == 21
    assert config.H6_PAIRS == (("^VIX", "SPY"), ("^VXN", "QQQ"))
    assert config.H7_PREDICTOR == ("^VIX", "^VIX3M")
    assert config.H7_TARGETS == ("SPY", "SOXX", "IGV")
    assert config.H7_HORIZONS == (21, 42, 63)

def test_vol_schema_validates_long_frame():
    from ingest.schemas import VOL_SCHEMA
    df = pd.DataFrame({
        "series": ["^VIX", "^VIX"],
        "date": pd.to_datetime(["2020-01-02", "2020-01-03"]),
        "close": [12.5, 13.1],
    })
    assert len(VOL_SCHEMA.validate(df)) == 2

def test_vol_schema_rejects_negative_close():
    from ingest.schemas import VOL_SCHEMA
    import pandera.errors as pae
    bad = pd.DataFrame({"series": ["^VIX"], "date": pd.to_datetime(["2020-01-02"]),
                        "close": [-1.0]})
    with pytest.raises(pae.SchemaError):
        VOL_SCHEMA.validate(bad)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_vol_ingest.py -v`
Expected: FAIL (`AttributeError: module 'config' has no attribute 'AUX_TICKERS'` / `ImportError: VOL_SCHEMA`).

- [ ] **Step 3: Write minimal implementation**

Append to `atlas/config.py` (after the existing factor-model block):

```python
# Track 1: options-implied vol. QQQ is VXN's matched underlying (NOT a chain node).
AUX_TICKERS: list[str] = ["QQQ"]

# Implied-vol index history (yfinance ^-prefixed), with FRED fallbacks where they exist.
VOL_SERIES: tuple[str, ...] = ("^VIX9D", "^VIX", "^VIX3M", "^VIX6M", "^VXN")
VOL_FRED_FALLBACK: dict[str, str] = {"^VIX": "VIXCLS", "^VXN": "VXNCLS"}

# H6 variance risk premium: forward realized-vol window (trading days) + implied/underlying pairs.
H6_RV_HORIZON = 21
H6_PAIRS: tuple[tuple[str, str], ...] = (("^VIX", "SPY"), ("^VXN", "QQQ"))

# H7 term-structure timing: predictor = VIX/VIX3M ratio; targets x forward horizons (trading days).
H7_PREDICTOR: tuple[str, str] = ("^VIX", "^VIX3M")
H7_TARGETS: tuple[str, ...] = ("SPY", "SOXX", "IGV")
H7_HORIZONS: tuple[int, ...] = (21, 42, 63)
```

Add to `atlas/ingest/schemas.py` (after `MACRO_SCHEMA`):

```python
VOL_SCHEMA = pa.DataFrameSchema(
    {
        "series": pa.Column(str, nullable=False),
        "date": pa.Column("datetime64[ns]", nullable=False),
        "close": pa.Column(float, pa.Check.ge(0), nullable=False),
    },
    strict=True,
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_vol_ingest.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add config.py ingest/schemas.py tests/test_vol_ingest.py
git commit -m "feat: Track 1 config constants + VOL_SCHEMA"
```

---

### Task 2: `ingest/vol.py` — normalize + fetch (pragma) + run

**Files:**
- Create: `atlas/ingest/vol.py`
- Test: `atlas/tests/test_vol_ingest.py` (extend)

- [ ] **Step 1: Write the failing test**

```python
# append to atlas/tests/test_vol_ingest.py
def test_normalize_vol_long_format():
    from ingest.vol import normalize_vol
    raw = pd.DataFrame(
        {"Open": [12.0, 13.0], "High": [12.5, 13.5], "Low": [11.0, 12.0],
         "Close": [12.3, 13.1], "Adj Close": [12.3, 13.1], "Volume": [0, 0]},
        index=pd.to_datetime(["2020-01-02", "2020-01-03"]),
    )
    out = normalize_vol(raw, "^VIX")
    assert list(out.columns) == ["series", "date", "close"]
    assert (out["series"] == "^VIX").all()
    assert out["close"].tolist() == [12.3, 13.1]
    assert str(out["date"].dtype) == "datetime64[ns]"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_vol_ingest.py::test_normalize_vol_long_format -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'ingest.vol'`).

- [ ] **Step 3: Write minimal implementation**

```python
# atlas/ingest/vol.py
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yfinance as yf

from config import DATA_RAW, PRICE_START, VOL_FRED_FALLBACK, VOL_SERIES
from ingest._base import atomic_write_parquet, with_retry
from ingest.macro import fetch_macro
from ingest.schemas import VOL_SCHEMA


def normalize_vol(raw: pd.DataFrame, series: str) -> pd.DataFrame:
    """Convert a yfinance index OHLC frame into validated long (series,date,close)."""
    close = raw["Close"] if "Close" in raw.columns else raw.iloc[:, 0]
    df = pd.DataFrame(
        {
            "series": series,
            "date": pd.to_datetime(close.index).tz_localize(None),
            "close": pd.to_numeric(close.to_numpy().ravel(), errors="coerce"),
        }
    )
    df = df.dropna(subset=["close"]).reset_index(drop=True)
    df["close"] = df["close"].astype(float)
    return VOL_SCHEMA.validate(df)


def _from_fred(series: str) -> pd.DataFrame:  # pragma: no cover - network
    """Fallback: pull the FRED equivalent and relabel to the ^-series id."""
    fred_id = VOL_FRED_FALLBACK[series]
    macro = fetch_macro(fred_id)  # columns: series_id, date, value
    return VOL_SCHEMA.validate(
        macro.rename(columns={"value": "close"})[["date", "close"]].assign(series=series)[
            ["series", "date", "close"]
        ]
    )


def fetch_vol(series: str, start: str = PRICE_START) -> pd.DataFrame:  # pragma: no cover - network
    """Download one vol index's history; fall back to FRED for ^VIX/^VXN."""
    def _dl() -> pd.DataFrame:
        raw = yf.download(series, start=start, auto_adjust=False, progress=False)
        if raw.empty:
            raise RuntimeError(f"empty download for {series}")
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        return normalize_vol(raw, series)

    try:
        return with_retry(_dl)
    except Exception:
        if series in VOL_FRED_FALLBACK:
            return _from_fred(series)
        raise


def run() -> None:  # pragma: no cover - network
    out_dir = Path(DATA_RAW) / "vol"
    wrote_any = False
    for series in VOL_SERIES:
        try:
            df = fetch_vol(series)
        except Exception as exc:  # noqa: BLE001 - tolerate a flaky series, keep going
            print(f"vol: SKIP {series} ({type(exc).__name__}: {exc})")
            continue
        atomic_write_parquet(df, out_dir / f"{series.lstrip('^')}.parquet")
        wrote_any = True
        print(f"vol: wrote {len(df)} rows for {series}")
    if not wrote_any:
        empty = VOL_SCHEMA.validate(
            pd.DataFrame({"series": pd.Series([], dtype="object"),
                          "date": pd.Series([], dtype="datetime64[ns]"),
                          "close": pd.Series([], dtype="float64")})
        )
        atomic_write_parquet(empty, out_dir / "_empty.parquet")
        print("vol: all series failed; wrote empty fallback parquet")


if __name__ == "__main__":
    run()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_vol_ingest.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ingest/vol.py tests/test_vol_ingest.py
git commit -m "feat: ingest vol indices (VIX complex + VXN) with FRED fallback"
```

---

### Task 3: Ingest QQQ via AUX_TICKERS

**Files:**
- Modify: `atlas/ingest/prices.py:run`
- Test: `atlas/tests/test_prices.py` (extend)

- [ ] **Step 1: Write the failing test**

`run()` is `# pragma: no cover` (network), so assert on its source that the default ticker list now pulls in `AUX_TICKERS` (which already exists from Task 1).

```python
# append to atlas/tests/test_prices.py
import inspect

def test_run_default_ticker_list_includes_aux_tickers():
    import ingest.prices as p
    from config import AUX_TICKERS
    assert "QQQ" in AUX_TICKERS
    assert "AUX_TICKERS" in inspect.getsource(p.run)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_prices.py::test_run_default_ticker_list_includes_aux_tickers -v`
Expected: FAIL (`run` source does not yet reference `AUX_TICKERS`).

- [ ] **Step 3: Write minimal implementation**

In `atlas/ingest/prices.py`, update `run`'s default and import:

```python
def run(tickers: list[str] | None = None) -> None:  # pragma: no cover
    from config import AUX_TICKERS, FACTOR_TICKERS

    tickers = tickers or (UNIVERSE + list(FACTOR_TICKERS.values()) + AUX_TICKERS)
    out_dir = Path(DATA_RAW) / "prices"
    for t in tickers:
        df = fetch_prices(t)
        atomic_write_parquet(df, out_dir / f"{t}.parquet")
        print(f"prices: wrote {len(df)} rows for {t}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_prices.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ingest/prices.py tests/test_prices.py
git commit -m "feat: ingest QQQ (VXN matched underlying) via AUX_TICKERS"
```

---

### Task 4: dbt models — `stg_vol` + `vol_indices`

**Files:**
- Create: `atlas/dbt_project/models/staging/stg_vol.sql`
- Create: `atlas/dbt_project/models/marts/vol_indices.sql`
- Modify: `atlas/dbt_project/models/staging/schema.yml`, `atlas/dbt_project/models/marts/schema.yml`
- Test: `atlas/tests/test_dbt_models.py` (extend)

- [ ] **Step 1: Write the failing test**

```python
# append to atlas/tests/test_dbt_models.py
def test_vol_models_exist_and_select_expected_columns():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "dbt_project" / "models"
    stg = (root / "staging" / "stg_vol.sql").read_text()
    mart = (root / "marts" / "vol_indices.sql").read_text()
    assert "read_parquet" in stg and "vol/*.parquet" in stg
    assert "stg_vol" in mart
    for col in ("series", "date", "close"):
        assert col in stg and col in mart
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_dbt_models.py::test_vol_models_exist_and_select_expected_columns -v`
Expected: FAIL (`FileNotFoundError`).

- [ ] **Step 3: Write minimal implementation**

`atlas/dbt_project/models/staging/stg_vol.sql` (mirror `stg_macro.sql`):

```sql
with src as (
    select * from read_parquet('{{ env_var("ATLAS_DATA_RAW", "../data/raw") }}/vol/*.parquet')
)
select
    cast(series as varchar) as series,
    cast(date as date)      as date,
    cast(close as double)   as close
from src
where close is not null
```

`atlas/dbt_project/models/marts/vol_indices.sql`:

```sql
select series, date, close
from {{ ref('stg_vol') }}
```

Append to `atlas/dbt_project/models/staging/schema.yml`:

```yaml
  - name: stg_vol
    description: "Raw implied-vol index history (VIX complex + VXN), long format."
    columns:
      - name: series
        tests: [not_null]
      - name: date
        tests: [not_null]
      - name: close
        tests: [not_null]
```

Append to `atlas/dbt_project/models/marts/schema.yml`:

```yaml
  - name: vol_indices
    description: "Implied-vol index levels used by H6/H7."
    columns:
      - name: series
        tests: [not_null]
      - name: date
        tests: [not_null]
```

> If `staging/schema.yml` / `marts/schema.yml` start with `version: 2` and a `models:` list, append these entries under the existing `models:` key (match indentation). Open each file first to confirm structure.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_dbt_models.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dbt_project/models/staging/stg_vol.sql dbt_project/models/marts/vol_indices.sql \
        dbt_project/models/staging/schema.yml dbt_project/models/marts/schema.yml \
        tests/test_dbt_models.py
git commit -m "feat: dbt stg_vol + vol_indices models"
```

---

## Phase 1 — H6: variance risk premium

### Task 5: Realized vol + VRP series (pure)

**Files:**
- Create: `atlas/analysis/vol_premium.py`
- Test: `atlas/tests/test_vol_premium.py`

- [ ] **Step 1: Write the failing test**

```python
# atlas/tests/test_vol_premium.py
import numpy as np
import pandas as pd

def _const_vol_returns(n, sigma_daily, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2015-01-01", periods=n)
    return pd.Series(rng.normal(0, sigma_daily, n), index=idx)

def test_realized_var_annualized_recovers_known_sigma():
    from analysis.vol_premium import realized_var_annualized
    sigma_daily = 0.01
    r = _const_vol_returns(252 * 4, sigma_daily, seed=1)
    rv = realized_var_annualized(r.to_numpy())
    # annualized variance ~= 252 * sigma_daily**2
    assert abs(rv - 252 * sigma_daily**2) < 0.25 * (252 * sigma_daily**2)

def test_vrp_series_positive_when_implied_above_realized():
    from analysis.vol_premium import vrp_series
    # realized daily sigma 1% -> annualized vol ~16%; set implied at 25% (> realized)
    r = _const_vol_returns(600, 0.01, seed=2)
    implied = pd.Series(25.0, index=r.index)  # vol points
    vrp = vrp_series(implied, r, horizon=21)
    assert vrp.notna().sum() > 100
    assert vrp.mean() > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_vol_premium.py -v`
Expected: FAIL (`ModuleNotFoundError: analysis.vol_premium`).

- [ ] **Step 3: Write minimal implementation**

```python
# atlas/analysis/vol_premium.py
"""H6: variance risk premium + implied-vol information content (pure functions).

VRP_t = implied_variance_t - realized_variance over (t, t+horizon]. Implied is in
vol POINTS (VIX=20 -> 0.20). Overlapping forward windows -> block bootstrap for the
mean CI. IV information content = incremental out-of-sample R2 of (IV + lagged RV)
over (lagged RV) at forecasting forward RV, via anchored walk-forward.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analysis.oos import walk_forward_folds
from analysis.significance import auto_block_length


def realized_var_annualized(returns: np.ndarray) -> float:
    """Annualized realized variance from daily log returns (zero-mean estimator)."""
    r = np.asarray(returns, dtype=float)
    if len(r) < 2:
        return float("nan")
    return float(252.0 * np.mean(r**2))


def vrp_series(implied_vol_pts: pd.Series, underlying_returns: pd.Series,
               *, horizon: int) -> pd.Series:
    """Per-day VRP = (IV/100)^2 - realized variance over the next `horizon` days."""
    iv = implied_vol_pts.sort_index().astype(float)
    r = underlying_returns.sort_index().astype(float)
    common = iv.index.intersection(r.index)
    iv = iv.loc[common]
    r = r.loc[common]
    vals = {}
    rvals = r.to_numpy()
    for i, t in enumerate(iv.index):
        window = rvals[i + 1: i + 1 + horizon]
        if len(window) < max(5, horizon // 2):
            continue
        implied_var = (iv.iloc[i] / 100.0) ** 2
        vals[t] = implied_var - realized_var_annualized(window)
    return pd.Series(vals).sort_index()


def mean_block_ci(x: np.ndarray, *, iters: int, seed: int, ci: float = 0.90) -> tuple[float, float, float]:
    """Stationary-block-bootstrap CI for the mean of an autocorrelated series."""
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    n = len(x)
    if n < 2:
        return float("nan"), float("nan"), float("nan")
    block = auto_block_length(x)
    rng = np.random.default_rng(seed)
    nblocks = int(np.ceil(n / block))
    draws = []
    for _ in range(iters):
        starts = rng.integers(0, max(1, n - block + 1), size=nblocks)
        idx = np.concatenate([np.arange(s, s + block) for s in starts])[:n]
        draws.append(float(np.mean(x[idx])))
    lo = float(np.percentile(draws, (1 - ci) / 2 * 100))
    hi = float(np.percentile(draws, (1 + ci) / 2 * 100))
    return lo, hi, float(np.mean(x))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_vol_premium.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add analysis/vol_premium.py tests/test_vol_premium.py
git commit -m "feat: H6 realized-var + VRP series + mean block CI"
```

---

### Task 6: IV→RV incremental OOS R² (pure)

**Files:**
- Modify: `atlas/analysis/vol_premium.py`
- Test: `atlas/tests/test_vol_premium.py` (extend)

- [ ] **Step 1: Write the failing test**

```python
# append to atlas/tests/test_vol_premium.py
def test_incremental_oos_r2_positive_when_iv_carries_signal():
    from analysis.vol_premium import incremental_oos_r2
    rng = np.random.default_rng(3)
    n = 1500
    idx = pd.bdate_range("2010-01-01", periods=n)
    iv = pd.Series(20 + 5 * np.sin(np.arange(n) / 40.0), index=idx)      # smooth implied
    # forward RV driven mostly by IV (in variance units), small noise + weak RV-lag
    fwd_rv = pd.Series((iv.to_numpy() / 100.0) ** 2 + rng.normal(0, 0.0003, n), index=idx)
    lag_rv = fwd_rv.shift(21).bfill()
    r2 = incremental_oos_r2(iv=iv, fwd_rv=fwd_rv, lag_rv=lag_rv,
                            test_days=252, step_days=252, init_train_frac=0.5)
    assert r2 > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_vol_premium.py::test_incremental_oos_r2_positive_when_iv_carries_signal -v`
Expected: FAIL (`AttributeError: incremental_oos_r2`).

- [ ] **Step 3: Write minimal implementation**

Append to `atlas/analysis/vol_premium.py`:

```python
def _ols_fit_predict(x_tr: np.ndarray, y_tr: np.ndarray, x_te: np.ndarray) -> np.ndarray:
    A = np.column_stack([np.ones(len(x_tr)), x_tr])
    beta, *_ = np.linalg.lstsq(A, y_tr, rcond=None)
    return np.column_stack([np.ones(len(x_te)), x_te]) @ beta


def _oos_sse(features_tr, y_tr, features_te, y_te) -> float:
    pred = _ols_fit_predict(features_tr, y_tr, features_te)
    return float(np.sum((y_te - pred) ** 2))


def incremental_oos_r2(*, iv: pd.Series, fwd_rv: pd.Series, lag_rv: pd.Series,
                       test_days: int, step_days: int, init_train_frac: float) -> float:
    """OOS R2 improvement of (IV + lagged RV) vs (lagged RV) at forecasting fwd RV.

    Pooled over anchored walk-forward folds: 1 - SSE_full / SSE_baseline. Positive =>
    implied vol adds out-of-sample forecast content beyond the RV autoregressor.
    """
    df = pd.concat([iv.rename("iv"), fwd_rv.rename("y"), lag_rv.rename("lag")],
                   axis=1, join="inner").dropna()
    if len(df) < 4 * test_days:
        return float("nan")
    folds = walk_forward_folds(df.index, test_days=test_days, step_days=step_days,
                               init_train_frac=init_train_frac, embargo=0)
    sse_full, sse_base = 0.0, 0.0
    for tr_idx, te_idx in folds:
        tr, te = df.loc[tr_idx], df.loc[te_idx]
        y_tr, y_te = tr["y"].to_numpy(), te["y"].to_numpy()
        sse_base += _oos_sse(tr[["lag"]].to_numpy(), y_tr, te[["lag"]].to_numpy(), y_te)
        sse_full += _oos_sse(tr[["lag", "iv"]].to_numpy(), y_tr, te[["lag", "iv"]].to_numpy(), y_te)
    if sse_base == 0:
        return float("nan")
    return float(1.0 - sse_full / sse_base)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_vol_premium.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add analysis/vol_premium.py tests/test_vol_premium.py
git commit -m "feat: H6 incremental OOS R2 (IV vs RV-only forecast)"
```

---

### Task 7: `vol_premium_table` driver

**Files:**
- Modify: `atlas/analysis/vol_premium.py`
- Test: `atlas/tests/test_vol_premium.py` (extend)

- [ ] **Step 1: Write the failing test**

```python
# append to atlas/tests/test_vol_premium.py
def _make_returns_df(tickers, n=900, seed=4):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2012-01-01", periods=n)
    frames = []
    for t in tickers:
        frames.append(pd.DataFrame({"ticker": t, "date": idx,
                                    "log_return": rng.normal(0, 0.01, n)}))
    return pd.concat(frames, ignore_index=True)

def _make_vol_df(series, n=900, level=22.0, seed=5):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2012-01-01", periods=n)
    frames = []
    for s in series:
        frames.append(pd.DataFrame({"series": s, "date": idx,
                                    "close": level + rng.normal(0, 1.0, n)}))
    return pd.concat(frames, ignore_index=True)

def test_vol_premium_table_shape_and_positive_vrp():
    from analysis.vol_premium import vol_premium_table
    from config import H6_PAIRS, H6_RV_HORIZON, BOOTSTRAP_ITERS, RANDOM_SEED
    returns = _make_returns_df(["SPY", "QQQ"])
    vol = _make_vol_df(["^VIX", "^VXN"], level=25.0)  # implied >> realized(~16%)
    out = vol_premium_table(vol, returns, pairs=H6_PAIRS, horizon=H6_RV_HORIZON,
                            iters=BOOTSTRAP_ITERS, seed=RANDOM_SEED)
    assert set(out["pair"]) == {"^VIX~SPY", "^VXN~QQQ"}
    for col in ("mean_vrp", "vrp_lo", "vrp_hi", "incremental_oos_r2", "n_obs"):
        assert col in out.columns
    assert (out["mean_vrp"] > 0).all()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_vol_premium.py::test_vol_premium_table_shape_and_positive_vrp -v`
Expected: FAIL (`AttributeError: vol_premium_table`).

- [ ] **Step 3: Write minimal implementation**

Append to `atlas/analysis/vol_premium.py`:

```python
def vol_premium_table(vol: pd.DataFrame, returns: pd.DataFrame, *,
                      pairs: tuple[tuple[str, str], ...], horizon: int,
                      iters: int, seed: int) -> pd.DataFrame:
    """One row per (implied series, underlying) pair: VRP mean+CI and IV info content."""
    iv_by = {s: g.set_index("date")["close"].sort_index() for s, g in vol.groupby("series")}
    ret_by = {t: g.set_index("date")["log_return"].sort_index()
              for t, g in returns.groupby("ticker")}
    rows = []
    for implied, under in pairs:
        if implied not in iv_by or under not in ret_by:
            continue
        iv = iv_by[implied]
        r = ret_by[under]
        vrp = vrp_series(iv, r, horizon=horizon)
        if vrp.empty:
            continue
        lo, hi, mean = mean_block_ci(vrp.to_numpy(), iters=iters, seed=seed)
        # forward realized variance aligned to each day t (same horizon)
        fwd_rv = pd.Series(
            {t: realized_var_annualized(r.sort_index().to_numpy()[i + 1: i + 1 + horizon])
             for i, t in enumerate(r.sort_index().index)}
        ).reindex(iv.index).dropna()
        aligned_iv = iv.reindex(fwd_rv.index)
        lag_rv = fwd_rv.shift(horizon)
        r2 = incremental_oos_r2(iv=aligned_iv, fwd_rv=fwd_rv, lag_rv=lag_rv,
                                test_days=252, step_days=252, init_train_frac=0.5)
        rows.append({
            "pair": f"{implied}~{under}", "implied": implied, "underlying": under,
            "mean_vrp": mean, "vrp_lo": lo, "vrp_hi": hi,
            "incremental_oos_r2": r2, "n_obs": int(len(vrp)),
        })
    return pd.DataFrame(rows)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_vol_premium.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add analysis/vol_premium.py tests/test_vol_premium.py
git commit -m "feat: H6 vol_premium_table driver"
```

---

### Task 8: `h6_record` + wire into `build_signal_records`

**Files:**
- Modify: `atlas/analysis/signals.py`
- Test: `atlas/tests/test_signals.py` (extend)

- [ ] **Step 1: Write the failing test**

```python
# append to atlas/tests/test_signals.py
import pandas as pd

def test_h6_record_confirmed_when_premium_and_info():
    from analysis.signals import h6_record
    rows = pd.DataFrame([
        {"pair": "^VIX~SPY", "implied": "^VIX", "underlying": "SPY",
         "mean_vrp": 0.02, "vrp_lo": 0.012, "vrp_hi": 0.03,
         "incremental_oos_r2": 0.08, "n_obs": 2500},
        {"pair": "^VXN~QQQ", "implied": "^VXN", "underlying": "QQQ",
         "mean_vrp": 0.03, "vrp_lo": 0.02, "vrp_hi": 0.04,
         "incremental_oos_r2": 0.05, "n_obs": 2500},
    ])
    rec = h6_record(rows)
    assert rec["id"] == "H6"
    assert rec["verdict"] == "confirmed"
    assert rec["chart"]["type"] == "vrp_term"
    assert rec["stat"]["n"] == 2500
    assert len(rec["evidence_chain"]) >= 2

def test_h6_record_null_when_no_premium():
    from analysis.signals import h6_record
    rows = pd.DataFrame([
        {"pair": "^VIX~SPY", "implied": "^VIX", "underlying": "SPY",
         "mean_vrp": 0.001, "vrp_lo": -0.004, "vrp_hi": 0.006,
         "incremental_oos_r2": -0.01, "n_obs": 2500},
    ])
    assert h6_record(rows)["verdict"] == "null"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_signals.py -k h6 -v`
Expected: FAIL (`ImportError: cannot import name 'h6_record'`).

- [ ] **Step 3: Write minimal implementation**

Add to `atlas/analysis/signals.py` (after `h2_record`):

```python
def h6_record(rows: pd.DataFrame) -> dict:
    """H6: variance risk premium + implied-vol information content."""
    elig = rows[rows["mean_vrp"].notna()]
    if not len(elig):
        verdict, best, n = "null", pd.Series(dtype=float), 0
    else:
        best = elig.sort_values("mean_vrp", ascending=False).iloc[0]
        n = int(best["n_obs"])
        premium = best["mean_vrp"] > 0 and best["vrp_lo"] > 0
        info = best["incremental_oos_r2"] > 0
        neg_premium = best["mean_vrp"] < 0 and best["vrp_hi"] < 0
        if premium and info:
            verdict = "confirmed"
        elif premium or info:
            verdict = "suggestive"
        elif neg_premium:
            verdict = "contradicts"
        else:
            verdict = "null"
    interp = {
        "confirmed": "options price risk informatively (premium + forecast content)",
        "suggestive": "partial: premium or forecast content, not both",
        "null": "no measurable premium / no added forecast content",
        "contradicts": "implied below realized (negative premium)",
    }[verdict]
    return {
        "id": "H6", "title": "Implied vol carries information: the variance risk premium",
        "horizon": "1 month (21d realized)",
        "claim": "Implied variance exceeds subsequent realized variance, and IV forecasts RV",
        "mechanism": f"Options market charges a variance risk premium -- verdict: {interp}",
        "verdict": verdict,
        "evidence_chain": [
            {"stage": "mean variance risk premium", "metric": "var", "value": _num(best.get("mean_vrp"))},
            {"stage": "VRP 90% CI low", "metric": "var", "value": _num(best.get("vrp_lo"))},
            {"stage": "IV incremental OOS R2", "metric": "r2", "value": _num(best.get("incremental_oos_r2"))},
        ],
        "stat": {"name": "mean_vrp", "value": _num(best.get("mean_vrp")),
                 "ci": [_num(best.get("vrp_lo")), _num(best.get("vrp_hi"))],
                 "q_value": None, "n": n},
        "caveats": [
            "Index/sector level: VIX<->SPY, VXN<->QQQ. No free semis implied series exists.",
            "Overlapping 21d windows -> block-bootstrap CI; observational, no costs.",
        ],
        "chart": {"type": "vrp_term", "ref": "h6"},
        "detail_rows": elig[["pair", "mean_vrp", "vrp_lo", "vrp_hi",
                             "incremental_oos_r2", "n_obs"]].to_dict("records"),
    }
```

In `build_signal_records`, after the H2 block, add:

```python
    has_h6 = con.execute("SELECT count(*) FROM information_schema.tables "
                         "WHERE table_name='vol_premium'").fetchone()[0] > 0
    if has_h6:
        h6 = con.execute('SELECT * FROM vol_premium').df()
        if len(h6):
            records.append(h6_record(h6))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_signals.py -k h6 -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add analysis/signals.py tests/test_signals.py
git commit -m "feat: H6 signal record + build_signal_records wiring"
```

---

## Phase 2 — H7: vol term-structure timing

### Task 9: Predictor slope + forward-return aligner (pure)

**Files:**
- Create: `atlas/analysis/vol_termstructure.py`
- Test: `atlas/tests/test_vol_termstructure.py`

- [ ] **Step 1: Write the failing test**

```python
# atlas/tests/test_vol_termstructure.py
import numpy as np
import pandas as pd

def test_termstructure_slope_ratio():
    from analysis.vol_termstructure import termstructure_slope
    idx = pd.bdate_range("2015-01-01", periods=5)
    vix = pd.Series([20, 22, 18, 30, 15], index=idx, dtype=float)
    vix3m = pd.Series([18, 20, 20, 24, 18], index=idx, dtype=float)
    s = termstructure_slope(vix, vix3m)
    assert np.isclose(s.iloc[0], 20 / 18)
    assert (s.index == idx).all()

def test_aligned_forward_returns_planted_relationship():
    from analysis.vol_termstructure import aligned_forward
    rng = np.random.default_rng(7)
    n = 800
    idx = pd.bdate_range("2012-01-01", periods=n)
    s = pd.Series(1.0 + rng.normal(0, 0.1, n), index=idx)         # predictor
    # forward 21d return positively driven by s (planted)
    base = pd.Series(rng.normal(0, 0.01, n), index=idx)
    log_ret = base + 0.02 * (s.shift(21).fillna(1.0) - 1.0)
    x, y = aligned_forward(s, log_ret, horizon=21)
    assert len(x) == len(y) > 300
    assert np.corrcoef(x, y)[0, 1] > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_vol_termstructure.py -v`
Expected: FAIL (`ModuleNotFoundError: analysis.vol_termstructure`).

- [ ] **Step 3: Write minimal implementation**

```python
# atlas/analysis/vol_termstructure.py
"""H7: does the vol term-structure slope time forward sector returns? (pure functions)

Predictor s_t = VIX_t / VIX3M_t (>1 backwardation/stress, <1 contango/calm). One-sided
declared direction: stress predicts POSITIVE forward returns. Targets x horizons form a
declared family; per-cell selection-aware p (single-series perturbation null), BH-FDR
over eligible cells, block-bootstrap slope CI, anchored walk-forward sign-retention.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analysis.fundamentals_leadlag import bootstrap_slope_ci
from analysis.oos import walk_forward_folds
from analysis.significance import block_resample_one


def termstructure_slope(vix: pd.Series, vix3m: pd.Series) -> pd.Series:
    """VIX / VIX3M ratio on the shared dates (drops zero/NaN denominators)."""
    df = pd.concat([vix.rename("a"), vix3m.rename("b")], axis=1, join="inner").dropna()
    df = df[df["b"] > 0]
    return (df["a"] / df["b"]).sort_index()


def aligned_forward(slope: pd.Series, log_return: pd.Series, *, horizon: int
                    ) -> tuple[np.ndarray, np.ndarray]:
    """Pair s_t with the summed forward log return over (t, t+horizon]."""
    s = slope.sort_index()
    r = log_return.sort_index()
    common = s.index.intersection(r.index)
    s = s.loc[common]
    rvals = r.loc[common].to_numpy()
    xs, ys = [], []
    for i, t in enumerate(s.index):
        window = rvals[i + 1: i + 1 + horizon]
        if len(window) < max(5, horizon // 2):
            continue
        xs.append(float(s.iloc[i]))
        ys.append(float(np.sum(window)))
    return np.asarray(xs), np.asarray(ys)


def _corr_slope(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return np.nan, np.nan
    return float(np.corrcoef(x, y)[0, 1]), float(np.polyfit(x, y, 1)[0])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_vol_termstructure.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add analysis/vol_termstructure.py tests/test_vol_termstructure.py
git commit -m "feat: H7 term-structure slope + forward-return aligner"
```

---

### Task 10: Per-cell selection-aware p + OOS sign-rate (pure)

**Files:**
- Modify: `atlas/analysis/vol_termstructure.py`
- Test: `atlas/tests/test_vol_termstructure.py` (extend)

- [ ] **Step 1: Write the failing test**

```python
# append to atlas/tests/test_vol_termstructure.py
def test_selection_pvalue_small_when_signal_strong():
    from analysis.vol_termstructure import selection_pvalue_one_series
    rng = np.random.default_rng(11)
    x = rng.normal(1.0, 0.1, 500)
    y = 0.5 * (x - 1.0) + rng.normal(0, 0.02, 500)   # strong positive relation
    p = selection_pvalue_one_series(x, y, iters=300, seed=1)
    assert p < 0.05

def test_selection_pvalue_large_when_no_signal():
    from analysis.vol_termstructure import selection_pvalue_one_series
    rng = np.random.default_rng(12)
    x = rng.normal(1.0, 0.1, 500)
    y = rng.normal(0, 0.02, 500)                      # unrelated
    p = selection_pvalue_one_series(x, y, iters=300, seed=1)
    assert p > 0.10

def test_oos_sign_rate_high_for_stable_positive():
    from analysis.vol_termstructure import oos_sign_rate
    rng = np.random.default_rng(13)
    n = 1600
    idx = pd.bdate_range("2010-01-01", periods=n)
    s = pd.Series(1.0 + rng.normal(0, 0.1, n), index=idx)
    log_ret = pd.Series(rng.normal(0, 0.01, n), index=idx) + \
        0.03 * (s.shift(21).fillna(1.0) - 1.0)
    rate = oos_sign_rate(s, log_ret, horizon=21,
                         test_days=252, step_days=252, init_train_frac=0.5)
    assert rate >= 0.6
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_vol_termstructure.py -k "selection or oos_sign" -v`
Expected: FAIL (`AttributeError`).

- [ ] **Step 3: Write minimal implementation**

Append to `atlas/analysis/vol_termstructure.py`:

```python
def selection_pvalue_one_series(x: np.ndarray, y: np.ndarray, *, iters: int, seed: int) -> float:
    """One-sided (positive) selection-aware p via single-series block resample of x.

    Null breaks the x->y relation while preserving x's autocorrelation. p = P(null
    signed corr >= observed). +1 smoothing, matching the project's other estimators.
    """
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    obs, _ = _corr_slope(x, y)
    if not np.isfinite(obs):
        return 1.0
    from analysis.significance import auto_block_length
    block = auto_block_length(x)
    rng = np.random.default_rng(seed)
    count = 0
    for _ in range(iters):
        xb = block_resample_one(x, block=block, rng=rng)
        c, _ = _corr_slope(xb, y)
        if np.isfinite(c) and c >= obs:
            count += 1
    return (count + 1) / (iters + 1)


def oos_sign_rate(slope: pd.Series, log_return: pd.Series, *, horizon: int,
                  test_days: int, step_days: int, init_train_frac: float) -> float:
    """Anchored walk-forward: fraction of folds whose test slope matches train slope sign."""
    s = slope.sort_index()
    r = log_return.sort_index()
    common = s.index.intersection(r.index)
    paired = pd.concat([s.loc[common].rename("s"), r.loc[common].rename("r")], axis=1).dropna()
    folds = walk_forward_folds(paired.index, test_days=test_days, step_days=step_days,
                               init_train_frac=init_train_frac, embargo=horizon)
    signs = []
    for tr_idx, te_idx in folds:
        xtr, ytr = aligned_forward(paired.loc[tr_idx, "s"], paired.loc[tr_idx, "r"], horizon=horizon)
        xte, yte = aligned_forward(paired.loc[te_idx, "s"], paired.loc[te_idx, "r"], horizon=horizon)
        _, str_ = _corr_slope(xtr, ytr)
        _, ste = _corr_slope(xte, yte)
        if np.isfinite(str_) and np.isfinite(ste) and str_ != 0:
            signs.append(np.sign(str_) == np.sign(ste))
    return float(np.mean(signs)) if signs else 0.0
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_vol_termstructure.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add analysis/vol_termstructure.py tests/test_vol_termstructure.py
git commit -m "feat: H7 selection-aware p + OOS sign-rate"
```

---

### Task 11: `vol_termstructure_table` driver (family + BH-FDR)

**Files:**
- Modify: `atlas/analysis/vol_termstructure.py`
- Test: `atlas/tests/test_vol_termstructure.py` (extend)

- [ ] **Step 1: Write the failing test**

```python
# append to atlas/tests/test_vol_termstructure.py
def _vol_df(series_levels, n=1000, seed=21):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2011-01-01", periods=n)
    frames = []
    for s, lvl in series_levels.items():
        frames.append(pd.DataFrame({"series": s, "date": idx,
                                    "close": lvl + rng.normal(0, 1.0, n)}))
    return pd.concat(frames, ignore_index=True)

def _ret_df(tickers, n=1000, seed=22):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2011-01-01", periods=n)
    frames = [pd.DataFrame({"ticker": t, "date": idx, "log_return": rng.normal(0, 0.01, n)})
              for t in tickers]
    return pd.concat(frames, ignore_index=True)

def test_vol_termstructure_table_family_and_fdr_columns():
    from analysis.vol_termstructure import vol_termstructure_table
    from config import (H7_PREDICTOR, H7_TARGETS, H7_HORIZONS, BOOTSTRAP_ITERS, RANDOM_SEED)
    vol = _vol_df({"^VIX": 20.0, "^VIX3M": 21.0})
    returns = _ret_df(list(H7_TARGETS))
    out = vol_termstructure_table(vol, returns, predictor=H7_PREDICTOR,
                                  targets=H7_TARGETS, horizons=H7_HORIZONS,
                                  iters=BOOTSTRAP_ITERS, seed=RANDOM_SEED)
    assert len(out) == len(H7_TARGETS) * len(H7_HORIZONS)
    for col in ("target", "horizon", "corr", "slope", "slope_lo", "slope_hi",
                "p_selection", "q_value", "oos_sign_rate", "n_obs", "contradicts_thesis"):
        assert col in out.columns
    assert out["q_value"].notna().all()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_vol_termstructure.py::test_vol_termstructure_table_family_and_fdr_columns -v`
Expected: FAIL (`AttributeError: vol_termstructure_table`).

- [ ] **Step 3: Write minimal implementation**

Append to `atlas/analysis/vol_termstructure.py`:

```python
def vol_termstructure_table(vol: pd.DataFrame, returns: pd.DataFrame, *,
                            predictor: tuple[str, str], targets: tuple[str, ...],
                            horizons: tuple[int, ...], iters: int, seed: int) -> pd.DataFrame:
    """One row per (target, horizon): slope of forward return on the term-structure slope,
    with per-cell selection-aware p, BH-FDR over eligible cells, CI, and OOS sign-rate."""
    from analysis.leadlag import bh_fdr

    iv_by = {s: g.set_index("date")["close"].sort_index() for s, g in vol.groupby("series")}
    ret_by = {t: g.set_index("date")["log_return"].sort_index()
              for t, g in returns.groupby("ticker")}
    front, back = predictor
    if front not in iv_by or back not in iv_by:
        return pd.DataFrame()
    s = termstructure_slope(iv_by[front], iv_by[back])

    rows = []
    for target in targets:
        if target not in ret_by:
            continue
        r = ret_by[target]
        for h in horizons:
            x, y = aligned_forward(s, r, horizon=h)
            corr, slope = _corr_slope(x, y)
            if not np.isfinite(corr) or len(x) < 10:
                rows.append({"target": target, "horizon": h, "corr": np.nan, "slope": np.nan,
                             "slope_lo": np.nan, "slope_hi": np.nan, "p_selection": 1.0,
                             "oos_sign_rate": 0.0, "n_obs": int(len(x)),
                             "contradicts_thesis": False})
                continue
            p = selection_pvalue_one_series(x, y, iters=iters, seed=seed)
            lo, hi, _ = bootstrap_slope_ci(x, y, block=8, iters=iters, seed=seed)
            sign = oos_sign_rate(s, r, horizon=h, test_days=252, step_days=252,
                                 init_train_frac=0.5)
            rows.append({"target": target, "horizon": h, "corr": float(corr),
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

Run: `uv run pytest tests/test_vol_termstructure.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add analysis/vol_termstructure.py tests/test_vol_termstructure.py
git commit -m "feat: H7 vol_termstructure_table driver (family + BH-FDR)"
```

---

### Task 12: `h7_record` + wire into `build_signal_records`

**Files:**
- Modify: `atlas/analysis/signals.py`
- Test: `atlas/tests/test_signals.py` (extend)

- [ ] **Step 1: Write the failing test**

```python
# append to atlas/tests/test_signals.py
def test_h7_record_null_surfaces_min_q_cell():
    from analysis.signals import h7_record
    rows = pd.DataFrame([
        {"target": "SPY", "horizon": 21, "corr": 0.04, "slope": 0.5, "slope_lo": -0.2,
         "slope_hi": 1.2, "p_selection": 0.30, "q_value": 0.55, "oos_sign_rate": 0.5,
         "n_obs": 2000, "contradicts_thesis": False},
        {"target": "SOXX", "horizon": 63, "corr": 0.06, "slope": 0.8, "slope_lo": -0.1,
         "slope_hi": 1.6, "p_selection": 0.12, "q_value": 0.40, "oos_sign_rate": 0.55,
         "n_obs": 2000, "contradicts_thesis": False},
    ])
    rec = h7_record(rows)
    assert rec["id"] == "H7"
    assert rec["verdict"] == "null"
    assert rec["chart"]["type"] == "termstructure_timing"
    # surfaced cell = smallest q
    assert rec["stat"]["q_value"] == 0.40

def test_h7_record_confirmed_when_cell_passes():
    from analysis.signals import h7_record
    rows = pd.DataFrame([
        {"target": "SOXX", "horizon": 21, "corr": 0.12, "slope": 1.1, "slope_lo": 0.3,
         "slope_hi": 1.9, "p_selection": 0.01, "q_value": 0.05, "oos_sign_rate": 0.7,
         "n_obs": 2000, "contradicts_thesis": False},
    ])
    assert h7_record(rows)["verdict"] == "confirmed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_signals.py -k h7 -v`
Expected: FAIL (`ImportError: cannot import name 'h7_record'`).

- [ ] **Step 3: Write minimal implementation**

Add to `atlas/analysis/signals.py` (after `h6_record`), mirroring `h5_record`'s select-then-classify:

```python
def h7_record(rows: pd.DataFrame) -> dict:
    """H7: vol term-structure slope as a forward-return timer."""
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
        "confirmed": "harvestable timing edge (not priced in)",
        "suggestive": "weak timing signal",
        "null": "priced in / no reliable timing",
        "contradicts": "term structure times returns the wrong way",
    }[verdict]
    n = int(best.get("n_obs")) if len(elig) else 0
    return {
        "id": "H7", "title": "Does the vol term-structure slope time forward sector returns?",
        "horizon": "1-3 months",
        "claim": "VIX/VIX3M backwardation predicts positive forward sector returns",
        "mechanism": f"Risk-appetite mean reversion -- verdict: {interp}",
        "verdict": verdict,
        "evidence_chain": [
            {"stage": "best-cell corr", "metric": "corr", "value": _num(best.get("corr"))},
            {"stage": "best-cell slope", "metric": "slope", "value": _num(best.get("slope"))},
            {"stage": "OOS sign-retention", "metric": "rate", "value": _num(best.get("oos_sign_rate"))},
        ],
        "stat": {"name": "slope", "value": _num(best.get("slope")),
                 "ci": [_num(best.get("slope_lo")), _num(best.get("slope_hi"))],
                 "q_value": _num(best.get("q_value")), "n": n},
        "caveats": [
            "Predictor is S&P term structure (VXN has no free term structure); targets raw forward returns.",
            "9-cell family (3 targets x 3 horizons), BH-FDR corrected; observational, no costs.",
        ],
        "chart": {"type": "termstructure_timing", "ref": "h7"},
        "detail_rows": elig[["target", "horizon", "corr", "slope", "slope_lo", "slope_hi",
                             "q_value", "oos_sign_rate", "n_obs"]].to_dict("records"),
    }
```

In `build_signal_records`, after the H6 block, add:

```python
    has_h7 = con.execute("SELECT count(*) FROM information_schema.tables "
                         "WHERE table_name='vol_termstructure'").fetchone()[0] > 0
    if has_h7:
        h7 = con.execute('SELECT * FROM vol_termstructure').df()
        if len(h7):
            records.append(h7_record(h7))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_signals.py -k h7 -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add analysis/signals.py tests/test_signals.py
git commit -m "feat: H7 signal record + build_signal_records wiring"
```

---

## Phase 3 — Orchestration wiring

### Task 13: Compute + write `vol_premium` / `vol_termstructure` in `run()`

**Files:**
- Modify: `atlas/analysis/leadlag.py:run` (the `# pragma: no cover` orchestrator)

- [ ] **Step 1 (no unit test — `run()` is pragma-no-cover network glue): add the blocks**

In `analysis/leadlag.py::run()`, after the `event_drift` write block (around line 522) and before `con.close()`, add:

```python
    # H6 + H7: options-implied vol cards (only if vol_indices was built by dbt).
    try:
        vol = con.execute("SELECT series, date, close FROM vol_indices").fetchdf()
    except duckdb.CatalogException:
        vol = pd.DataFrame(columns=["series", "date", "close"])
    if len(vol):
        from config import (H6_PAIRS, H6_RV_HORIZON, H7_HORIZONS, H7_PREDICTOR,
                            H7_TARGETS)
        from analysis.vol_premium import vol_premium_table
        from analysis.vol_termstructure import vol_termstructure_table

        h6 = vol_premium_table(vol, returns, pairs=H6_PAIRS, horizon=H6_RV_HORIZON,
                               iters=BOOTSTRAP_ITERS, seed=RANDOM_SEED)
        con.register("h6t", h6)
        con.execute("CREATE OR REPLACE TABLE vol_premium AS SELECT * FROM h6t")
        con.unregister("h6t")
        print(f"vol_premium: wrote {len(h6)} VRP pair rows")

        h7 = vol_termstructure_table(vol, returns, predictor=H7_PREDICTOR,
                                     targets=H7_TARGETS, horizons=H7_HORIZONS,
                                     iters=BOOTSTRAP_ITERS, seed=RANDOM_SEED)
        con.register("h7t", h7)
        con.execute("CREATE OR REPLACE TABLE vol_termstructure AS SELECT * FROM h7t")
        con.unregister("h7t")
        print(f"vol_termstructure: wrote {len(h7)} (target x horizon) rows")
```

> `returns` already includes SPY/SOXX/IGV/QQQ because `prices/*.parquet` now contains QQQ and the `returns` dbt mart computes log returns for every ticker.

- [ ] **Step 2: Smoke-run the orchestrator locally (requires ingested data)**

Run: `uv run make ingest && uv run make build && uv run make analyze`
Expected: console shows `vol_premium: wrote 2 ...` and `vol_termstructure: wrote 9 ...` (or `0` if vol ingest was skipped offline — acceptable; tables still created empty-safe only when `len(vol)`).

- [ ] **Step 3: Commit**

```bash
git add analysis/leadlag.py
git commit -m "feat: compute + persist vol_premium / vol_termstructure tables"
```

---

### Task 14: Makefile — run `ingest.vol`

**Files:**
- Modify: `atlas/Makefile`

- [ ] **Step 1: Write the failing test**

```python
# append to atlas/tests/test_makefile.py
def test_ingest_target_runs_vol():
    from pathlib import Path
    mk = (Path(__file__).resolve().parents[1] / "Makefile").read_text()
    assert "ingest.vol" in mk
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_makefile.py::test_ingest_target_runs_vol -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

Update the `ingest:` target in `atlas/Makefile`:

```make
ingest:
	python -m ingest.prices && python -m ingest.macro && python -m ingest.vol && python -m ingest.graph && python -m ingest.fundamentals
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_makefile.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add Makefile tests/test_makefile.py
git commit -m "feat: run ingest.vol in make ingest"
```

---

## Phase 4 — Web rendering

### Task 15: SignalCard chart blocks for `vrp_term` + `termstructure_timing`

**Files:**
- Modify: `atlas/web/src/components/SignalCard.svelte`

- [ ] **Step 1: Add the chart blocks (after the `event_drift` block, before `{#each signal.caveats ...}`)**

```svelte
  {#if signal.chart.type === "vrp_term"}
    <p class="legend">Variance risk premium = implied² − realized² (annualized)</p>
    <ul class="edges">
      {#each signal.detail_rows as r}
        <li><span>{r.pair}</span>
          <b>VRP {Number(r.mean_vrp).toFixed(4)}</b>
          <span class="ci">[{Number(r.vrp_lo).toFixed(4)}, {Number(r.vrp_hi).toFixed(4)}]</span>
          <span class="lag">ΔR² {Number(r.incremental_oos_r2).toFixed(3)} · n={r.n_obs}</span></li>
      {/each}
    </ul>
  {/if}
  {#if signal.chart.type === "termstructure_timing"}
    <p class="legend">Slope of forward return on VIX/VIX3M (one-sided, FDR-corrected)</p>
    <ul class="edges">
      {#each signal.detail_rows as r}
        <li><span>{r.target} · {r.horizon}d</span>
          <b>slope {Number(r.slope).toFixed(2)}</b>
          <span class="ci">[{Number(r.slope_lo).toFixed(2)}, {Number(r.slope_hi).toFixed(2)}]</span>
          <span class="lag">q={Number(r.q_value).toFixed(2)} · sign {Number(r.oos_sign_rate).toFixed(2)}</span></li>
      {/each}
    </ul>
  {/if}
```

- [ ] **Step 2: Verify the web build compiles**

Run: `cd web && npm ci && npm run build`
Expected: build succeeds with no new errors (the 2 pre-existing a11y warnings in `NodePanel.svelte`/`Scroller.svelte` are out of scope and may remain).

- [ ] **Step 3: Commit**

```bash
git add web/src/components/SignalCard.svelte
git commit -m "feat: render vrp_term + termstructure_timing signal cards"
```

---

## Phase 5 — Collector B (silent single-name IV pipeline)

### Task 16: Snapshot feature functions + IV_SNAPSHOT_SCHEMA (pure)

**Files:**
- Create: `atlas/ingest/iv_snapshot.py`
- Modify: `atlas/ingest/schemas.py`
- Test: `atlas/tests/test_iv_snapshot.py`

- [ ] **Step 1: Write the failing test**

```python
# atlas/tests/test_iv_snapshot.py
import pandas as pd

def _chain(strikes, ivs, ois, kind):
    return pd.DataFrame({"strike": strikes, "impliedVolatility": ivs,
                         "openInterest": ois, "type": kind})

def test_atm_iv_picks_nearest_strike():
    from ingest.iv_snapshot import atm_iv
    calls = _chain([90, 100, 110], [0.40, 0.30, 0.35], [10, 10, 10], "call")
    assert atm_iv(calls, spot=101.0) == 0.30  # nearest strike = 100

def test_put_call_oi_ratio():
    from ingest.iv_snapshot import put_call_oi_ratio
    calls = _chain([100], [0.3], [200], "call")
    puts = _chain([100], [0.3], [300], "put")
    assert put_call_oi_ratio(calls, puts) == 1.5

def test_iv_snapshot_schema_validates():
    from ingest.schemas import IV_SNAPSHOT_SCHEMA
    df = pd.DataFrame({"ticker": ["NVDA"], "date": pd.to_datetime(["2026-06-05"]),
                       "atm_iv_30d": [0.45], "skew_25d": [0.05],
                       "term_slope": [0.02], "put_call_oi": [1.1]})
    assert len(IV_SNAPSHOT_SCHEMA.validate(df)) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_iv_snapshot.py -v`
Expected: FAIL (`ModuleNotFoundError` / `ImportError: IV_SNAPSHOT_SCHEMA`).

- [ ] **Step 3: Write minimal implementation**

Add to `atlas/ingest/schemas.py`:

```python
IV_SNAPSHOT_SCHEMA = pa.DataFrameSchema(
    {
        "ticker": pa.Column(str, nullable=False),
        "date": pa.Column("datetime64[ns]", nullable=False),
        "atm_iv_30d": pa.Column(float, pa.Check.ge(0), nullable=True),
        "skew_25d": pa.Column(float, nullable=True),
        "term_slope": pa.Column(float, nullable=True),
        "put_call_oi": pa.Column(float, pa.Check.ge(0), nullable=True),
    },
    strict=True,
)
```

Create `atlas/ingest/iv_snapshot.py` (pure feature functions first; network `run` added in Task 18):

```python
# atlas/ingest/iv_snapshot.py
"""Collector B: daily single-name option-chain snapshot -> accumulating panel.

Pure feature functions (unit-tested) + network fetch/run (pragma-no-cover). The panel
persists across CI runs as a release asset (see scripts/publish_release.py)."""
from __future__ import annotations

import numpy as np
import pandas as pd


def atm_iv(calls: pd.DataFrame, *, spot: float) -> float:
    """ATM implied vol = IV at the strike nearest spot."""
    if calls.empty or "impliedVolatility" not in calls:
        return float("nan")
    i = (calls["strike"] - spot).abs().idxmin()
    return float(calls.loc[i, "impliedVolatility"])


def put_call_oi_ratio(calls: pd.DataFrame, puts: pd.DataFrame) -> float:
    c = float(calls["openInterest"].sum()) if not calls.empty else 0.0
    p = float(puts["openInterest"].sum()) if not puts.empty else 0.0
    return p / c if c > 0 else float("nan")


def risk_reversal_skew(calls: pd.DataFrame, puts: pd.DataFrame, *, spot: float) -> float:
    """OTM put IV minus OTM call IV (~25-delta proxy via ±10% moneyness)."""
    if calls.empty or puts.empty:
        return float("nan")
    otm_put = puts.loc[(puts["strike"] - spot * 0.9).abs().idxmin(), "impliedVolatility"]
    otm_call = calls.loc[(calls["strike"] - spot * 1.1).abs().idxmin(), "impliedVolatility"]
    return float(otm_put - otm_call)


def term_slope(near_atm: float, far_atm: float) -> float:
    """Far-minus-near ATM IV (contango>0)."""
    if not np.isfinite(near_atm) or not np.isfinite(far_atm):
        return float("nan")
    return float(far_atm - near_atm)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_iv_snapshot.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ingest/iv_snapshot.py ingest/schemas.py tests/test_iv_snapshot.py
git commit -m "feat: Collector B snapshot feature functions + schema"
```

---

### Task 17: Idempotent panel merge (pure)

**Files:**
- Modify: `atlas/ingest/iv_snapshot.py`
- Test: `atlas/tests/test_iv_snapshot.py` (extend)

- [ ] **Step 1: Write the failing test**

```python
# append to atlas/tests/test_iv_snapshot.py
def test_merge_panel_dedupes_on_ticker_date():
    from ingest.iv_snapshot import merge_panel
    prior = pd.DataFrame({"ticker": ["NVDA"], "date": pd.to_datetime(["2026-06-04"]),
                          "atm_iv_30d": [0.40], "skew_25d": [0.05], "term_slope": [0.02],
                          "put_call_oi": [1.0]})
    today = pd.DataFrame({"ticker": ["NVDA", "AMD"], "date": pd.to_datetime(["2026-06-04", "2026-06-05"]),
                          "atm_iv_30d": [0.99, 0.50], "skew_25d": [0.06, 0.04],
                          "term_slope": [0.03, 0.01], "put_call_oi": [1.1, 0.9]})
    out = merge_panel(prior, today)
    assert len(out) == 2  # NVDA 06-04 replaced (0.99), AMD 06-05 added
    nvda = out[(out.ticker == "NVDA") & (out.date == pd.Timestamp("2026-06-04"))]
    assert float(nvda["atm_iv_30d"].iloc[0]) == 0.99
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_iv_snapshot.py::test_merge_panel_dedupes_on_ticker_date -v`
Expected: FAIL (`AttributeError: merge_panel`).

- [ ] **Step 3: Write minimal implementation**

Append to `atlas/ingest/iv_snapshot.py`:

```python
from ingest.schemas import IV_SNAPSHOT_SCHEMA


def merge_panel(prior: pd.DataFrame, today: pd.DataFrame) -> pd.DataFrame:
    """Append today's rows, keeping the latest row per (ticker, date)."""
    cols = list(IV_SNAPSHOT_SCHEMA.columns)
    combined = pd.concat([prior[cols], today[cols]], ignore_index=True)
    combined = combined.drop_duplicates(subset=["ticker", "date"], keep="last")
    combined = combined.sort_values(["ticker", "date"]).reset_index(drop=True)
    return IV_SNAPSHOT_SCHEMA.validate(combined)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_iv_snapshot.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ingest/iv_snapshot.py tests/test_iv_snapshot.py
git commit -m "feat: Collector B idempotent panel merge"
```

---

### Task 18: Network fetch + `run()` (pragma-no-cover)

**Files:**
- Modify: `atlas/ingest/iv_snapshot.py`

- [ ] **Step 1: Implement fetch + run (no unit test — network/IO glue)**

Append to `atlas/ingest/iv_snapshot.py`:

```python
from datetime import datetime, timezone
from pathlib import Path

from config import DATA_RAW, UNIVERSE
from ingest._base import atomic_write_parquet


def snapshot_one(ticker: str, *, asof: pd.Timestamp) -> dict | None:  # pragma: no cover - network
    """Compute today's IV features for one ticker from the live yfinance chain."""
    import yfinance as yf

    tk = yf.Ticker(ticker)
    expiries = list(tk.options or [])
    if not expiries:
        return None
    spot = float(tk.fast_info.get("last_price") or tk.history(period="1d")["Close"].iloc[-1])
    near = tk.option_chain(expiries[0])
    far = tk.option_chain(expiries[-1])
    near_atm = atm_iv(near.calls, spot=spot)
    far_atm = atm_iv(far.calls, spot=spot)
    return {
        "ticker": ticker, "date": pd.Timestamp(asof.date()),
        "atm_iv_30d": near_atm, "skew_25d": risk_reversal_skew(near.calls, near.puts, spot=spot),
        "term_slope": term_slope(near_atm, far_atm),
        "put_call_oi": put_call_oi_ratio(near.calls, near.puts),
    }


def _load_prior_panel(path: Path) -> pd.DataFrame:  # pragma: no cover - IO
    if path.exists():
        return IV_SNAPSHOT_SCHEMA.validate(pd.read_parquet(path))
    return IV_SNAPSHOT_SCHEMA.validate(pd.DataFrame(
        {c: pd.Series([], dtype="datetime64[ns]" if c == "date" else
                      ("object" if c == "ticker" else "float64"))
         for c in IV_SNAPSHOT_SCHEMA.columns}))


def run() -> None:  # pragma: no cover - network
    asof = pd.Timestamp(datetime.now(timezone.utc))
    panel_path = Path(DATA_RAW) / "iv_snapshots" / "panel.parquet"
    rows = []
    for t in UNIVERSE:
        try:
            row = snapshot_one(t, asof=asof)
        except Exception as exc:  # noqa: BLE001 - tolerate one flaky chain
            print(f"iv_snapshot: SKIP {t} ({type(exc).__name__}: {exc})")
            continue
        if row is not None:
            rows.append(row)
    if not rows:
        print("iv_snapshot: no chains fetched; leaving panel unchanged")
        return
    today = IV_SNAPSHOT_SCHEMA.validate(pd.DataFrame(rows))
    merged = merge_panel(_load_prior_panel(panel_path), today)
    atomic_write_parquet(merged, panel_path)
    print(f"iv_snapshot: panel now {len(merged)} rows ({today['ticker'].nunique()} names today)")


if __name__ == "__main__":
    run()
```

- [ ] **Step 2: Confirm existing tests still pass (no regression)**

Run: `uv run pytest tests/test_iv_snapshot.py -v`
Expected: PASS (pure functions unaffected).

- [ ] **Step 3: Commit**

```bash
git add ingest/iv_snapshot.py
git commit -m "feat: Collector B network fetch + accumulating run()"
```

---

### Task 19: dbt models for the IV panel

**Files:**
- Create: `atlas/dbt_project/models/staging/stg_iv_snapshots.sql`, `atlas/dbt_project/models/marts/iv_snapshots.sql`
- Modify: `atlas/dbt_project/models/staging/schema.yml`, `atlas/dbt_project/models/marts/schema.yml`
- Test: `atlas/tests/test_dbt_models.py` (extend)

- [ ] **Step 1: Write the failing test**

```python
# append to atlas/tests/test_dbt_models.py
def test_iv_snapshot_models_exist():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "dbt_project" / "models"
    stg = (root / "staging" / "stg_iv_snapshots.sql").read_text()
    mart = (root / "marts" / "iv_snapshots.sql").read_text()
    assert "iv_snapshots/panel.parquet" in stg or "iv_snapshots/*.parquet" in stg
    assert "stg_iv_snapshots" in mart
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_dbt_models.py::test_iv_snapshot_models_exist -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

`atlas/dbt_project/models/staging/stg_iv_snapshots.sql`:

```sql
with src as (
    select * from read_parquet('{{ env_var("ATLAS_DATA_RAW", "../data/raw") }}/iv_snapshots/*.parquet')
)
select
    cast(ticker as varchar)  as ticker,
    cast(date as date)       as date,
    cast(atm_iv_30d as double) as atm_iv_30d,
    cast(skew_25d as double)   as skew_25d,
    cast(term_slope as double) as term_slope,
    cast(put_call_oi as double) as put_call_oi
from src
```

`atlas/dbt_project/models/marts/iv_snapshots.sql`:

```sql
select ticker, date, atm_iv_30d, skew_25d, term_slope, put_call_oi
from {{ ref('stg_iv_snapshots') }}
```

Register both in the respective `schema.yml` files (mirror Task 4). Mark the staging source as `config(enabled=...)`-free; an empty glob is tolerated because the panel parquet may not exist yet — to avoid a dbt failure on a missing glob before Collector B first runs, guard with a seed-empty file: the first CI run writes `panel.parquet` before `dbt build` (ingest precedes build in `make all`), so the glob matches. No extra guard needed.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_dbt_models.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dbt_project/models/staging/stg_iv_snapshots.sql dbt_project/models/marts/iv_snapshots.sql \
        dbt_project/models/staging/schema.yml dbt_project/models/marts/schema.yml tests/test_dbt_models.py
git commit -m "feat: dbt models for accumulating IV snapshot panel"
```

---

### Task 20: Persist the panel across CI runs + run Collector B in `make ingest`

**Files:**
- Modify: `atlas/Makefile`
- Modify: `atlas/scripts/publish_release.py`
- Test: `atlas/tests/test_makefile.py`, `atlas/tests/test_publish_release.py` (extend)

- [ ] **Step 1: Write the failing tests**

```python
# append to atlas/tests/test_makefile.py
def test_ingest_target_runs_iv_snapshot():
    from pathlib import Path
    assert "ingest.iv_snapshot" in (Path(__file__).resolve().parents[1] / "Makefile").read_text()

# append to atlas/tests/test_publish_release.py
def test_iv_snapshots_in_row_count_tables():
    import scripts.publish_release as pr
    assert "iv_snapshots" in pr.ROW_COUNT_TABLES
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_makefile.py::test_ingest_target_runs_iv_snapshot tests/test_publish_release.py::test_iv_snapshots_in_row_count_tables -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

Update `atlas/Makefile` `ingest:` target to append `&& python -m ingest.iv_snapshot`:

```make
ingest:
	python -m ingest.prices && python -m ingest.macro && python -m ingest.vol && python -m ingest.iv_snapshot && python -m ingest.graph && python -m ingest.fundamentals
```

In `atlas/scripts/publish_release.py`:
- Add `"iv_snapshots"` to `ROW_COUNT_TABLES`.
- Upload the panel parquet alongside the db, and download-then-restore it next run. Add near the top of `main()`, before building the release, resolve the panel path and include it as an asset:

```python
from config import DATA_RAW  # add to imports

    panel = Path(DATA_RAW) / "iv_snapshots" / "panel.parquet"
    assets = [str(db), "manifest.json"]
    if panel.exists():
        assets.append(str(panel))
```

Then change the `gh release create` call to pass `*assets` instead of the hard-coded `str(db), "manifest.json"`:

```python
    subprocess.run(
        ["gh", "release", "create", tag, *assets,
         "--draft", "--title", tag, "--notes", "automated data release"],
        check=True,
    )
```

> **Cross-run accumulation note (no code change required here, documented for the operator):** because `make ingest` runs before `publish_release.py`, and `ingest.iv_snapshot._load_prior_panel` reads the local `panel.parquet`, full accumulation in CI requires restoring the previous release's panel into `data/raw/iv_snapshots/` *before* `make all`. Add this one line to the `refresh` job in `.github/workflows/update-data.yml` immediately after `uv pip install` (kept out of this plan's automated tests; apply manually and verify in the first scheduled run):
>
> ```yaml
>       - name: Restore prior IV panel (best-effort)
>         run: |
>           mkdir -p data/raw/iv_snapshots
>           TAG=$(gh release list --json tagName,createdAt \
>             --jq 'map(select(.tagName|startswith("data-")))|sort_by(.createdAt)|last|.tagName' || true)
>           if [ -n "$TAG" ]; then gh release download "$TAG" --pattern panel.parquet \
>             --dir data/raw/iv_snapshots || echo "no prior panel yet"; fi
> ```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_makefile.py tests/test_publish_release.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add Makefile scripts/publish_release.py tests/test_makefile.py tests/test_publish_release.py
git commit -m "feat: persist + accumulate IV snapshot panel across releases"
```

---

## Final verification (run before declaring done)

- [ ] **Full test suite + coverage**

Run: `uv run pytest --cov --cov-report=term-missing`
Expected: all green; new analysis modules (`vol_premium.py`, `vol_termstructure.py`, pure parts of `iv_snapshot.py`) at 80%+ (network/`run()`/`fetch_*` lines are `# pragma: no cover`).

- [ ] **Lint**

Run: `uv run ruff check .`
Expected: no NEW issues (the 2 pre-existing issues in `analysis/fundamentals_leadlag.py` are out of scope).

- [ ] **End-to-end data build (if online)**

Run: `uv run make all && uv run python web/export_data.py --db data/atlas.duckdb --out web/static/data`
Expected: `web/static/data/signals.json` contains H6 and H7 records (in addition to H0/H1/H2/H5). Validate they parse against `SignalZ`: `cd web && npm run build` succeeds.

- [ ] **Report verdicts honestly**

Read the H6 and H7 verdicts/numbers out of `signals.json` and report them EXACTLY as produced — no threshold changes. Do NOT push; hand back to the user for the Phase 3 review of the verdict numbers (esp. the contradicts/null boundary and any clustering).

---

## Spec coverage self-check (done while writing this plan)

- Index/sector vol ingest (VIX complex + VXN, FRED fallback) → Tasks 1, 2, 4.
- QQQ matched underlying → Task 3.
- H6 VRP (implied² − realized², block-bootstrap CI) + IV info content (OOS R²) → Tasks 5–8.
- H7 term-structure slope → {SPY,SOXX,IGV}×{21,42,63}, selection-aware p, BH-FDR, walk-forward sign-rate → Tasks 9–12.
- Verdict reuse of `FDR_ALPHA`/`OOS_SIGN_FLOOR`/single-series null/`bh_fdr` → Tasks 8, 11, 12.
- Orchestration into `run()` + `build_signal_records` + DuckDB tables → Tasks 8, 12, 13.
- Web chart types `vrp_term` / `termstructure_timing` → Task 15.
- Collector B (snapshot features, idempotent panel, accumulation across releases, dbt models, silent — no card) → Tasks 16–20.
- Honest semis-implied-unavailable caveat → H6 record caveats (Task 8).
- No new thresholds; verdicts reported as produced → Final verification.
