# Atlas Working Paper — P3 (Curve Exports + Figures + Self-Hosted Fonts) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two additive curve exports (lead–lag cross-correlogram, H6 variance-risk-premium time series), render them as two new academic SVG figures wired into the §4 findings, and self-host the two paper fonts — all without changing any hypothesis verdict.

**Architecture:** New analysis primitives (`analysis/correlogram.py`, a `vrp_timeseries` function in `analysis/vol_premium.py`) recompute *curves* from raw tables that the pipeline currently collapses to a single peak/aggregate row. `web/export_data.py` calls them and writes two new schema-versioned JSON files (`correlogram.json`, `vrp.json`). Two new Svelte figures (`CorrelogramFigure`, `VrpFigure`) consume them via tested `paper.ts` transforms and mount in the relevant §4 hypothesis subsections. Fonts move from the Google CDN `<link>` to `@fontsource` npm packages imported in `paper.css`.

**Tech Stack:** Python 3.13 + DuckDB + pandas + numpy (exports); Svelte 5 (runes) + Vite + TypeScript (figures); Vitest (unit) + Playwright (smoke); `@fontsource/eb-garamond` + `@fontsource/ibm-plex-mono`.

---

## Decision note — H2 needs NO new export (verified)

`analysis/signals.py:211` already emits H2 `detail_rows` as
`["horizon", "slope", "slope_lo", "slope_hi", "q_value", ...]` — i.e. the
drift-by-horizon point estimate **with CI and selection-aware q, one row per
horizon (21/42/63 trading days)**. `paper.ts:detailCoefficients` already maps
`slope → effect`, `slope_lo/slope_hi → lo/hi`, `q_value ≤ 0.10 → passes`, so
H2's existing `DetailFigure` already renders the event-study-by-horizon forest.

**Therefore Figure 5 (event-study CAR) requires no backend change.** Task 6
(optional) adds a dedicated connected-line presentation of those *same*
`detail_rows`; it is frontend-only and can be dropped without losing the data.
Only the **correlogram** and **VRP series** are genuinely missing from the
exports (the `leadlag` table stores only the peak lag; `vol_premium` stores only
per-pair aggregates), so those are the two real export tasks.

---

## File structure

| File | Responsibility | Action |
|------|----------------|--------|
| `atlas/analysis/correlogram.py` | Recompute the by-lag cross-correlation curve + block-bootstrap CI band for one headline edge | Create |
| `atlas/analysis/vol_premium.py` | Add `vrp_timeseries()` returning the implied²/realized²/VRP day series for a pair | Modify |
| `atlas/web/export_data.py` | Call both, write `correlogram.json` + `vrp.json`; bump `SCHEMA_VERSION` | Modify |
| `atlas/tests/test_correlogram.py` | Unit-test the correlogram primitive | Create |
| `atlas/tests/test_vol_premium.py` | Add `vrp_timeseries` unit test | Modify |
| `atlas/web/tests/test_export_data.py` | Assert the two new JSON files + shapes | Modify |
| `atlas/web/src/lib/paper.ts` | `correlogramPoints()` + `vrpSeriesPoints()` transforms + interfaces | Modify |
| `atlas/web/tests/paper.test.ts` | Unit-test the two transforms | Modify |
| `atlas/web/src/components/paper/CorrelogramFigure.svelte` | Cross-correlogram SVG (CI band, peak marker, FDR shading) | Create |
| `atlas/web/src/components/paper/VrpFigure.svelte` | Implied² vs realized² series SVG | Create |
| `atlas/web/src/components/paper/EventStudyFigure.svelte` | (Optional) connected CAR line from H2 detail_rows | Create |
| `atlas/web/src/components/Paper.svelte` | Mount the two figures in §4 H1/H6 subsections | Modify |
| `atlas/web/src/lib/paper.css` | `@fontsource` imports replacing CDN | Modify |
| `atlas/web/index.html` | Remove Google Fonts `<link>`/preconnect | Modify |
| `atlas/web/package.json` | Add `@fontsource/*` deps | Modify (via npm) |

**Headline pair for the correlogram:** the confirmed daily edge with the
strongest hardened result. Compute it deterministically (Task 2, Step 3) as the
`pair_type='edge'` row in `leadlag` with `confirmed = true` and maximal
`abs(corr_resid)`; fall back to maximal `abs(corr_resid)` overall if none are
flagged confirmed. Store the chosen `left`/`right` node ids in the JSON so the
caption is data-driven.

---

## Task 1: Self-host the two fonts

**Files:**
- Modify: `atlas/web/package.json` (via npm)
- Modify: `atlas/web/src/lib/paper.css:1-13`
- Modify: `atlas/web/index.html:7-9`

- [ ] **Step 1: Install the fontsource packages**

Run (from `atlas/web`):

```bash
npm install @fontsource/eb-garamond@^5 @fontsource/ibm-plex-mono@^5
```

Expected: both added to `dependencies` in `package.json`; `node_modules/@fontsource/*` present.

