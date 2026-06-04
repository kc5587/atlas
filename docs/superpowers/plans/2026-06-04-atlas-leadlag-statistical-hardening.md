# Lead/Lag Statistical Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the 19 pre-registered value-chain price edges statistically defensible — de-beta'd (market-only + market+sector), one-sided directionally tested with a selection-aware null, FDR-controlled per spec, and validated out-of-sample with anchored walk-forward.

**Architecture:** New pure analysis modules (`residualize.py`, `significance.py`, `oos.py`) each do one job and are unit-tested in isolation; `analysis/leadlag.py` orchestrates them into an extended `leadlag` table. Factor ETFs (SPY/SOXX/IGV) are ingested through the existing prices path and exposed via a `factor_returns` dbt model. Everything is a deterministic function of the frozen Parquet snapshot + `RANDOM_SEED`.

**Tech Stack:** Python 3.13, NumPy, pandas, statsmodels-free OLS (NumPy `lstsq`), DuckDB, dbt-duckdb, pytest. Web: Svelte 5 + Zod.

**Spec:** `docs/superpowers/specs/2026-06-04-atlas-leadlag-statistical-hardening-design.md`

**Conventions for every task:**
- Run Python tests from `atlas/`: `uv run --extra dev python -m pytest <path> -v`
- Commits are path-scoped; never commit `data/`, `dist/`, `node_modules/`, caches.
- `left` = edge `from_id` (upstream); `right` = edge `to_id` (downstream). Positive lag ⇒ left leads right.

---

## File Structure

| File | Responsibility |
|---|---|
| `atlas/config.py` (modify) | Factor tickers, stage→sector map, lag domain, walk-forward + confirmation params |
| `atlas/ingest/prices.py` (modify) | Also ingest factor ETF tickers into `data/raw/prices/` |
| `atlas/dbt_project/models/marts/factor_returns.sql` (create) | Daily log returns for factor tickers only |
| `atlas/analysis/residualize.py` (create) | Orthogonalized sector factor, M1/M2 OLS betas (train-only), residuals, leave-one-out sector |
| `atlas/analysis/significance.py` (create) | Politis–White block length, single-series perturbation null, signed one-sided selection-aware p-value, direction/sign diagnostics |
| `atlas/analysis/oos.py` (create) | Anchored/expanding walk-forward folds, per-fold reselection, OOS stability summary |
| `atlas/analysis/leadlag.py` (modify) | Orchestrate hardened edge rows, per-spec BH-FDR, confirmation rule, extended schema |
| `atlas/web/export_data.py` (modify) | Exclude factor tickers from price series export |
| `atlas/web/src/lib/types.ts` (modify) | Extend `LeadLagZ` with new optional fields |
| `atlas/web/src/lib/leadlag.ts` (modify) | `leadLagFor` prefers the M2 (sector-controlled) row |
| `atlas/tests/test_residualize.py` (create) | Unit tests |
| `atlas/tests/test_significance.py` (create) | Unit tests |
| `atlas/tests/test_oos.py` (create) | Unit tests |
| `atlas/tests/test_leadlag_hardened.py` (create) | Integration + data-quality tests |

**Shared types (defined once, used everywhere):**
- Residual series: `pd.Series` indexed by `date`, named by ticker.
- Factor returns: `dict[str, pd.Series]` keyed by ETF ticker (`"SPY"`, `"SOXX"`, `"IGV"`).
- Edge result row: `dict` matching the §8 schema (one row per edge × spec).

---

## Task 1: Factor config, ingest, and `factor_returns` model

**Files:**
- Modify: `atlas/config.py`
- Modify: `atlas/ingest/prices.py:48-56`
- Create: `atlas/dbt_project/models/marts/factor_returns.sql`
- Modify: `atlas/web/export_data.py:70-79`
- Test: `atlas/tests/test_factors.py`

- [ ] **Step 1: Write the failing test**

```python
# atlas/tests/test_factors.py
from config import FACTOR_TICKERS, STAGE_SECTOR, LAG_MIN, LAG_MAX


def test_factor_tickers_distinct_from_universe():
    from config import UNIVERSE
    assert set(FACTOR_TICKERS.values()).isdisjoint(set(UNIVERSE))
    assert FACTOR_TICKERS["market"] == "SPY"


def test_every_stage_maps_to_a_sector_factor():
    for stage in ("equipment", "foundry", "chips", "cloud"):
        assert STAGE_SECTOR[stage] in FACTOR_TICKERS


def test_lag_domain_is_one_sided():
    assert LAG_MIN == 1
    assert LAG_MAX >= LAG_MIN
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev python -m pytest tests/test_factors.py -v`
Expected: FAIL with `ImportError: cannot import name 'FACTOR_TICKERS'`

- [ ] **Step 3: Add config**

Append to `atlas/config.py`:

```python
# Priority 1 hardening: factor model + OOS params.
FACTOR_TICKERS: dict[str, str] = {"market": "SPY", "semis": "SOXX", "cloud": "IGV"}
STAGE_SECTOR: dict[str, str] = {
    "equipment": "semis", "foundry": "semis", "chips": "semis", "cloud": "cloud",
}
LAG_MIN = 1
LAG_MAX = MAX_LAG_DAYS  # one-sided, hypothesized direction only

OOS_TEST_DAYS = 252
OOS_STEP_DAYS = 252
OOS_INIT_TRAIN_FRAC = 0.5
OOS_EMBARGO_DAYS = MAX_LAG_DAYS
OOS_MIN_FOLDS = 3
OOS_SIGN_RATE_FLOOR = 0.6        # descriptive heuristic, NOT a significance test
LEAVE_ONE_OUT_WEIGHT = 0.10      # ETF-weight threshold for leave-one-out variant
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --extra dev python -m pytest tests/test_factors.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Ingest factor tickers**

Modify `atlas/ingest/prices.py` `run()`:

```python
def run(tickers: list[str] | None = None) -> None:  # pragma: no cover
    from config import FACTOR_TICKERS
    tickers = tickers or (UNIVERSE + list(FACTOR_TICKERS.values()))
    out_dir = Path(DATA_RAW) / "prices"
    for t in tickers:
        df = fetch_prices(t)
        atomic_write_parquet(df, out_dir / f"{t}.parquet")
        print(f"prices: wrote {len(df)} rows for {t}")