- [ ] **Step 2: Import the exact weights at the top of `paper.css`**

Edit `atlas/web/src/lib/paper.css` — add these imports as the very first lines,
before the existing `:root` block (Vite resolves `@fontsource` CSS imports and
bundles the woff2 files):

```css
@import "@fontsource/eb-garamond/400.css";
@import "@fontsource/eb-garamond/500.css";
@import "@fontsource/eb-garamond/600.css";
@import "@fontsource/eb-garamond/400-italic.css";
@import "@fontsource/eb-garamond/500-italic.css";
@import "@fontsource/ibm-plex-mono/400.css";
@import "@fontsource/ibm-plex-mono/500.css";
```

The existing `--serif: "EB Garamond", …` / `--mono: "IBM Plex Mono", …`
custom properties (lines 12–13) already reference these family names — leave them unchanged.

- [ ] **Step 3: Remove the CDN link from `index.html`**

Edit `atlas/web/index.html` — delete the three font lines (the two `preconnect`
links and the `fonts.googleapis.com/css2…` stylesheet link), leaving:

```html
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Atlas — the AI value chain</title>
</head>
```

- [ ] **Step 4: Verify the build bundles fonts and no network font request remains**

Run (from `atlas/web`):

```bash
npm run build && grep -rn "fonts.googleapis" dist/ ; echo "exit:$?"
```

Expected: build succeeds; `grep` prints nothing and `exit:1` (no CDN reference
in output). `dist/assets/` contains `*.woff2` files.

- [ ] **Step 5: Commit**

```bash
git add atlas/web/package.json atlas/web/package-lock.json atlas/web/src/lib/paper.css atlas/web/index.html
git commit -m "feat(paper): self-host EB Garamond + IBM Plex Mono via fontsource"
```

---

## Task 2: Lead–lag cross-correlogram export

**Files:**
- Create: `atlas/analysis/correlogram.py`
- Create: `atlas/tests/test_correlogram.py`
- Modify: `atlas/web/export_data.py`
- Modify: `atlas/web/tests/test_export_data.py`

Reuses existing primitives: `analysis.leadlag.cross_correlations(left, right, max_lag)`
(returns a DataFrame with columns `lag, corr, n`), `analysis.residualize.residual_for_spec`,
and config `MAX_LAG_DAYS=20`, `BOOTSTRAP_ITERS=1000`, `RANDOM_SEED=7`.

- [ ] **Step 1: Write the failing unit test**

Create `atlas/tests/test_correlogram.py`:

```python
import numpy as np
import pandas as pd

from analysis.correlogram import correlogram_curve


def _series(n, seed):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    return pd.Series(rng.standard_normal(n), index=idx)


def test_correlogram_curve_shape_and_peak():
    left = _series(400, 1)
    # right is left shifted forward by 3 days => peak cross-corr near lag +3
    right = left.shift(3).fillna(0.0)
    out = correlogram_curve(left, right, max_lag=20, iters=200, seed=7)

    # one row per lag in [-20, 20]
    assert list(out["lag"]) == list(range(-20, 21))
    # required columns present
    assert {"lag", "corr", "ci_lo", "ci_hi", "is_peak", "passes_fdr"} <= set(out.columns)
    # band brackets the estimate
    assert (out["ci_lo"] <= out["corr"] + 1e-9).all()
    assert (out["ci_hi"] >= out["corr"] - 1e-9).all()
    # exactly one selected peak, at the strongest |corr|
    assert int(out["is_peak"].sum()) == 1
    peak_lag = int(out.loc[out["is_peak"], "lag"].iloc[0])
    assert peak_lag == int(out.loc[out["corr"].abs().idxmax(), "lag"])


def test_correlogram_curve_handles_short_series():
    left = _series(10, 2)
    right = _series(10, 3)
    out = correlogram_curve(left, right, max_lag=20, iters=50, seed=7)
    assert out.empty
```

- [ ] **Step 2: Run it to verify failure**

Run (from `atlas`): `uv run pytest tests/test_correlogram.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'analysis.correlogram'`.

- [ ] **Step 3: Implement `analysis/correlogram.py`**

Create `atlas/analysis/correlogram.py`:

```python
"""By-lag cross-correlogram with a block-bootstrap CI band (additive export only)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from analysis.leadlag import align_pair, cross_correlations
from analysis.significance import auto_block_length

_MIN_OBS = 60


def _stationary_block_indices(n: int, block: int, rng: np.random.Generator) -> np.ndarray:
    """Indices for one stationary-bootstrap resample of length n (wrap-around)."""
    idx = np.empty(n, dtype=int)
    i = 0
    while i < n:
        start = rng.integers(0, n)
        length = rng.geometric(1.0 / block)
        for k in range(length):
            if i >= n:
                break
            idx[i] = (start + k) % n
            i += 1
    return idx


def correlogram_curve(
    left: pd.Series,
    right: pd.Series,
    *,
    max_lag: int,
    iters: int,
    seed: int,
    ci: float = 0.95,
) -> pd.DataFrame:
    """Cross-correlation by lag in [-max_lag, max_lag] with a bootstrap CI band.

    Returns columns: lag, corr, ci_lo, ci_hi, is_peak, passes_fdr.
    Empty frame when fewer than _MIN_OBS aligned observations.
    """
    a, b = align_pair(left, right)
    if len(a) < _MIN_OBS:
        return pd.DataFrame(columns=["lag", "corr", "ci_lo", "ci_hi", "is_peak", "passes_fdr"])

    base = cross_correlations(a, b, max_lag=max_lag).set_index("lag")["corr"]
    lags = list(range(-max_lag, max_lag + 1))
    base = base.reindex(lags)

    av = a.to_numpy()
    bv = b.to_numpy()
    n = len(av)
    block = auto_block_length(av)
    rng = np.random.default_rng(seed)
    draws = np.full((iters, len(lags)), np.nan)
    for it in range(iters):
        sel = _stationary_block_indices(n, block, rng)
        ra = pd.Series(av[sel], index=a.index)
        rb = pd.Series(bv[sel], index=b.index)
        cc = cross_correlations(ra, rb, max_lag=max_lag).set_index("lag")["corr"].reindex(lags)
        draws[it, :] = cc.to_numpy()

    lo_q = (1.0 - ci) / 2.0
    ci_lo = np.nanpercentile(draws, 100 * lo_q, axis=0)
    ci_hi = np.nanpercentile(draws, 100 * (1.0 - lo_q), axis=0)

    corr = base.to_numpy()
    # Two-sided bootstrap p per lag: fraction of resamples at least as extreme as 0-null.
    # Approximate null as the resample distribution recentred on 0.
    centred = draws - np.nanmean(draws, axis=0)
    p = np.array([
        (np.sum(np.abs(centred[:, j]) >= abs(corr[j])) + 1) / (np.sum(~np.isnan(centred[:, j])) + 1)
        for j in range(len(lags))
    ])
    # Benjamini-Hochberg across lags.
    order = np.argsort(p)
    m = len(p)
    q = np.empty(m)
    ranked = p[order] * m / (np.arange(m) + 1)
    q_sorted = np.minimum.accumulate(ranked[::-1])[::-1]
    q[order] = np.clip(q_sorted, 0, 1)

    peak_idx = int(np.nanargmax(np.abs(corr)))
    is_peak = np.zeros(m, dtype=bool)
    is_peak[peak_idx] = True

    return pd.DataFrame({
        "lag": lags,
        "corr": corr,
        "ci_lo": ci_lo,
        "ci_hi": ci_hi,
        "is_peak": is_peak,
        "passes_fdr": q <= 0.10,
    })
```

- [ ] **Step 4: Run the test to verify it passes**

Run (from `atlas`): `uv run pytest tests/test_correlogram.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add atlas/analysis/correlogram.py atlas/tests/test_correlogram.py
git commit -m "feat(analysis): block-bootstrap cross-correlogram curve primitive"
```

- [ ] **Step 6: Write the failing export test**

Edit `atlas/web/tests/test_export_data.py` — add (match the existing test style in that file; it already builds a fixture DuckDB and runs `export_all`):

```python
def test_export_writes_correlogram(tmp_path, fixture_con):
    from export_data import export_all
    out = tmp_path / "data"
    export_all(fixture_con, out)
    cg = json.loads((out / "correlogram.json").read_text())
    assert "pair" in cg and "left" in cg["pair"] and "right" in cg["pair"]
    assert isinstance(cg["points"], list) and len(cg["points"]) >= 1
    row = cg["points"][0]
    assert {"lag", "corr", "ci_lo", "ci_hi", "is_peak", "passes_fdr"} <= set(row)
```

(If `fixture_con` is not already a fixture in this file, reuse the same
connection-construction the existing tests use — read the top of
`test_export_data.py` and follow that pattern exactly; do not invent a new one.)

- [ ] **Step 7: Run it to verify failure**

Run (from `atlas`): `uv run pytest web/tests/test_export_data.py -q -k correlogram`
Expected: FAIL — `FileNotFoundError: …/correlogram.json`.

- [ ] **Step 8: Wire the export into `export_data.py`**

Edit `atlas/web/export_data.py` — bump `SCHEMA_VERSION = "3"`, and inside
`export_all(...)`, after the `leadlag.json` write (around line 94), add:

```python
    from analysis.correlogram import correlogram_curve
    from config import MAX_LAG_DAYS, BOOTSTRAP_ITERS, RANDOM_SEED

    edge_df = con.execute(
        'SELECT "left","right",corr_resid,confirmed FROM leadlag '
        "WHERE pair_type='edge' AND corr_resid IS NOT NULL"
    ).df()
    if len(edge_df):
        ranked = edge_df.assign(_abs=edge_df["corr_resid"].abs())
        confirmed = ranked[ranked["confirmed"] == True]  # noqa: E712
        pool = confirmed if len(confirmed) else ranked
        head = pool.sort_values("_abs", ascending=False).iloc[0]
        left_id, right_id = str(head["left"]), str(head["right"])
        ret = con.execute(
            "SELECT ticker, date, log_return FROM returns ORDER BY ticker, date"
        ).df()
        from analysis.leadlag import _ticker_for_node  # node id -> ticker
        nodes_df = con.execute("SELECT id, tickers FROM graph_nodes").df()
        lt = _ticker_for_node(nodes_df, left_id) or left_id
        rt = _ticker_for_node(nodes_df, right_id) or right_id
        by = {t: g.set_index("date")["log_return"].sort_index()
              for t, g in ret.groupby("ticker")}
        cg_points: list[dict] = []
        if lt in by and rt in by:
            curve = correlogram_curve(
                by[lt], by[rt],
                max_lag=MAX_LAG_DAYS, iters=BOOTSTRAP_ITERS, seed=RANDOM_SEED,
            )
            cg_points = curve.to_dict("records")
        _write_json(out_dir / "correlogram.json", {
            "pair": {"left": left_id, "right": right_id,
                     "left_ticker": lt, "right_ticker": rt},
            "max_lag": MAX_LAG_DAYS,
            "points": cg_points,
        })
```

> Verify `_ticker_for_node` is importable from `analysis/leadlag.py` (it is
> defined there, see `pipeline_runner`). If it is module-private and import
> fails, inline the one-liner: `json.loads(tickers)[0]` from the node row.

- [ ] **Step 9: Run the export test to verify it passes**

Run (from `atlas`): `uv run pytest web/tests/test_export_data.py -q -k correlogram`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add atlas/web/export_data.py atlas/web/tests/test_export_data.py
git commit -m "feat(export): emit correlogram.json for the headline confirmed edge"
```

---

## Task 3: H6 variance-risk-premium time-series export

**Files:**
- Modify: `atlas/analysis/vol_premium.py`
- Modify: `atlas/tests/test_vol_premium.py`
- Modify: `atlas/web/export_data.py`
- Modify: `atlas/web/tests/test_export_data.py`

Reuses `vrp_series()` and the existing `_forward_rv_series(returns, horizon)` in
the same module; config `H6_PAIRS=(("^VIX","SPY"),("^VXN","QQQ"))`, `H6_RV_HORIZON=21`.

- [ ] **Step 1: Write the failing unit test**

Edit `atlas/tests/test_vol_premium.py` — add:

```python
def test_vrp_timeseries_aligned_points():
    import numpy as np, pandas as pd
    from analysis.vol_premium import vrp_timeseries

    idx = pd.date_range("2021-01-01", periods=120, freq="B")
    iv = pd.Series(np.linspace(18, 22, 120), index=idx)        # vol points
    r = pd.Series(np.random.default_rng(7).standard_normal(120) * 0.01, index=idx)

    out = vrp_timeseries(iv, r, horizon=21)
    assert {"date", "implied_var", "realized_var", "vrp"} <= set(out.columns)
    assert len(out) >= 1
    # implied_var = (iv/100)^2 ; vrp = implied_var - realized_var
    row = out.iloc[0]
    assert abs(row["implied_var"] - row["realized_var"] - row["vrp"]) < 1e-9
    assert row["implied_var"] > 0
```

- [ ] **Step 2: Run it to verify failure**

Run (from `atlas`): `uv run pytest tests/test_vol_premium.py -q -k timeseries`
Expected: FAIL — `ImportError: cannot import name 'vrp_timeseries'`.

- [ ] **Step 3: Implement `vrp_timeseries` in `analysis/vol_premium.py`**

Add to `atlas/analysis/vol_premium.py` (below `vrp_series`):

```python
def vrp_timeseries(
    implied_vol_pts: pd.Series,
    underlying_returns: pd.Series,
    *,
    horizon: int,
) -> pd.DataFrame:
    """Per-day implied vs realized variance and their difference (the VRP series).

    implied_var = (IV/100)^2 ; realized_var = annualized RV over the next `horizon`
    days ; vrp = implied_var - realized_var. Rows where realized_var is undefined
    (insufficient forward window) are dropped. Additive only — no verdict impact.
    """
    iv = implied_vol_pts.sort_index().astype(float)
    fwd_rv = _forward_rv_series(underlying_returns.sort_index().astype(float), horizon)
    common = iv.index.intersection(fwd_rv.index)
    iv = iv.loc[common]
    rv = fwd_rv.loc[common]
    implied_var = (iv / 100.0) ** 2
    out = pd.DataFrame({
        "date": common,
        "implied_var": implied_var.to_numpy(),
        "realized_var": rv.to_numpy(),
        "vrp": (implied_var - rv).to_numpy(),
    }).dropna()
    return out.reset_index(drop=True)