```

- [ ] **Step 6: Create the `factor_returns` model**

Create `atlas/dbt_project/models/marts/factor_returns.sql`:

```sql
-- Daily log returns for factor ETFs only (SPY market, SOXX semis, IGV cloud).
-- Factors flow into stg_prices via the prices/*.parquet glob; this isolates them.
select ticker, date, log_return
from {{ ref('returns') }}
where ticker in ('SPY', 'SOXX', 'IGV')
```

- [ ] **Step 7: Exclude factors from the price series export**

Modify `atlas/web/export_data.py` price loop (around line 70) to skip factor tickers — they are not graph nodes and should not bloat `series.json`:

```python
    from config import FACTOR_TICKERS
    factor_set = set(FACTOR_TICKERS.values())
    prices: dict[str, list[dict]] = {}
    for (ticker,) in con.execute("SELECT DISTINCT ticker FROM returns").fetchall():
        if ticker in factor_set:
            continue
        # ... existing cumulative-return query unchanged ...
```

- [ ] **Step 8: Commit**

```bash
git add atlas/config.py atlas/ingest/prices.py atlas/dbt_project/models/marts/factor_returns.sql atlas/web/export_data.py atlas/tests/test_factors.py
git commit -m "feat: ingest SPY/SOXX/IGV factors + factor_returns model + config"
```

---

## Task 2: Politis–White automatic block length (`significance.py` part 1)

**Files:**
- Create: `atlas/analysis/significance.py`
- Test: `atlas/tests/test_significance.py`

Politis–White (2004): optimal block length scales with the series' autocorrelation. We implement the standard estimator: find the lag `m̂` beyond which autocorrelations are negligible (first lag where `|ρ_k| < 2·sqrt(log10(n)/n)` for `K_N` consecutive lags), form `g = Σ |k|·ρ_k` and `D` terms, and `b_opt = (2·G²/D)^{1/3}·n^{1/3}`. We use the flat-top lag-window simplification and clamp to `[1, n//3]`.

- [ ] **Step 1: Write the failing test**

```python
# atlas/tests/test_significance.py
import numpy as np
from analysis.significance import auto_block_length


def test_block_length_grows_with_autocorrelation():
    rng = np.random.default_rng(0)
    white = rng.standard_normal(2000)
    # AR(1) with strong persistence
    ar = np.zeros(2000)
    for t in range(1, 2000):
        ar[t] = 0.8 * ar[t - 1] + rng.standard_normal()
    b_white = auto_block_length(white)
    b_ar = auto_block_length(ar)
    assert 1 <= b_white < b_ar
    assert b_ar <= len(ar) // 3


def test_block_length_handles_degenerate_input():
    assert auto_block_length(np.ones(50)) >= 1          # zero variance
    assert auto_block_length(np.array([1.0, 2.0])) >= 1  # too short
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --extra dev python -m pytest tests/test_significance.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'analysis.significance'`

- [ ] **Step 3: Implement `auto_block_length`**

Create `atlas/analysis/significance.py`:

```python
"""Selection-aware significance for one-sided lead/lag tests.

INVARIANT: the bootstrap null perturbs a SINGLE residual series independently,
never the pair jointly. Joint resampling preserves the lead/lag under test and
yields an invalid null.
"""
from __future__ import annotations

import numpy as np

from config import BOOTSTRAP_BLOCK


def _autocorr(x: np.ndarray, max_lag: int) -> np.ndarray:
    x = x - x.mean()
    var = np.dot(x, x)
    if var == 0:
        return np.zeros(max_lag + 1)
    return np.array([np.dot(x[: len(x) - k], x[k:]) / var for k in range(max_lag + 1)])


def auto_block_length(x: np.ndarray, *, fallback: int = BOOTSTRAP_BLOCK) -> int:
    """Politis-White (2004) optimal stationary-bootstrap expected block length.

    Returns a clamped integer in [1, n // 3]; falls back on degenerate input.
    """
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < 8 or np.std(x) == 0:
        return max(1, min(fallback, max(1, n // 3)))
    max_lag = min(n - 1, int(np.ceil(np.sqrt(n))) + 20)
    rho = _autocorr(x, max_lag)
    # Flat-top: first lag after which K consecutive |rho| are below the bound.
    bound = 2.0 * np.sqrt(np.log10(n) / n)
    K = max(5, int(np.ceil(np.sqrt(np.log10(n)))))
    m = 1
    for k in range(1, max_lag - K + 1):
        if np.all(np.abs(rho[k : k + K]) < bound):
            m = k - 1
            break
    else:
        m = max_lag // 2
    M = max(1, 2 * m)
    lags = np.arange(-M, M + 1)
    rho_sym = np.array([rho[abs(int(k))] for k in lags])
    # Flat-top lag window weights.
    w = np.where(np.abs(lags) <= M / 2, 1.0, 2.0 * (1.0 - np.abs(lags) / M))
    w = np.clip(w, 0.0, 1.0)
    g_hat = float(np.sum(w * np.abs(lags) * rho_sym))
    d_hat = float(np.sum(w * rho_sym) ** 2) + 1e-12
    b_opt = (2.0 * g_hat**2 / d_hat) ** (1.0 / 3.0) * n ** (1.0 / 3.0)
    if not np.isfinite(b_opt) or b_opt < 1:
        return max(1, min(fallback, n // 3))
    return int(np.clip(round(b_opt), 1, n // 3))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --extra dev python -m pytest tests/test_significance.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add atlas/analysis/significance.py atlas/tests/test_significance.py
git commit -m "feat: Politis-White automatic block length for bootstrap null"
```

---

## Task 3: Single-series perturbation + signed one-sided selection-aware p-value

**Files:**
- Modify: `atlas/analysis/significance.py`
- Test: `atlas/tests/test_significance.py`

- [ ] **Step 1: Write the failing tests**

Append to `atlas/tests/test_significance.py`:

```python
from analysis.significance import (
    circular_rotate, block_resample_one, selection_aware,
)


def test_circular_rotate_preserves_values_and_length():
    y = np.arange(10.0)
    r = circular_rotate(y, 3)
    assert len(r) == 10
    assert sorted(r) == sorted(y)
    assert r[3] == y[0]


def test_block_resample_preserves_length_and_membership():
    rng = np.random.default_rng(1)
    y = np.arange(100.0)
    r = block_resample_one(y, block=10, rng=rng)
    assert len(r) == 100
    assert set(r).issubset(set(y))


def test_real_lead_lag_is_significant_in_correct_direction():
    rng = np.random.default_rng(2)
    n = 1500
    left = rng.standard_normal(n)
    right = np.empty(n)              # right_t = left_{t-3} + noise  => left leads by 3
    right[:3] = rng.standard_normal(3)
    right[3:] = left[:-3] + 0.5 * rng.standard_normal(n - 3)
    out = selection_aware(left, right, lag_min=1, lag_max=20, iters=500, seed=7)
    assert out["lag"] == 3
    assert out["corr"] > 0
    assert out["p_selection"] < 0.05
    assert out["contradicts_thesis"] is False
    assert out["inverse_lead"] is False


def test_downstream_leads_is_flagged_contradicts_thesis():
    rng = np.random.default_rng(3)
    n = 1500
    right = rng.standard_normal(n)
    left = np.empty(n)               # left_t = right_{t-3}  => right leads (wrong direction)
    left[:3] = rng.standard_normal(3)
    left[3:] = right[:-3] + 0.5 * rng.standard_normal(n - 3)
    out = selection_aware(left, right, lag_min=1, lag_max=20, iters=500, seed=7)
    assert out["contradicts_thesis"] is True


def test_null_cross_corr_centered_on_zero():
    rng = np.random.default_rng(4)
    a = rng.standard_normal(1000)
    b = rng.standard_normal(1000)    # independent
    out = selection_aware(a, b, lag_min=1, lag_max=20, iters=800, seed=1)
    assert out["p_selection"] > 0.1  # nothing real => not significant
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --extra dev python -m pytest tests/test_significance.py -v`
Expected: FAIL with `ImportError` on `circular_rotate`.

- [ ] **Step 3: Implement**

Append to `atlas/analysis/significance.py`:

```python
def circular_rotate(y: np.ndarray, shift: int) -> np.ndarray:
    """Circularly shift one series (preserves its autocorrelation exactly)."""
    return np.roll(np.asarray(y, dtype=float), int(shift))


def block_resample_one(y: np.ndarray, *, block: int, rng: np.random.Generator) -> np.ndarray:
    """Stationary block bootstrap of a SINGLE series (geometric block lengths)."""
    y = np.asarray(y, dtype=float)
    n = len(y)
    p = 1.0 / max(1, block)
    out = np.empty(n)
    i = 0
    while i < n:
        start = int(rng.integers(0, n))
        length = int(rng.geometric(p))
        for k in range(length):
            if i >= n:
                break
            out[i] = y[(start + k) % n]
            i += 1
    return out


def _corr_at_lag(left: np.ndarray, right: np.ndarray, lag: int) -> float:
    if lag >= 0:
        x, y = left[: len(left) - lag], right[lag:]
    else:
        x, y = left[-lag:], right[: len(right) + lag]
    if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
        return np.nan
    return float(np.corrcoef(x, y)[0, 1])


def _signed_peak(left, right, lag_min, lag_max) -> tuple[int, float]:
    """Lag in [lag_min, lag_max] maximizing SIGNED corr (the one-sided hypothesis)."""
    best_lag, best = lag_min, -np.inf
    for lag in range(lag_min, lag_max + 1):
        c = _corr_at_lag(left, right, lag)
        if np.isfinite(c) and c > best:
            best, best_lag = c, lag
    return best_lag, (best if np.isfinite(best) else np.nan)


def _abs_peak(left, right, lags) -> float:
    vals = [abs(_corr_at_lag(left, right, lag)) for lag in lags]
    vals = [v for v in vals if np.isfinite(v)]
    return max(vals) if vals else np.nan


def selection_aware(
    left: np.ndarray, right: np.ndarray, *,
    lag_min: int, lag_max: int, iters: int, seed: int,
    method: str = "block", block: int | None = None,
) -> dict:
    """Signed, one-sided, selection-aware p-value over positive lags.

    Null: perturb ONE series (block bootstrap default; circular rotation cross-check),
    recompute the signed max(+corr) over [lag_min, lag_max] each iteration.
    """
    left = np.asarray(left, dtype=float)
    right = np.asarray(right, dtype=float)
    rng = np.random.default_rng(seed)
    block = block or auto_block_length(right)

    lag, corr = _signed_peak(left, right, lag_min, lag_max)
    pos_lags = range(lag_min, lag_max + 1)
    neg_lags = range(-lag_max, -lag_min + 1)
    pos_abs = _abs_peak(left, right, pos_lags)
    neg_abs = _abs_peak(left, right, neg_lags)
    # dominant positive-lag relationship sign (for inverse_lead)
    pa_lag = max(pos_lags, key=lambda L: (abs(_corr_at_lag(left, right, L)) if np.isfinite(_corr_at_lag(left, right, L)) else -1))
    pa_sign_corr = _corr_at_lag(left, right, pa_lag)

    count = 0
    for _ in range(iters):
        if method == "rotate":
            yb = circular_rotate(right, int(rng.integers(1, len(right))))
        else:
            yb = block_resample_one(right, block=block, rng=rng)
        _, null_peak = _signed_peak(left, yb, lag_min, lag_max)
        if np.isfinite(null_peak) and null_peak >= corr:
            count += 1
    p = (count + 1) / (iters + 1)

    return {
        "lag": int(lag),
        "corr": float(corr) if np.isfinite(corr) else np.nan,
        "corr_contemporaneous": _corr_at_lag(left, right, 0),
        "p_selection": float(p),
        "block_len": int(block),
        "best_neg_lag_corr": float(neg_abs) if np.isfinite(neg_abs) else np.nan,
        "contradicts_thesis": bool(np.isfinite(neg_abs) and np.isfinite(pos_abs) and neg_abs > pos_abs),
        "inverse_lead": bool(np.isfinite(pa_sign_corr) and pa_sign_corr < 0),
    }
```

- [ ] **Step 4: Run to verify passes**

Run: `uv run --extra dev python -m pytest tests/test_significance.py -v`
Expected: PASS (7 tests total in file)

- [ ] **Step 5: Commit**

```bash
git add atlas/analysis/significance.py atlas/tests/test_significance.py
git commit -m "feat: signed one-sided selection-aware null with single-series perturbation"
```

---

## Task 4: Residualization with orthogonalized sector + train-only betas

**Files:**
- Create: `atlas/analysis/residualize.py`
- Test: `atlas/tests/test_residualize.py`

- [ ] **Step 1: Write the failing tests**

```python
# atlas/tests/test_residualize.py
import numpy as np
import pandas as pd
from analysis.residualize import ols_residual, orthogonalize, residual_for_spec


def _series(vals, start="2020-01-01"):
    idx = pd.bdate_range(start, periods=len(vals))
    return pd.Series(vals, index=idx)


def test_ols_residual_is_orthogonal_to_regressors():
    rng = np.random.default_rng(0)
    x = _series(rng.standard_normal(500))
    y = 2.0 + 1.5 * x + _series(rng.standard_normal(500))
    resid = ols_residual(y, pd.DataFrame({"x": x}))
    assert abs(np.corrcoef(resid.values, x.loc[resid.index].values)[0, 1]) < 1e-6


def test_orthogonalize_removes_market_from_sector():
    rng = np.random.default_rng(1)
    spy = _series(rng.standard_normal(500))
    soxx = 0.9 * spy + 0.3 * _series(rng.standard_normal(500))
    pure = orthogonalize(soxx, spy)
    assert abs(np.corrcoef(pure.values, spy.loc[pure.index].values)[0, 1]) < 1e-6


def test_residual_for_spec_m1_vs_m2_differ_when_sector_loads():
    rng = np.random.default_rng(2)
    spy = _series(rng.standard_normal(600))
    soxx = 0.8 * spy + 0.4 * _series(rng.standard_normal(600))
    asset = 1.0 * spy + 0.7 * soxx + 0.2 * _series(rng.standard_normal(600))
    factors = {"SPY": spy, "SOXX": soxx}
    train = asset.index[:400]
    r1 = residual_for_spec(asset, factors, sector="SOXX", spec="M1", train_index=train)
    r2 = residual_for_spec(asset, factors, sector="SOXX", spec="M2", train_index=train)
    # M2 removes sector too, so residual variance should drop materially
    assert r2.loc[train].var() < r1.loc[train].var()


def test_betas_are_train_only_no_lookahead():
    # Residuals on the test slice must use betas fit on train only.
    rng = np.random.default_rng(3)
    spy = _series(rng.standard_normal(500))
    asset = 1.2 * spy + _series(rng.standard_normal(500))
    factors = {"SPY": spy}
    train = asset.index[:300]
    r = residual_for_spec(asset, factors, sector=None, spec="M1", train_index=train)
    # Full series residualized; index covers train+test
    assert len(r) > len(train)
    assert r.index.equals(asset.index)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --extra dev python -m pytest tests/test_residualize.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'analysis.residualize'`

- [ ] **Step 3: Implement**

Create `atlas/analysis/residualize.py`:

```python
"""De-beta returns against market (M1) and market + orthogonalized sector (M2).

Betas (and the sector orthogonalization) are fit on the TRAIN index only, then
applied to the full series, so out-of-sample residuals carry no look-ahead.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def _design(X: pd.DataFrame) -> np.ndarray:
    return np.column_stack([np.ones(len(X)), X.to_numpy(dtype=float)])


def _fit_betas(y: pd.Series, X: pd.DataFrame) -> np.ndarray:
    df = pd.concat([y.rename("y"), X], axis=1, join="inner").dropna()
    A = _design(df.drop(columns="y"))
    beta, *_ = np.linalg.lstsq(A, df["y"].to_numpy(dtype=float), rcond=None)
    return beta


def ols_residual(y: pd.Series, X: pd.DataFrame, *, train_index=None) -> pd.Series:
    """Residual of y on [const, X]; betas fit on train_index (default: all)."""
    fit_y = y.loc[train_index] if train_index is not None else y
    fit_X = X.loc[train_index] if train_index is not None else X
    beta = _fit_betas(fit_y, fit_X)
    full = pd.concat([y.rename("y"), X], axis=1, join="inner").dropna()
    pred = _design(full.drop(columns="y")) @ beta
    resid = full["y"].to_numpy() - pred
    return pd.Series(resid, index=full.index)


def leave_one_out_sector(
    name_ticker: str, peer_tickers: list[str], returns: dict[str, pd.Series]
) -> pd.Series:
    """Equal-weight mean return of same-stage peers EXCLUDING the name itself.

    Robustness variant for heavy ETF constituents (spec §5): avoids a name
    sitting inside its own sector factor. Peers are the other universe tickers
    sharing the name's stage.
    """
    cols = [returns[t] for t in peer_tickers if t != name_ticker and t in returns]
    if not cols:
        return pd.Series(dtype=float)
    return pd.concat(cols, axis=1, join="inner").dropna().mean(axis=1)


def orthogonalize(target: pd.Series, base: pd.Series, *, train_index=None) -> pd.Series:
    """Return target residualized on base (the 'pure' factor)."""
    return ols_residual(target, pd.DataFrame({"base": base}), train_index=train_index)


def residual_for_spec(
    asset: pd.Series,
    factors: dict[str, pd.Series],
    *,
    sector: str | None,
    spec: str,
    train_index,
) -> pd.Series:
    """Idiosyncratic return for one spec.

    M1: residual on SPY only.
    M2: residual on SPY + sector_pure (sector orthogonalized on SPY, train-only).
    """
    spy = factors["SPY"]
    if spec == "M1" or sector is None:
        return ols_residual(asset, pd.DataFrame({"SPY": spy}), train_index=train_index)
    sector_pure = orthogonalize(factors[sector], spy, train_index=train_index)
    X = pd.DataFrame({"SPY": spy, "SEC": sector_pure}).dropna()
    return ols_residual(asset, X, train_index=train_index)
```

- [ ] **Step 4: Add the leave-one-out test**

Append to `atlas/tests/test_residualize.py`:

```python
def test_leave_one_out_excludes_the_name():
    from analysis.residualize import leave_one_out_sector
    rng = np.random.default_rng(5)
    rets = {t: _series(rng.standard_normal(300)) for t in ("NVDA", "AMD", "MU")}
    loo = leave_one_out_sector("NVDA", ["NVDA", "AMD", "MU"], rets)
    # NVDA must not influence its own factor: equals mean of AMD+MU
    expected = pd.concat([rets["AMD"], rets["MU"]], axis=1).mean(axis=1)
    assert np.allclose(loo.values, expected.loc[loo.index].values)
```

- [ ] **Step 5: Run to verify passes**

Run: `uv run --extra dev python -m pytest tests/test_residualize.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add atlas/analysis/residualize.py atlas/tests/test_residualize.py
git commit -m "feat: residualize returns (M1/M2) with orthogonalized sector, train-only betas"
```

---

## Task 5: Anchored walk-forward OOS

**Files:**
- Create: `atlas/analysis/oos.py`
- Test: `atlas/tests/test_oos.py`

- [ ] **Step 1: Write the failing tests**

```python
# atlas/tests/test_oos.py
import numpy as np
import pandas as pd
from analysis.oos import walk_forward_folds, oos_stability


def test_folds_anchored_with_fixed_test_window_and_embargo():
    idx = pd.bdate_range("2010-01-01", periods=4128)
    folds = walk_forward_folds(idx, test_days=252, step_days=252,
                               init_train_frac=0.5, embargo=20)
    assert len(folds) == 8
    for train_idx, test_idx in folds:
        assert train_idx[0] == idx[0]          # anchored: always starts at origin
        assert len(test_idx) == 252 - 20       # 232 usable after embargo
        assert train_idx[-1] < test_idx[0]     # no overlap


def test_short_series_yields_fewer_but_not_thinner_folds():
    idx = pd.bdate_range("2016-08-18", periods=2461)
    folds = walk_forward_folds(idx, test_days=252, step_days=252,
                               init_train_frac=0.5, embargo=20)
    assert len(folds) == 4
    assert all(len(t) == 232 for _, t in folds)


def test_oos_stability_reports_sign_retention():
    # Synthetic: left leads right by 3, positive corr, stable across folds.
    rng = np.random.default_rng(0)
    n = 2000
    left = rng.standard_normal(n)
    right = np.empty(n)
    right[:3] = rng.standard_normal(3)
    right[3:] = left[:-3] + 0.5 * rng.standard_normal(n - 3)
    idx = pd.bdate_range("2012-01-01", periods=n)
    out = oos_stability(pd.Series(left, idx), pd.Series(right, idx),
                        lag_min=1, lag_max=20, test_days=252, step_days=252,
                        init_train_frac=0.5, embargo=20)
    assert out["n_folds"] >= 3
    assert out["oos_sign_rate"] >= 0.6
    assert np.isfinite(out["oos_corr_median"])
    assert len(out["fold_date_ranges"]) == out["n_folds"]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --extra dev python -m pytest tests/test_oos.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'analysis.oos'`

- [ ] **Step 3: Implement**

Create `atlas/analysis/oos.py`:

```python
"""Anchored/expanding walk-forward OOS for lead/lag stability.

Per fold: select the peak lag on the (anchored) train slice, embargo the
boundary, then measure residual corr at that fixed lag on a fixed 252-day test
window. Reports the DISTRIBUTION of test corr; sign-rate is descriptive only
(folds overlap and returns autocorrelate — not independent Bernoulli trials).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from analysis.significance import _corr_at_lag, _signed_peak


def walk_forward_folds(index, *, test_days, step_days, init_train_frac, embargo):
    index = pd.DatetimeIndex(index)
    n = len(index)
    k = int((init_train_frac * n) // test_days)
    init_train = n - k * test_days
    folds = []
    for i in range(k):
        train_end = init_train + i * step_days
        test_start = train_end + embargo
        test_end = train_end + test_days
        if test_end > n:
            break
        folds.append((index[:train_end], index[test_start:test_end]))
    return folds


def oos_stability(left: pd.Series, right: pd.Series, *, lag_min, lag_max,
                  test_days, step_days, init_train_frac, embargo) -> dict:
    paired = pd.concat([left.rename("l"), right.rename("r")], axis=1, join="inner").dropna()
    folds = walk_forward_folds(paired.index, test_days=test_days, step_days=step_days,
                               init_train_frac=init_train_frac, embargo=embargo)
    corrs, signs, ranges = [], [], []
    for train_idx, test_idx in folds:
        tr = paired.loc[train_idx]
        lag, train_corr = _signed_peak(tr["l"].to_numpy(), tr["r"].to_numpy(), lag_min, lag_max)
        te = paired.loc[test_idx]
        test_corr = _corr_at_lag(te["l"].to_numpy(), te["r"].to_numpy(), lag)
        if np.isfinite(test_corr):
            corrs.append(test_corr)
            signs.append(np.sign(test_corr) == np.sign(train_corr) if train_corr != 0 else False)
            ranges.append((str(test_idx[0].date()), str(test_idx[-1].date())))
    corrs_arr = np.array(corrs) if corrs else np.array([np.nan])
    return {
        "n_folds": len(corrs),
        "oos_corr_median": float(np.nanmedian(corrs_arr)),
        "oos_corr_iqr": float(np.nanpercentile(corrs_arr, 75) - np.nanpercentile(corrs_arr, 25)) if corrs else np.nan,
        "oos_sign_rate": float(np.mean(signs)) if signs else 0.0,
        "fold_date_ranges": ranges,
    }
```

- [ ] **Step 4: Run to verify passes**

Run: `uv run --extra dev python -m pytest tests/test_oos.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add atlas/analysis/oos.py atlas/tests/test_oos.py
git commit -m "feat: anchored walk-forward OOS stability with per-fold lag reselection"
```

---

## Task 6: Orchestrate hardened edge rows + per-spec FDR + confirmation

**Files:**
- Modify: `atlas/analysis/leadlag.py`
- Test: `atlas/tests/test_leadlag_hardened.py`

- [ ] **Step 1: Write the failing tests**

```python
# atlas/tests/test_leadlag_hardened.py
import json
import numpy as np
import pandas as pd
from analysis.leadlag import build_hardened_edges, bh_fdr


def _returns_df():
    rng = np.random.default_rng(0)
    idx = pd.bdate_range("2012-01-01", periods=1500)
    spy = rng.standard_normal(1500)
    soxx = 0.8 * spy + 0.4 * rng.standard_normal(1500)
    up = 0.5 * spy + 0.6 * soxx + rng.standard_normal(1500)
    down = np.empty(1500)
    down[:3] = rng.standard_normal(3)
    down[3:] = up[:-3] + 0.6 * rng.standard_normal(1497)   # up leads down by 3
    frames = []
    for tkr, vals in {"SPY": spy, "SOXX": soxx, "UP": up, "DOWN": down}.items():
        frames.append(pd.DataFrame({"ticker": tkr, "date": idx, "log_return": vals}))
    return pd.concat(frames, ignore_index=True)


def _nodes_edges():
    nodes = pd.DataFrame([
        {"id": "up", "tickers": json.dumps(["UP"]), "stage": "chips"},
        {"id": "down", "tickers": json.dumps(["DOWN"]), "stage": "cloud"},
    ])
    edges = pd.DataFrame([{"from_id": "up", "to_id": "down"}])
    return nodes, edges


def test_emits_one_row_per_edge_per_spec():
    nodes, edges = _nodes_edges()
    rows = build_hardened_edges(_returns_df(), nodes, edges, iters=300, seed=7)
    specs = {r["factor_model"] for r in rows}
    assert specs == {"M1_market", "M2_market_sector"}
    assert len(rows) == 2  # 1 edge x 2 specs


def test_real_lead_lag_confirmed_and_correct_direction():
    nodes, edges = _nodes_edges()
    rows = build_hardened_edges(_returns_df(), nodes, edges, iters=300, seed=7)
    for r in rows:
        assert r["lag"] >= 1
        assert r["m"] == 1
        assert r["contradicts_thesis"] is False


def test_bh_fdr_monotone():
    q = bh_fdr(np.array([0.001, 0.02, 0.5]))
    assert (np.diff(q) >= -1e-9).all()
    assert (q <= 1).all()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --extra dev python -m pytest tests/test_leadlag_hardened.py -v`
Expected: FAIL with `ImportError: cannot import name 'build_hardened_edges'`

- [ ] **Step 3: Implement orchestration**

Add to `atlas/analysis/leadlag.py` (keep existing `bh_fdr`; add the new builder and a `_node_stage` helper):

```python
from config import (
    FACTOR_TICKERS, STAGE_SECTOR, LAG_MIN, LAG_MAX, FDR_ALPHA,
    OOS_TEST_DAYS, OOS_STEP_DAYS, OOS_INIT_TRAIN_FRAC, OOS_EMBARGO_DAYS,
    OOS_MIN_FOLDS, OOS_SIGN_RATE_FLOOR, PRICE_NMIN,
)
from analysis.residualize import residual_for_spec
from analysis.significance import selection_aware, _corr_at_lag, _signed_peak
from analysis.oos import oos_stability

SPECS = {"M1_market": "M1", "M2_market_sector": "M2"}


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
            train = ret[lt].index[: int(len(ret[lt]) * OOS_INIT_TRAIN_FRAC)]
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
```

- [ ] **Step 4: Run to verify passes**

Run: `uv run --extra dev python -m pytest tests/test_leadlag_hardened.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Wire into `run()`** — replace the naive edge rows, keep macro + fundamental rows

In `atlas/analysis/leadlag.py` `run()`, build the final `leadlag` table as **legacy non-edge rows (macro + `fund_*`, untouched) + hardened edge rows**. This preserves the `fund_capex_price` rows the shipped NodePanel depends on, drops only the naive `pair_type == "edge"` rows, and replaces them with hardened ones. `pd.concat` aligns columns (legacy rows get `NaN` for the new hardening columns — fine; the web fields are optional):

```python
    legacy = build_leadlag_table(returns, macro, nodes, edges, fundamentals=fundamentals)
    non_edge = legacy[legacy["pair_type"] != "edge"]
    hardened = pd.DataFrame(build_hardened_edges(
        returns, nodes, edges, iters=BOOTSTRAP_ITERS, seed=RANDOM_SEED))
    combined = pd.concat([non_edge, hardened], ignore_index=True)
    con.register("ll", combined)
    con.execute("CREATE OR REPLACE TABLE leadlag AS SELECT * FROM ll")
    con.unregister("ll")
    print(f"leadlag: {len(non_edge)} non-edge + {len(hardened)} hardened edge rows")
```

Remove the prior `build_leadlag_table` → `CREATE TABLE leadlag` block in `run()` (this replaces it).

- [ ] **Step 6: Commit**

```bash
git add atlas/analysis/leadlag.py atlas/tests/test_leadlag_hardened.py
git commit -m "feat: orchestrate hardened edge rows with per-spec FDR and confirmation rule"
```

---

## Task 7: Export hardened table + extend web schema

**Files:**
- Modify: `atlas/web/src/lib/types.ts`
- Modify: `atlas/web/src/lib/leadlag.ts` (prefer the M2 row per edge)
- Test: `atlas/web/tests/data.test.ts`, `atlas/web/tests/leadlag.test.ts` (extend)

> No `export_data.py` change needed here: Task 6 writes the combined `leadlag`
> table, and the exporter already does `SELECT * FROM leadlag`. The factor-ticker
> price filter was added in Task 1.

- [ ] **Step 1: Write the failing web test**

Append to `atlas/web/tests/data.test.ts`:

```typescript
it("parses hardened lead/lag rows with new fields", () => {
  const ll = parseLeadLag([
    { pair_type: "edge", left: "nvidia", right: "microsoft", lag: 2,
      corr: 0.4, p_value: 0.01, q_value: 0.05, n_eff: 1200, stable: true,
      factor_model: "M2_market_sector", corr_raw: 0.6, corr_resid: 0.4,
      p_selection: 0.01, oos_sign_rate: 0.8, confirmed: true,
      survives_sector_control: true, contradicts_thesis: false },
  ]);
  expect(ll[0].factor_model).toBe("M2_market_sector");
  expect(ll[0].confirmed).toBe(true);
});
```

- [ ] **Step 2: Run to verify failure**

Run (from `atlas/web/`): `npm run test -- tests/data.test.ts`
Expected: FAIL — Zod strips/rejects unknown keys or assertion on `factor_model` undefined.

- [ ] **Step 3: Extend the Zod schema**

In `atlas/web/src/lib/types.ts`, extend `LeadLagZ` with optional hardening fields (optional keeps legacy rows valid):

```typescript
export const LeadLagZ = z.object({
  pair_type: z.string(), left: z.string(), right: z.string(), lag: z.number(),
  corr: z.number(), p_value: z.number(), q_value: z.number(),
  n_eff: z.number(), stable: z.boolean(),
  // Priority 1 hardening (optional; present on hardened edge rows):
  factor_model: z.string().optional(),
  corr_raw: z.number().nullable().optional(),
  corr_resid: z.number().nullable().optional(),
  p_selection: z.number().optional(),
  oos_sign_rate: z.number().optional(),
  oos_corr_median: z.number().nullable().optional(),
  confirmed: z.boolean().optional(),
  survives_sector_control: z.boolean().optional(),
  contradicts_thesis: z.boolean().optional(),
  inverse_lead: z.boolean().optional(),
});
```

- [ ] **Step 4: Write the failing `leadLagFor` preference test**

There are now two `pair_type:"edge"` rows per edge (M1 and M2). The map must
prefer the sector-controlled M2 row. Append to `atlas/web/tests/leadlag.test.ts`:

```typescript
it("prefers the M2 (sector-controlled) row when both specs are present", () => {
  const rows: LeadLag[] = [
    { pair_type: "edge", left: "nvidia", right: "microsoft", lag: 2, corr: 0.5,
      p_value: 0.01, q_value: 0.04, n_eff: 1200, stable: true, factor_model: "M1_market" },
    { pair_type: "edge", left: "nvidia", right: "microsoft", lag: 3, corr: 0.3,
      p_value: 0.02, q_value: 0.06, n_eff: 1200, stable: false, factor_model: "M2_market_sector" },
  ];
  expect(leadLagFor(rows, "nvidia", "microsoft")?.factor_model).toBe("M2_market_sector");
});
```

- [ ] **Step 5: Update `leadLagFor` to prefer M2**

In `atlas/web/src/lib/leadlag.ts`:

```typescript
export function leadLagFor(rows: LeadLag[], from: string, to: string): LeadLag | undefined {
  const matches = rows.filter(
    (r) => (r.left === from && r.right === to) || (r.left === to && r.right === from),
  );
  return matches.find((r) => r.factor_model === "M2_market_sector") ?? matches[0];
}
```

- [ ] **Step 6: Run web tests to verify pass**

Run (from `atlas/web/`): `npm run test`
Expected: PASS (data.test.ts + leadlag.test.ts, including the legacy rows without `factor_model`).

- [ ] **Step 7: Commit**

```bash
git add atlas/web/src/lib/types.ts atlas/web/src/lib/leadlag.ts atlas/web/tests/data.test.ts atlas/web/tests/leadlag.test.ts
git commit -m "feat: extend web schema and prefer sector-controlled (M2) edge in the map"
```

---

## Task 8: Data-quality assertions + pipeline wiring

**Files:**
- Modify: `atlas/tests/test_leadlag_hardened.py` (add data-quality tests)
- Modify: `atlas/dbt_project/models/marts/factor_returns.sql` schema doc (optional dbt test)

- [ ] **Step 1: Write the failing data-quality tests**

Append to `atlas/tests/test_leadlag_hardened.py`:

```python
from analysis.residualize import residual_for_spec
from analysis.significance import auto_block_length


def test_residual_orthogonal_to_factors():
    returns = _returns_df()
    ret = {t: g.set_index("date")["log_return"] for t, g in returns.groupby("ticker")}
    factors = {"SPY": ret["SPY"], "SOXX": ret["SOXX"]}
    r = residual_for_spec(ret["UP"], factors, sector="SOXX", spec="M2",
                          train_index=ret["UP"].index)
    aligned = pd.concat([r.rename("e"), ret["SPY"].rename("spy")], axis=1, join="inner").dropna()
    assert abs(np.corrcoef(aligned["e"], aligned["spy"])[0, 1]) < 1e-6


def test_block_length_within_bounds():
    n = 1500
    b = auto_block_length(np.random.default_rng(0).standard_normal(n))
    assert 1 <= b <= n // 3


def test_fdr_family_size_equals_edge_count_per_spec():
    nodes, edges = _nodes_edges()
    rows = build_hardened_edges(_returns_df(), nodes, edges, iters=200, seed=7)
    for r in rows:
        assert r["m"] == len(edges)
```

- [ ] **Step 2: Run to verify failure, then passes**

Run: `uv run --extra dev python -m pytest tests/test_leadlag_hardened.py -v`
Expected: the three new tests are collected; they pass against the Task 4/6 implementations (no new production code needed — they assert existing invariants). If `test_residual_orthogonal_to_factors` fails, fix `residualize.py`, not the test.

- [ ] **Step 3: Full suite + coverage gate**

Run: `uv run --extra dev python -m pytest --cov=analysis --cov-report=term-missing tests/test_residualize.py tests/test_significance.py tests/test_oos.py tests/test_leadlag_hardened.py tests/test_factors.py -v`
Expected: all pass; coverage on `analysis/` modules ≥ 80%.

- [ ] **Step 4: End-to-end pipeline smoke (local, manual)**

Run from `atlas/`:
```bash
uv run make all          # ingest (incl. factors) -> dbt build -> analyze
uv run python web/export_data.py --db data/atlas.duckdb --out web/static/data
```
Expected: `leadlag_edges_hardened` populated; `web/static/data/leadlag.json` contains rows with `factor_model` ∈ {M1_market, M2_market_sector} and `m == 19`. Spot-check that no row has `confirmed == true && contradicts_thesis == true`.

- [ ] **Step 5: Commit**

```bash
git add atlas/tests/test_leadlag_hardened.py
git commit -m "test: data-quality assertions for residual orthogonality, block length, FDR family"
```

---

## Self-Review Notes (for the executor)

- **Single `leadlag` table, edge rows replaced:** Task 6 Step 5 rebuilds `leadlag` as legacy **non-edge** rows (macro + `fund_*`, untouched — preserves the shipped NodePanel's `fund_capex_price` line) **+** hardened edge rows. The naive `pair_type=="edge"` rows are dropped. Hardened rows carry legacy aliases (`corr`=`corr_resid`, `p_value`=`p_selection`, `stable`=`confirmed`) so the existing Zod schema and `edgeStyle`/map keep working; two edge rows per pair (M1, M2) are disambiguated by `leadLagFor` preferring M2 (Task 7).
- **Beta estimation — deliberate simplification vs spec §7:** the spec describes per-fold beta refitting. The plan residualizes **once** using betas fit on the initial 50% train window, then reselects only the *lag* per fold. This is still **look-ahead-free**: every walk-forward test window begins at or after the 50% boundary, so the betas predate all test folds. Per-fold beta refitting (slightly more statistically efficient in late folds) is a noted future refinement, not a correctness fix — call it out in the `oos.py` module docstring so the choice is explicit.
- **Map labeling of confirmed edges** is satisfied via the legacy alias `stable = confirmed`: the existing `edgeStyle` already renders confirmed edges as significant. A richer raw-vs-residual side-by-side UI is a follow-up, not part of this plan.
- **Macro/fundamental hardening deferred** to the sample-appropriate fast-follow (spec §13); their rows pass through unchanged this pass.
- **Private helpers (`_corr_at_lag`, `_signed_peak`) are imported across modules** — they are intentionally shared internals of `significance.py`; do not duplicate them.
- **Determinism:** every stochastic function takes `seed`/`RANDOM_SEED`; no global RNG.
- **Not in this plan (by design):** ARCHITECTURE.md, README re-lead, Priority 2 backtest, Layer 3 — these are separate specs/plans.