```

> If `_forward_rv_series` returns the realized variance indexed at the *start* of
> the forward window (read its body to confirm — it is used at
> `vol_premium_table` line ~153 with `.reindex(iv.index)`), this alignment
> matches the existing aggregate computation, so the series is consistent with
> the published `mean_vrp`.

- [ ] **Step 4: Run the test to verify it passes**

Run (from `atlas`): `uv run pytest tests/test_vol_premium.py -q -k timeseries`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add atlas/analysis/vol_premium.py atlas/tests/test_vol_premium.py
git commit -m "feat(analysis): vrp_timeseries implied vs realized variance series"
```

- [ ] **Step 6: Write the failing export test**

Edit `atlas/web/tests/test_export_data.py` — add:

```python
def test_export_writes_vrp(tmp_path, fixture_con):
    from export_data import export_all
    out = tmp_path / "data"
    export_all(fixture_con, out)
    vrp = json.loads((out / "vrp.json").read_text())
    assert "pair" in vrp and isinstance(vrp["points"], list)
    if vrp["points"]:
        row = vrp["points"][0]
        assert {"date", "implied_var", "realized_var", "vrp"} <= set(row)
```

- [ ] **Step 7: Run it to verify failure**

Run (from `atlas`): `uv run pytest web/tests/test_export_data.py -q -k vrp`
Expected: FAIL — `FileNotFoundError: …/vrp.json`.

- [ ] **Step 8: Wire the VRP export into `export_data.py`**

Edit `atlas/web/export_data.py` — in `export_all(...)`, after the correlogram
block, add (guarded on the `vol_indices` table existing, like other optional tables):

```python
    if _has_table(con, "vol_indices") and _has_table(con, "returns"):
        from analysis.vol_premium import vrp_timeseries
        from config import H6_PAIRS, H6_RV_HORIZON

        vol = con.execute("SELECT series, date, close FROM vol_indices").df()
        rdf = con.execute("SELECT ticker, date, log_return FROM returns").df()
        iv_by = {s: g.set_index("date")["close"].sort_index()
                 for s, g in vol.groupby("series")}
        ret_by = {t: g.set_index("date")["log_return"].sort_index()
                  for t, g in rdf.groupby("ticker")}
        implied, under = H6_PAIRS[0]
        points: list[dict] = []
        if implied in iv_by and under in ret_by:
            ts = vrp_timeseries(iv_by[implied], ret_by[under], horizon=H6_RV_HORIZON)
            ts = _downsample([{"date": str(pd.Timestamp(d).date()),
                               "implied_var": iv, "realized_var": rv, "vrp": v}
                              for d, iv, rv, v in ts.itertuples(index=False)], 400)
            points = ts
        _write_json(out_dir / "vrp.json", {
            "pair": {"implied": implied, "underlying": under},
            "horizon": H6_RV_HORIZON,
            "points": points,
        })
```

> `_downsample(points, max_points)` already exists near the top of
> `export_data.py` (keeps first/last). Import `pandas as pd` is already present.
> If `_downsample` expects a list of `{date, value}` it still works on arbitrary
> dicts (it only slices the list) — confirm by reading its body (it indexes the
> list, not the dict).

- [ ] **Step 9: Run the export test to verify it passes**

Run (from `atlas`): `uv run pytest web/tests/test_export_data.py -q -k vrp`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add atlas/web/export_data.py atlas/web/tests/test_export_data.py
git commit -m "feat(export): emit vrp.json implied vs realized variance series (H6)"
```

---

## Task 4: `paper.ts` transforms for both curves (TDD)

**Files:**
- Modify: `atlas/web/src/lib/paper.ts`
- Modify: `atlas/web/tests/paper.test.ts`

- [ ] **Step 1: Write the failing transform tests**

Edit `atlas/web/tests/paper.test.ts` — add:

```typescript
import { correlogramPoints, vrpSeriesPoints } from "../src/lib/paper";

describe("correlogramPoints", () => {
  it("maps rows and finds the peak lag", () => {
    const raw = {
      pair: { left: "A", right: "B", left_ticker: "AA", right_ticker: "BB" },
      max_lag: 2,
      points: [
        { lag: -1, corr: 0.1, ci_lo: -0.2, ci_hi: 0.3, is_peak: false, passes_fdr: false },
        { lag: 0, corr: 0.5, ci_lo: 0.2, ci_hi: 0.7, is_peak: true, passes_fdr: true },
        { lag: 1, corr: -0.2, ci_lo: -0.4, ci_hi: 0.0, is_peak: false, passes_fdr: false },
      ],
    };
    const out = correlogramPoints(raw);
    expect(out.points).toHaveLength(3);
    expect(out.peakLag).toBe(0);
    expect(out.pairLabel).toBe("AA → BB");
  });
  it("returns null on empty points", () => {
    expect(correlogramPoints({ pair: {}, max_lag: 2, points: [] })).toBeNull();
  });
});

describe("vrpSeriesPoints", () => {
  it("parses dates and keeps the three series", () => {
    const raw = {
      pair: { implied: "^VIX", underlying: "SPY" }, horizon: 21,
      points: [{ date: "2021-01-04", implied_var: 0.04, realized_var: 0.03, vrp: 0.01 }],
    };
    const out = vrpSeriesPoints(raw);
    expect(out!.points[0].impliedVar).toBeCloseTo(0.04);
    expect(out!.label).toContain("^VIX");
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run (from `atlas/web`): `npx vitest run tests/paper.test.ts -t correlogram`
Expected: FAIL — `correlogramPoints is not a function`.

- [ ] **Step 3: Implement the transforms in `paper.ts`**

Add to `atlas/web/src/lib/paper.ts`:

```typescript
export interface CorrelogramPoint {
  lag: number; corr: number; ciLo: number; ciHi: number;
  isPeak: boolean; passesFdr: boolean;
}
export interface Correlogram {
  pairLabel: string; maxLag: number; peakLag: number; points: CorrelogramPoint[];
}

export function correlogramPoints(raw: unknown): Correlogram | null {
  const r = raw as {
    pair?: { left_ticker?: string; right_ticker?: string };
    max_lag?: number;
    points?: Array<Record<string, unknown>>;
  };
  if (!r?.points?.length) return null;
  const points: CorrelogramPoint[] = r.points.map((p) => ({
    lag: Number(p.lag), corr: Number(p.corr),
    ciLo: Number(p.ci_lo), ciHi: Number(p.ci_hi),
    isPeak: Boolean(p.is_peak), passesFdr: Boolean(p.passes_fdr),
  }));
  const peak = points.find((p) => p.isPeak) ?? points.reduce((a, b) =>
    Math.abs(b.corr) > Math.abs(a.corr) ? b : a);
  const lt = r.pair?.left_ticker ?? "", rt = r.pair?.right_ticker ?? "";
  return {
    pairLabel: `${lt} → ${rt}`,
    maxLag: Number(r.max_lag ?? 0),
    peakLag: peak.lag,
    points,
  };
}

export interface VrpPoint { date: Date; impliedVar: number; realizedVar: number; vrp: number; }
export interface VrpSeries { label: string; points: VrpPoint[]; }

export function vrpSeriesPoints(raw: unknown): VrpSeries | null {
  const r = raw as {
    pair?: { implied?: string; underlying?: string };
    points?: Array<Record<string, unknown>>;
  };
  if (!r?.points?.length) return null;
  const points: VrpPoint[] = r.points.map((p) => ({
    date: new Date(String(p.date)),
    impliedVar: Number(p.implied_var),
    realizedVar: Number(p.realized_var),
    vrp: Number(p.vrp),
  }));
  return { label: `${r.pair?.implied ?? ""} vs ${r.pair?.underlying ?? ""}`, points };
}
```

- [ ] **Step 4: Run to verify pass**

Run (from `atlas/web`): `npx vitest run tests/paper.test.ts`
Expected: PASS (all, including the new cases).

- [ ] **Step 5: Commit**

```bash
git add atlas/web/src/lib/paper.ts atlas/web/tests/paper.test.ts
git commit -m "feat(paper): correlogram + vrp series transforms"
```

---

## Task 5: `CorrelogramFigure.svelte` (CI band + peak + FDR shading)

**Files:**
- Create: `atlas/web/src/components/paper/CorrelogramFigure.svelte`

- [ ] **Step 1: Create the figure**

Create `atlas/web/src/components/paper/CorrelogramFigure.svelte` (mirror the SVG
idiom of `VolcanoFigure.svelte`/`DetailFigure.svelte`: viewBox, `var(--mono)`/`var(--serif)`,
`var(--blue)`/`var(--null)`/`var(--rule-2)` tokens, hairline frame):

```svelte
<script lang="ts">
  import type { Correlogram } from "../../lib/paper";
  let { data }: { data: Correlogram } = $props();

  const W = 760, H = 300;
  const m = { t: 16, r: 24, b: 40, l: 48 };
  const PW = W - m.l - m.r, PH = H - m.t - m.b;

  const xs = (lag: number) => m.l + ((lag + data.maxLag) / (2 * data.maxLag)) * PW;
  const yMax = $derived(Math.max(0.1, ...data.points.flatMap((p) => [Math.abs(p.ciHi), Math.abs(p.ciLo), Math.abs(p.corr)])));
  const ys = (c: number) => m.t + PH / 2 - (c / yMax) * (PH / 2);
  const barW = $derived((PW / (2 * data.maxLag + 1)) * 0.6);
</script>

<svg viewBox="0 0 {W} {H}" role="img" aria-label="Lead-lag cross-correlogram">
  <!-- CI band as a shaded ribbon -->
  <path
    d={`M ${data.points.map((p) => `${xs(p.lag)} ${ys(p.ciHi)}`).join(" L ")}
        L ${[...data.points].reverse().map((p) => `${xs(p.lag)} ${ys(p.ciLo)}`).join(" L ")} Z`}
    fill="var(--rule-2)" opacity="0.35" />
  <!-- zero line -->
  <line x1={m.l} y1={ys(0)} x2={m.l + PW} y2={ys(0)} stroke="var(--ink)" />
  <!-- per-lag stems -->
  {#each data.points as p}
    <rect x={xs(p.lag) - barW / 2} y={Math.min(ys(0), ys(p.corr))}
          width={barW} height={Math.abs(ys(p.corr) - ys(0))}
          fill={p.isPeak ? "var(--blue)" : p.passesFdr ? "var(--blue)" : "var(--null)"}
          opacity={p.isPeak ? 1 : p.passesFdr ? 0.7 : 0.4} />
  {/each}
  <!-- peak marker -->
  {#each data.points.filter((p) => p.isPeak) as p}
    <text x={xs(p.lag)} y={ys(p.corr) - 6} text-anchor="middle"
          font-family="var(--mono)" font-size="11" fill="var(--blue)">peak λ={p.lag}</text>
  {/each}
  <text x={m.l + PW / 2} y={H - 8} text-anchor="middle"
        font-family="var(--serif)" font-style="italic" font-size="13" fill="var(--ink-soft)">
    lag (trading days) · {data.pairLabel}
  </text>
</svg>
```

- [ ] **Step 2: Type-check**

Run (from `atlas/web`): `npx svelte-check --threshold error`
Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add atlas/web/src/components/paper/CorrelogramFigure.svelte
git commit -m "feat(paper): cross-correlogram figure (CI band, peak, FDR shading)"
```

---

## Task 6: `VrpFigure.svelte` (implied² vs realized² series)

**Files:**
- Create: `atlas/web/src/components/paper/VrpFigure.svelte`

- [ ] **Step 1: Create the figure**

Create `atlas/web/src/components/paper/VrpFigure.svelte`:

```svelte
<script lang="ts">
  import type { VrpSeries } from "../../lib/paper";
  let { data }: { data: VrpSeries } = $props();

  const W = 760, H = 300;
  const m = { t: 16, r: 24, b: 40, l: 56 };
  const PW = W - m.l - m.r, PH = H - m.t - m.b;

  const t0 = $derived(data.points[0].date.getTime());
  const t1 = $derived(data.points[data.points.length - 1].date.getTime());
  const xs = (d: Date) => m.l + ((d.getTime() - t0) / (t1 - t0 || 1)) * PW;
  const vMax = $derived(Math.max(...data.points.flatMap((p) => [p.impliedVar, p.realizedVar])) || 0.1);
  const ys = (v: number) => m.t + PH - (v / vMax) * PH;
  const path = (key: "impliedVar" | "realizedVar") =>
    data.points.map((p, i) => `${i ? "L" : "M"} ${xs(p.date)} ${ys(p[key])}`).join(" ");
</script>

<svg viewBox="0 0 {W} {H}" role="img" aria-label="Variance risk premium series">
  <line x1={m.l} y1={m.t + PH} x2={m.l + PW} y2={m.t + PH} stroke="var(--ink)" />
  <path d={path("realizedVar")} fill="none" stroke="var(--null)" stroke-width="1.2" />
  <path d={path("impliedVar")} fill="none" stroke="var(--blue)" stroke-width="1.4" />
  <text x={m.l + PW} y={m.t + 4} text-anchor="end"
        font-family="var(--mono)" font-size="11" fill="var(--blue)">implied²</text>
  <text x={m.l + PW} y={m.t + 18} text-anchor="end"
        font-family="var(--mono)" font-size="11" fill="var(--null)">realized²</text>
  <text x={m.l + PW / 2} y={H - 8} text-anchor="middle"
        font-family="var(--serif)" font-style="italic" font-size="13" fill="var(--ink-soft)">
    annualized variance · {data.label}
  </text>
</svg>
```

- [ ] **Step 2: Type-check**

Run (from `atlas/web`): `npx svelte-check --threshold error`
Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add atlas/web/src/components/paper/VrpFigure.svelte
git commit -m "feat(paper): variance-risk-premium series figure (H6)"
```

---

## Task 7: Load the two JSONs and mount the figures in §4

**Files:**
- Modify: `atlas/web/src/components/Paper.svelte`
- Modify whichever component loads data and passes props to `Paper` (the parent
  that already fetches `signals.json`/`graph.json` — find it via
  `grep -rn "loadSignals\|export_data\|signals.json" atlas/web/src` and follow that pattern).

- [ ] **Step 1: Fetch the new files alongside existing data**

In the data-loading parent (the same place `loadSignals` is awaited), add fetches
for `data/correlogram.json` and `data/vrp.json` (tolerate 404 → `null`, since a
stale deploy may predate the export), then pass `correlogram` and `vrp` props
into `<Paper>`. Use the existing fetch/parse idiom in that file; do not add a new
HTTP client.

- [ ] **Step 2: Accept the props and build view models in `Paper.svelte`**

Edit `atlas/web/src/components/Paper.svelte` — extend `$props()` and derive:

```typescript
import CorrelogramFigure from "./paper/CorrelogramFigure.svelte";
import VrpFigure from "./paper/VrpFigure.svelte";
import { correlogramPoints, vrpSeriesPoints } from "../lib/paper";

let { graph, signals, correlogram = null, vrp = null }:
  { graph: Graph; signals: Signal[]; correlogram?: unknown; vrp?: unknown } = $props();

const correlogramVM = $derived(correlogramPoints(correlogram));
const vrpVM = $derived(vrpSeriesPoints(vrp));
```

- [ ] **Step 3: Render inside the matching §4 subsections**

In the §4 findings loop (or after the relevant `<Hypothesis>` blocks), mount the
figures so the correlogram sits in the H1 (capex→revenue propagation) subsection
and the VRP series in the H6 subsection, each wrapped in the existing `<Figure n={…}>`
component with an italic caption. Example for H6:

```svelte
{#if vrpVM}
  <Figure n={6}>
    {#snippet caption()}
      <em>Variance risk premium.</em> Implied variance (blue) sits persistently above
      subsequent realized variance (grey) for {vrpVM.label}: the options market charges
      a positive premium (H6).
    {/snippet}
    <VrpFigure data={vrpVM} />
  </Figure>
{/if}
```

Keep figure numbering consistent with the spec inventory (DAG=1, volcano=2,
forest=3, correlogram=4, event-study=5, VRP=6). Place the correlogram `<Figure n={4}>`
in the H1 subsection.

- [ ] **Step 4: Type-check + unit/smoke**

Run (from `atlas/web`): `npx svelte-check --threshold error && npx vitest run`
Expected: 0 type errors; all vitest green.

- [ ] **Step 5: Commit**

```bash
git add atlas/web/src/components/Paper.svelte <data-loading-parent>
git commit -m "feat(paper): mount correlogram (§4 H1) and VRP series (§4 H6) figures"
```

---

## Task 8 (optional): `EventStudyFigure.svelte` from existing H2 detail_rows

Frontend-only; no export. Renders H2's `detail_rows` (`horizon, slope, slope_lo,
slope_hi, q_value`) as a connected CAR-style line across horizons (21/42/63),
filled markers where `q_value ≤ 0.10`. Reuse `detailCoefficients(signal)` for the
data (label = horizon, effect = slope, lo/hi, passes). Mount as `<Figure n={5}>`
in the H2 subsection. Only build this if time allows — the existing `DetailFigure`
already conveys the same data as a forest.

---

## Verification (MANDATORY — render real data, not just tests)

Real-data bugs hide behind green tests (already burned twice on this project:
volcano dropped a confirmed hypothesis; §4 content leaked into the sidenote rail).

- [ ] **Step 1: Regenerate exports from the real DB**

Run (from `atlas`):

```bash
uv run python web/export_data.py --db data/atlas.duckdb --out web/static/data
```

Expected: prints `export_data: wrote JSON to web/static/data`; `correlogram.json`
and `vrp.json` now exist and are non-empty (`jq '.points | length' web/static/data/correlogram.json`
≥ 1, same for vrp.json).

- [ ] **Step 2: Screenshot the rendered paper with a temp Playwright spec**

Create a throwaway spec in `atlas/web` that visits `/`, scrolls to §4, and
screenshots the H1 and H6 subsections (the webServer auto-builds+previews;
chromium is installed). Confirm visually:
- correlogram shows a CI ribbon, per-lag stems, and a labelled peak λ;
- VRP figure shows implied² above realized²;
- both sit in the **main reading column**, not the sidenote rail;
- fonts still render (EB Garamond / IBM Plex Mono) with the CDN link removed.

Delete the temp spec after capturing. Do **not** commit screenshots.

- [ ] **Step 3: Full CI parity locally**

Run (from `atlas/web`): `npx svelte-check --threshold error && npx vitest run && npx playwright test`
Run (from `atlas`): `uv run pytest -q`
Expected: all green.

- [ ] **Step 4: Final commit / open follow-up PR**

```bash
git add -A && git commit -m "chore(paper): regenerate static data with correlogram + vrp exports"
```

Open a P3 PR (or push to `feat/working-paper` if P1+P2 has not yet merged).

---

## Self-review notes (author)

- **Spec coverage:** correlogram export+figure (Fig 4) ✓; VRP export+figure (Fig 6) ✓;
  H2 event-study (Fig 5) resolved as no-export with optional frontend Task 8 ✓;
  self-host fonts ✓. All four spec §8 / §4 open items covered.
- **Type consistency:** `correlogram_curve` columns (`lag, corr, ci_lo, ci_hi,
  is_peak, passes_fdr`) match the export JSON keys, the export test, the
  `correlogramPoints` parser, and the `Correlogram`/`CorrelogramPoint` interfaces
  consumed by `CorrelogramFigure`. `vrp_timeseries` columns (`date, implied_var,
  realized_var, vrp`) match through `vrpSeriesPoints`/`VrpPoint`/`VrpFigure`.
- **Verification-first:** the mandatory real-data render guards against the two
  classes of bug already seen on this project.
- **No verdict change:** every export reads existing tables and recomputes
  curves; no write to `leadlag`/`vol_premium`/`event_drift`; `signals.json` is untouched.
