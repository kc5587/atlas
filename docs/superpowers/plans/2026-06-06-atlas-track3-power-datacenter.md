# Atlas Track 3 — Power / Datacenter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax. **Phase 2 runs via Codex CLI (gpt-5.4)**: strict TDD (RED→GREEN), per-task path-scoped commits, reuse existing thresholds, report verdicts honestly with NO tuning, do NOT push.

**Goal:** Add two Signal Lab cards — **H9** (electricity cost → cloud gross-margin compression; economic) and **H10** (electricity demand → returns of a new power/datacenter "forgotten plays" layer; market) — from free FRED data, and expand the value-chain map with a guarded `power` stage.

**Architecture:** Add FRED price/demand ids + 6 power tickers to config; ingest power-name prices via yfinance; add a `power` stage to `value_chain.yml` (extending `graph.py`'s `Stage` Literal). Guard the existing H0–H5 scans by filtering to the original four stages in `run()` so shipped verdicts are unchanged. Two pure-function modules (`analysis/power_margins.py`, `analysis/power_demand.py`) compute the tables; `run()` writes `power_margins`/`power_demand`; `signals.py` builds the cards; `SignalCard.svelte` + the map render them.

**Tech Stack:** Python 3.13, pandas, numpy, duckdb, dbt-duckdb, pydantic, yaml, pytest; Svelte. Run via `uv run` from `atlas/`.

> **DEPENDENCY:** This plan reuses **Track 2** helpers — `analysis.leading_indicators.indicator_yoy`, `_quarterly_indicator`, `indicator_revenue_lead`; `analysis.macro_sector.monthly_returns` — and the **Track 1** generic helpers in `analysis.vol_termstructure` (`aligned_forward`, `selection_pvalue_one_series`, `oos_sign_rate`, `_corr_slope`). **Execute Track 2 (plan `2026-06-06-atlas-track2-leading-indicators.md`) first.**

**Non-negotiables:** reuse `FDR_ALPHA=0.10`, `OOS_SIGN_RATE_FLOOR=0.6`, `RANDOM_SEED`, `BOOTSTRAP_ITERS`, the single-series null, `bh_fdr`, `bootstrap_slope_ci`. No new thresholds. Report verdicts as produced.

---

## File Structure

**New files**
- `atlas/analysis/power_margins.py` (H9) + `atlas/tests/test_power_margins.py`
- `atlas/analysis/power_demand.py` (H10) + `atlas/tests/test_power_demand.py`

**Modified files**
- `atlas/config.py`, `atlas/ingest/prices.py`, `atlas/ingest/graph.py`, `atlas/seeds/value_chain.yml`
- `atlas/analysis/leadlag.py` (stage guard + run() wiring), `atlas/analysis/signals.py`
- `atlas/web/export_data.py` (meta stages), `atlas/web/src/components/SignalCard.svelte`, the web stage-order constant
- `atlas/tests/test_graph.py`, `atlas/tests/test_signals.py`, `atlas/tests/test_prices.py`

---

## Phase 0 — Config, ingest, graph

### Task 1: Config constants

**Files:** Modify `atlas/config.py`; Test `atlas/tests/test_power_margins.py`

- [ ] **Step 1: Write the failing test**

```python
# atlas/tests/test_power_margins.py
def test_config_track3_constants():
    import config
    for sid in ("WPU0543", "IPG2211A2N"):
        assert sid in config.FRED_SERIES
    assert config.POWER_NAMES == ["VST", "NRG", "CEG", "ETN", "VRT", "D"]
    assert config.POWER_PRICE_SERIES == ("WPU0543",)
    assert config.POWER_DEMAND_SERIES == ("IPG2211A2N",)
    assert config.H9_LEAD_QUARTERS == (0, 1, 2)
    assert config.H10_HORIZON_MONTHS == (1, 2, 3)
    for sid in config.POWER_PRICE_SERIES + config.POWER_DEMAND_SERIES:
        assert config.INDICATOR_PUB_LAG_MONTHS[sid] >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_power_margins.py::test_config_track3_constants -v`
Expected: FAIL (`ModuleNotFoundError` or `AttributeError: POWER_NAMES`).

- [ ] **Step 3: Write minimal implementation**

In `atlas/config.py`, extend `FRED_SERIES` and append:

```python
FRED_SERIES.update({
    "WPU0543": "PPI: Electric Power",
    "IPG2211A2N": "Industrial Production: Electric Power Generation",
})

# Track 3: power / datacenter "forgotten plays".
POWER_NAMES: list[str] = ["VST", "NRG", "CEG", "ETN", "VRT", "D"]
POWER_PRICE_SERIES: tuple[str, ...] = ("WPU0543",)      # H9 cost predictor
POWER_DEMAND_SERIES: tuple[str, ...] = ("IPG2211A2N",)  # H10 demand predictor
H9_LEAD_QUARTERS: tuple[int, ...] = (0, 1, 2)
H10_HORIZON_MONTHS: tuple[int, ...] = (1, 2, 3)
# cloud names with SEC gross margin (H9 target).
CLOUD_MARGIN_NAMES: list[str] = ["MSFT", "GOOGL", "AMZN", "ORCL"]
INDICATOR_PUB_LAG_MONTHS.update({"WPU0543": 1, "IPG2211A2N": 1})
```

> `INDICATOR_PUB_LAG_MONTHS` is created in Track 2. If running Track 3 standalone, define it as `INDICATOR_PUB_LAG_MONTHS: dict[str, int] = {}` before the `.update(...)`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_power_margins.py::test_config_track3_constants -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add config.py tests/test_power_margins.py
git commit -m "feat: Track 3 config (power names, price/demand series, params)"
```

---

### Task 2: Ingest power-name prices

**Files:** Modify `atlas/ingest/prices.py:run`; Test `atlas/tests/test_prices.py`

- [ ] **Step 1: Write the failing test**

```python
# append to atlas/tests/test_prices.py
import inspect

def test_run_default_ticker_list_includes_power_names():
    import ingest.prices as p
    from config import POWER_NAMES
    assert POWER_NAMES[0] == "VST"
    assert "POWER_NAMES" in inspect.getsource(p.run)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_prices.py::test_run_default_ticker_list_includes_power_names -v`
Expected: FAIL.

- [ ] **Step 3: Write minimal implementation**

In `atlas/ingest/prices.py`, update `run`:

```python
def run(tickers: list[str] | None = None) -> None:  # pragma: no cover
    from config import AUX_TICKERS, FACTOR_TICKERS, POWER_NAMES

    tickers = tickers or (UNIVERSE + list(FACTOR_TICKERS.values()) + AUX_TICKERS + POWER_NAMES)
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
git commit -m "feat: ingest power-layer ticker prices"
```

---

### Task 3: `power` stage in the graph

**Files:** Modify `atlas/ingest/graph.py`, `atlas/seeds/value_chain.yml`; Test `atlas/tests/test_graph.py`

- [ ] **Step 1: Write the failing test**

```python
# append to atlas/tests/test_graph.py
def test_power_stage_nodes_and_edges_load():
    from config import SEED_PATH
    from ingest.graph import load_graph
    nodes, edges = load_graph(SEED_PATH)
    power = nodes[nodes["stage"] == "power"]
    assert set(power["id"]) >= {"vistra", "constellation", "vertiv", "dominion"}
    # at least one cloud -> power edge exists
    cloud_ids = set(nodes[nodes["stage"] == "cloud"]["id"])
    power_ids = set(power["id"])
    assert ((edges["from_id"].isin(cloud_ids)) & (edges["to_id"].isin(power_ids))).any()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_graph.py::test_power_stage_nodes_and_edges_load -v`
Expected: FAIL (pydantic rejects `stage: power`, or nodes missing).

- [ ] **Step 3: Write minimal implementation**

In `atlas/ingest/graph.py`, extend the `Stage` Literal:

```python
Stage = Literal["equipment", "foundry", "chips", "cloud", "power"]
```

Append to `atlas/seeds/value_chain.yml` under `nodes:` (match existing indentation):

```yaml
  # --- power / datacenter (Layer 3) ---
  - id: vistra
    name: Vistra
    tickers: [VST]
    stage: power
    region: US
  - id: nrg
    name: NRG Energy
    tickers: [NRG]
    stage: power
    region: US
  - id: constellation
    name: Constellation Energy
    tickers: [CEG]
    stage: power
    region: US
  - id: eaton
    name: Eaton
    tickers: [ETN]
    stage: power
    region: US
  - id: vertiv
    name: Vertiv
    tickers: [VRT]
    stage: power
    region: US
  - id: dominion
    name: Dominion Energy
    tickers: [D]
    stage: power
    region: US
```

Append under `edges:` (the cloud datacenters pull on the power layer):

```yaml
  - from: microsoft
    to: dominion
    relationship: supplies
    as_of: "2026-06-06"
  - from: amazon
    to: vistra
    relationship: supplies
    as_of: "2026-06-06"
  - from: microsoft
    to: constellation
    relationship: supplies
    as_of: "2026-06-06"
  - from: amazon
    to: vertiv
    relationship: supplies
    as_of: "2026-06-06"
```

> The `relationship` Literal is `"supplies" | "partner"` — reuse `supplies` (power/infra supplies the datacenter). `as_of` is required.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_graph.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ingest/graph.py seeds/value_chain.yml tests/test_graph.py
git commit -m "feat: add power/datacenter (Layer 3) stage to value chain"
```

---

### Task 4: Stage-exclusion guard (protect H0–H5)

**Files:** Modify `atlas/analysis/leadlag.py`; Test `atlas/tests/test_leadlag_hardened.py`

- [ ] **Step 1: Write the failing test**

```python
# append to atlas/tests/test_leadlag_hardened.py
import json
import pandas as pd

def test_exclude_stage_drops_power_nodes_and_their_edges():
    from analysis.leadlag import exclude_stage
    nodes = pd.DataFrame([
        {"id": "nvidia", "stage": "chips", "tickers": json.dumps(["NVDA"])},
        {"id": "microsoft", "stage": "cloud", "tickers": json.dumps(["MSFT"])},
        {"id": "vistra", "stage": "power", "tickers": json.dumps(["VST"])},
    ])
    edges = pd.DataFrame([
        {"from_id": "nvidia", "to_id": "microsoft"},
        {"from_id": "microsoft", "to_id": "vistra"},  # cloud -> power, must be dropped
    ])
    cn, ce = exclude_stage(nodes, edges, "power")
    assert set(cn["id"]) == {"nvidia", "microsoft"}
    assert len(ce) == 1
    assert ce.iloc[0]["to_id"] == "microsoft"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_leadlag_hardened.py::test_exclude_stage_drops_power_nodes_and_their_edges -v`
Expected: FAIL (`AttributeError: exclude_stage`).

- [ ] **Step 3: Write minimal implementation**

Add to `atlas/analysis/leadlag.py` (module level):

```python
def exclude_stage(nodes, edges, stage: str):
    """Return (core_nodes, core_edges) with `stage` nodes and any edge touching them
    removed — so the H0-H5 scans never see the map-only power layer."""
    core_nodes = nodes[nodes["stage"] != stage]
    keep = set(core_nodes["id"])
    core_edges = edges[edges["from_id"].isin(keep) & edges["to_id"].isin(keep)]
    return core_nodes.reset_index(drop=True), core_edges.reset_index(drop=True)
```

In `run()`, immediately after `nodes`/`edges` are loaded and before any scan that uses them, add:

```python
    core_nodes, core_edges = exclude_stage(nodes, edges, "power")
```

Then replace `nodes`/`edges` with `core_nodes`/`core_edges` in the calls to
`build_leadlag_table(...)`, `build_hardened_edges(...)`, `capex_revenue_edges(...)`,
`capex_price_edges(...)`, and `event_drift(...)`. **Leave the full `nodes`/`edges`
flowing to `graph_nodes`/`graph_edges`** (the map needs the power layer) — only the
analysis scans use the core-filtered frames.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_leadlag_hardened.py -v`
Expected: PASS (and existing leadlag tests still green).

- [ ] **Step 5: Commit**

```bash
git add analysis/leadlag.py tests/test_leadlag_hardened.py
git commit -m "feat: exclude power stage from H0-H5 scans (guard shipped verdicts)"
```

---

## Phase 1 — H9: electricity cost → cloud margins

### Task 5: Sector gross-margin delta aggregate

**Files:** Create `atlas/analysis/power_margins.py`; Test `atlas/tests/test_power_margins.py`

- [ ] **Step 1: Write the failing test**

```python
# append to atlas/tests/test_power_margins.py
import numpy as np
import pandas as pd

def test_sector_margin_delta_median():
    from analysis.power_margins import sector_margin_delta
    rows = []
    for tkr in ["MSFT", "ORCL"]:
        for i, q in enumerate(pd.period_range("2015Q1", periods=12, freq="Q")):
            rows.append({"ticker": tkr, "period_end": q.to_timestamp(how="end"),
                         "gross_margin": 0.60 - 0.005 * i})  # margin declining 0.5pp/q
    fund = pd.DataFrame(rows)
    d = sector_margin_delta(fund, names=["MSFT", "ORCL"])
    assert isinstance(d.index, pd.PeriodIndex)
    assert abs(d.dropna().iloc[0] - (-0.005)) < 1e-9
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_power_margins.py::test_sector_margin_delta_median -v`
Expected: FAIL (`ModuleNotFoundError: analysis.power_margins`).

- [ ] **Step 3: Write minimal implementation**

```python
# atlas/analysis/power_margins.py
"""H9: does electricity cost compress cloud gross margins? (pure functions)

Target = cross-sectional MEDIAN quarter-over-quarter change in gross margin (stationary).
Predictor = electricity price YoY (PIT-lagged), NEGATED so the existing positive-slope
machinery detects compression (slope>0 on -price == margin falls as price rises). Small
quarterly sample => effect sizes + bootstrap CI + selection-aware p + BH-FDR, NO
walk-forward (mirrors H1/H8). Reuses Track 2 helpers."""
from __future__ import annotations

import numpy as np
import pandas as pd

from analysis.leading_indicators import _quarterly_indicator, indicator_revenue_lead


def sector_margin_delta(fundamentals: pd.DataFrame, *, names: list[str]) -> pd.Series:
    """Cross-sectional MEDIAN quarter-over-quarter Δ gross margin across `names`,
    indexed by calendar quarter (PeriodIndex 'Q')."""
    per_name = {}
    for t in names:
        sub = fundamentals.loc[fundamentals["ticker"] == t,
                               ["period_end", "gross_margin"]].dropna()
        if sub.empty:
            continue
        q = pd.to_datetime(sub["period_end"]).dt.to_period("Q")
        lvl = pd.Series(sub["gross_margin"].to_numpy(float), index=q).sort_index()
        lvl = lvl[~lvl.index.duplicated(keep="last")]
        d = lvl.diff().dropna()
        if not d.empty:
            per_name[t] = d
    if not per_name:
        return pd.Series(dtype=float)
    return pd.concat(per_name, axis=1).median(axis=1).dropna()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_power_margins.py::test_sector_margin_delta_median -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add analysis/power_margins.py tests/test_power_margins.py
git commit -m "feat: H9 sector gross-margin delta aggregate"
```

---

### Task 6: H9 driver table (negated-predictor, FDR)

**Files:** Modify `atlas/analysis/power_margins.py`; Test `atlas/tests/test_power_margins.py`

- [ ] **Step 1: Write the failing test**

```python
# append to atlas/tests/test_power_margins.py
def _macro_long(series_levels, start="2010-01-01", n=120):
    idx = pd.date_range(start, periods=n, freq="MS")
    return pd.concat([pd.DataFrame({"series_id": s, "date": idx, "value": f(idx)})
                      for s, f in series_levels.items()], ignore_index=True)

def test_power_margins_table_detects_compression():
    from analysis.power_margins import power_margins_table
    rng = np.random.default_rng(0)
    # electricity price rising ~ +8%/yr; build margin Δ that falls when price YoY rises
    macro = _macro_long({"WPU0543": lambda i: np.exp(np.linspace(0, 0.8, len(i)))})
    # construct quarterly margin delta negatively tied to price YoY at lead 1
    rows = []
    for tkr in ["MSFT", "ORCL"]:
        for k, q in enumerate(pd.period_range("2010Q1", periods=40, freq="Q")):
            rows.append({"ticker": tkr, "period_end": q.to_timestamp(how="end"),
                         "gross_margin": 0.60 - 0.001 * k + rng.normal(0, 0.0005)})
    fund = pd.DataFrame(rows)
    out = power_margins_table(macro, fund, price_series=("WPU0543",),
                              names=["MSFT", "ORCL"], leads=(0, 1, 2),
                              pub_lag={"WPU0543": 1}, iters=200, seed=1)
    assert set(out["indicator"]) == {"WPU0543"}
    for col in ("best_lead", "slope", "slope_lo", "slope_hi", "p_selection",
                "q_value", "n_obs", "contradicts_thesis"):
        assert col in out.columns
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_power_margins.py::test_power_margins_table_detects_compression -v`
Expected: FAIL (`AttributeError: power_margins_table`).

- [ ] **Step 3: Write minimal implementation**

Append to `atlas/analysis/power_margins.py`:

```python
def power_margins_table(macro: pd.DataFrame, fundamentals: pd.DataFrame, *,
                        price_series: tuple[str, ...], names: list[str],
                        leads: tuple[int, ...], pub_lag: dict[str, int],
                        iters: int, seed: int) -> pd.DataFrame:
    """One row per electricity-price series: best-lead compression of cloud gross margin.
    Predictor is NEGATED price YoY so slope>0 == margin compression. BH-FDR over eligible."""
    from analysis.leadlag import bh_fdr

    margin = sector_margin_delta(fundamentals, names=names)
    rows = []
    for sid in price_series:
        price_q = _quarterly_indicator(macro, sid, pub_lag.get(sid, 1))
        if price_q.empty or margin.empty:
            rows.append({"indicator": sid, "best_lead": leads[0], "corr": np.nan,
                         "slope": np.nan, "slope_lo": np.nan, "slope_hi": np.nan,
                         "p_selection": 1.0, "n_obs": 0, "contradicts_thesis": False})
            continue
        out = indicator_revenue_lead(-price_q, margin, leads=leads, iters=iters, seed=seed)
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

Run: `uv run pytest tests/test_power_margins.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add analysis/power_margins.py tests/test_power_margins.py
git commit -m "feat: H9 power_margins_table (negated-predictor cost->margin, FDR)"
```

---

### Task 7: `h9_record` + wiring

**Files:** Modify `atlas/analysis/signals.py`; Test `atlas/tests/test_signals.py`

- [ ] **Step 1: Write the failing test**

```python
# append to atlas/tests/test_signals.py
def test_h9_record_confirmed_compression_and_null():
    from analysis.signals import h9_record
    conf = pd.DataFrame([
        {"indicator": "WPU0543", "best_lead": 1, "corr": 0.4, "slope": 0.02,
         "slope_lo": 0.005, "slope_hi": 0.04, "p_selection": 0.002, "q_value": 0.01,
         "n_obs": 45, "contradicts_thesis": False},
    ])
    rec = h9_record(conf)
    assert rec["id"] == "H9" and rec["verdict"] == "confirmed"
    assert rec["chart"]["type"] == "power_margins"

    nul = pd.DataFrame([
        {"indicator": "WPU0543", "best_lead": 0, "corr": 0.05, "slope": 0.001,
         "slope_lo": -0.01, "slope_hi": 0.02, "p_selection": 0.5, "q_value": 0.7,
         "n_obs": 45, "contradicts_thesis": False},
    ])
    assert h9_record(nul)["verdict"] == "null"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_signals.py -k h9 -v`
Expected: FAIL (`ImportError: cannot import name 'h9_record'`).

- [ ] **Step 3: Write minimal implementation**

Add to `atlas/analysis/signals.py` (after `h8_record`), mirroring `h5_record`. The stored
`slope` is on the NEGATED predictor, so slope > 0 = compression:

```python
def h9_record(rows: pd.DataFrame) -> dict:
    """H9: does electricity cost compress cloud gross margins? (slope>0 = compression)."""
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
        "confirmed": "rising power cost compresses cloud margins",
        "suggestive": "weak compression signal",
        "null": "no measurable margin compression (small, hedged input)",
        "contradicts": "power cost moves margins UP (implausible)",
    }[verdict]
    n = int(best.get("n_obs")) if len(elig) else 0
    return {
        "id": "H9", "title": "Does electricity cost compress cloud margins?",
        "horizon": "0-2 quarters",
        "claim": "Rising electricity price compresses cloud gross margins",
        "mechanism": f"Power is a real datacenter opex -- {interp}",
        "verdict": verdict,
        "evidence_chain": [
            {"stage": "best price->margin corr", "metric": "corr", "value": _num(best.get("corr"))},
            {"stage": "compression slope", "metric": "slope", "value": _num(best.get("slope"))},
            {"stage": "selection-aware q", "metric": "q", "value": _num(best.get("q_value"))},
        ],
        "stat": {"name": "compression_slope", "value": _num(best.get("slope")),
                 "ci": [_num(best.get("slope_lo")), _num(best.get("slope_hi"))],
                 "q_value": _num(best.get("q_value")), "n": n},
        "caveats": [
            "Slope is of Δgross-margin on NEGATED price YoY; >0 = compression.",
            "Blended gross margin (not datacenter-segment); power is small & PPA-hedged. No walk-forward.",
        ],
        "chart": {"type": "power_margins", "ref": "h9"},
        "detail_rows": elig[["indicator", "best_lead", "corr", "slope", "slope_lo",
                             "slope_hi", "q_value", "n_obs"]].to_dict("records"),
    }
```

In `build_signal_records`, after the H8 block, add:

```python
    has_h9 = con.execute("SELECT count(*) FROM information_schema.tables "
                         "WHERE table_name='power_margins'").fetchone()[0] > 0
    if has_h9:
        h9 = con.execute('SELECT * FROM power_margins').df()
        if len(h9):
            records.append(h9_record(h9))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_signals.py -k h9 -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add analysis/signals.py tests/test_signals.py
git commit -m "feat: H9 signal record + build_signal_records wiring"
```

---

## Phase 2 — H10: electricity demand → power-layer returns

### Task 8: H10 driver table

**Files:** Create `atlas/analysis/power_demand.py`; Test `atlas/tests/test_power_demand.py`

- [ ] **Step 1: Write the failing test**

```python
# atlas/tests/test_power_demand.py
import numpy as np
import pandas as pd

def _macro_long(series_levels, start="2008-01-01", n=180):
    idx = pd.date_range(start, periods=n, freq="MS")
    return pd.concat([pd.DataFrame({"series_id": s, "date": idx, "value": f(idx)})
                      for s, f in series_levels.items()], ignore_index=True)

def _daily_returns(tickers, start="2008-01-01", n=4000, seed=3):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range(start, periods=n)
    return pd.concat([pd.DataFrame({"ticker": t, "date": idx,
                                    "log_return": rng.normal(0, 0.012, n)})
                      for t in tickers], ignore_index=True)

def test_power_demand_table_shapes_and_fdr():
    from analysis.power_demand import power_demand_table
    macro = _macro_long({"IPG2211A2N": lambda i: np.exp(np.linspace(0, 0.4, len(i)))})
    returns = _daily_returns(["VST", "ETN", "D"])
    out = power_demand_table(macro, returns, demand_series=("IPG2211A2N",),
                             names=["VST", "ETN", "D"], horizons=(1, 2, 3),
                             pub_lag={"IPG2211A2N": 1}, iters=150, seed=5)
    assert len(out) == 3 * 3
    for col in ("name", "horizon", "corr", "slope", "slope_lo", "slope_hi",
                "p_selection", "q_value", "oos_sign_rate", "n_obs", "contradicts_thesis"):
        assert col in out.columns
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_power_demand.py -v`
Expected: FAIL (`ModuleNotFoundError: analysis.power_demand`).

- [ ] **Step 3: Write minimal implementation**

```python
# atlas/analysis/power_demand.py
"""H10: is the AI-power 'forgotten plays' layer pricing in the electricity-demand boom?
(pure functions)

Monthly electricity-demand YoY (PIT-lagged) vs forward monthly returns of the power-layer
names over {1,2,3}-month horizons. Selection-aware single-series null + anchored
walk-forward OOS + BH-FDR over the name x horizon family (mirrors H4/H7). Reuses Track 1
generic helpers and Track 2 monthly helpers."""
from __future__ import annotations

import numpy as np
import pandas as pd

from analysis.leading_indicators import indicator_yoy
from analysis.macro_sector import monthly_returns
from analysis.vol_termstructure import (
    _corr_slope, aligned_forward, oos_sign_rate, selection_pvalue_one_series,
)


def _demand_monthly(macro: pd.DataFrame, sid: str, pub_lag_months: int) -> pd.Series:
    sub = macro.loc[macro["series_id"] == sid, ["date", "value"]].dropna()
    if sub.empty:
        return pd.Series(dtype=float)
    s = pd.Series(sub["value"].to_numpy(float),
                  index=pd.to_datetime(sub["date"])).sort_index()
    yoy = indicator_yoy(s, pub_lag_months=pub_lag_months)
    return pd.Series(yoy.to_numpy(), index=yoy.index.to_period("M").to_timestamp())


def power_demand_table(macro: pd.DataFrame, returns: pd.DataFrame, *,
                       demand_series: tuple[str, ...], names: list[str],
                       horizons: tuple[int, ...], pub_lag: dict[str, int],
                       iters: int, seed: int) -> pd.DataFrame:
    """One row per (name, horizon): slope of forward name return on demand YoY, with
    selection-aware p, block-bootstrap CI, OOS sign-rate, BH-FDR. Uses the first
    available demand series as the predictor."""
    from analysis.fundamentals_leadlag import bootstrap_slope_ci
    from analysis.leadlag import bh_fdr

    sid = next((s for s in demand_series
                if not macro.loc[macro["series_id"] == s].empty), None)
    demand = _demand_monthly(macro, sid, pub_lag.get(sid, 1)) if sid else pd.Series(dtype=float)
    rows = []
    for name in names:
        tgt = monthly_returns(returns, name)
        for h in horizons:
            x, y = (aligned_forward(demand, tgt, horizon=h)
                    if (not demand.empty and not tgt.empty) else (np.array([]), np.array([])))
            corr, slope = _corr_slope(x, y)
            if not np.isfinite(corr) or len(x) < 10:
                rows.append({"name": name, "horizon": h, "corr": np.nan, "slope": np.nan,
                             "slope_lo": np.nan, "slope_hi": np.nan, "p_selection": 1.0,
                             "oos_sign_rate": 0.0, "n_obs": int(len(x)),
                             "contradicts_thesis": False})
                continue
            p = selection_pvalue_one_series(x, y, iters=iters, seed=seed)
            lo, hi, _ = bootstrap_slope_ci(x, y, block=3, iters=iters, seed=seed)
            sign = oos_sign_rate(demand, tgt, horizon=h, test_days=24, step_days=24,
                                 init_train_frac=0.5)
            rows.append({"name": name, "horizon": h, "corr": float(corr),
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

Run: `uv run pytest tests/test_power_demand.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add analysis/power_demand.py tests/test_power_demand.py
git commit -m "feat: H10 power_demand_table (demand -> power-name returns, walk-forward)"
```

---

### Task 9: `h10_record` + wiring

**Files:** Modify `atlas/analysis/signals.py`; Test `atlas/tests/test_signals.py`

- [ ] **Step 1: Write the failing test**

```python
# append to atlas/tests/test_signals.py
def test_h10_record_null_and_confirmed():
    from analysis.signals import h10_record
    nul = pd.DataFrame([
        {"name": "VST", "horizon": 1, "corr": 0.05, "slope": 0.4, "slope_lo": -0.3,
         "slope_hi": 1.1, "p_selection": 0.3, "q_value": 0.5, "oos_sign_rate": 0.5,
         "n_obs": 120, "contradicts_thesis": False},
        {"name": "ETN", "horizon": 3, "corr": 0.07, "slope": 0.6, "slope_lo": -0.1,
         "slope_hi": 1.3, "p_selection": 0.12, "q_value": 0.3, "oos_sign_rate": 0.55,
         "n_obs": 150, "contradicts_thesis": False},
    ])
    rec = h10_record(nul)
    assert rec["id"] == "H10" and rec["verdict"] == "null"
    assert rec["chart"]["type"] == "power_demand"
    assert rec["stat"]["q_value"] == 0.3

    conf = pd.DataFrame([
        {"name": "CEG", "horizon": 3, "corr": 0.3, "slope": 1.0, "slope_lo": 0.4,
         "slope_hi": 1.6, "p_selection": 0.001, "q_value": 0.01, "oos_sign_rate": 0.8,
         "n_obs": 120, "contradicts_thesis": False},
    ])
    assert h10_record(conf)["verdict"] == "confirmed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_signals.py -k h10 -v`
Expected: FAIL (`ImportError: cannot import name 'h10_record'`).

- [ ] **Step 3: Write minimal implementation**

Add to `atlas/analysis/signals.py` (after `h9_record`), mirroring `h7_record`:

```python
def h10_record(rows: pd.DataFrame) -> dict:
    """H10: is the chip-power 'forgotten plays' layer pricing in the demand boom?"""
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
        "confirmed": "demand growth still predicts the forgotten plays (under-priced)",
        "suggestive": "weak predictive signal",
        "null": "priced in -- the AI-power trade is well known",
        "contradicts": "predicts these names' returns the wrong way",
    }[verdict]
    n = int(best.get("n_obs")) if len(elig) else 0
    return {
        "id": "H10", "title": "Are the AI-power 'forgotten plays' pricing in the demand boom?",
        "horizon": "1-3 months",
        "claim": "Electricity-demand growth predicts power-layer (VST/NRG/CEG/ETN/VRT/D) returns",
        "mechanism": f"AI datacenters pull on power/cooling/utilities -- {interp}",
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
            "Demand proxy is economy-wide electricity output, NOT datacenter-specific.",
            "Name x {1,2,3}m family, BH-FDR; some names have short history (CEG/VRT); observational, no costs.",
        ],
        "chart": {"type": "power_demand", "ref": "h10"},
        "detail_rows": elig[["name", "horizon", "corr", "slope", "slope_lo", "slope_hi",
                             "q_value", "oos_sign_rate", "n_obs"]].to_dict("records"),
    }
```

In `build_signal_records`, after the H9 block, add:

```python
    has_h10 = con.execute("SELECT count(*) FROM information_schema.tables "
                          "WHERE table_name='power_demand'").fetchone()[0] > 0
    if has_h10:
        h10 = con.execute('SELECT * FROM power_demand').df()
        if len(h10):
            records.append(h10_record(h10))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_signals.py -k h10 -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add analysis/signals.py tests/test_signals.py
git commit -m "feat: H10 signal record + build_signal_records wiring"
```

---

## Phase 3 — Orchestration & web

### Task 10: Compute + write `power_margins` / `power_demand` in `run()`

**Files:** Modify `atlas/analysis/leadlag.py:run`

- [ ] **Step 1: Add the blocks**

In `analysis/leadlag.py::run()`, after the H8/H4 leading-indicator block (Track 2) and before `con.close()`, add:

```python
    from config import (CLOUD_MARGIN_NAMES, H10_HORIZON_MONTHS, H9_LEAD_QUARTERS,
                        INDICATOR_PUB_LAG_MONTHS, POWER_DEMAND_SERIES, POWER_NAMES,
                        POWER_PRICE_SERIES)
    present = set(macro["series_id"].unique()) if len(macro) else set()
    if any(s in present for s in POWER_PRICE_SERIES) and len(fundamentals):
        from analysis.power_margins import power_margins_table
        h9 = power_margins_table(
            macro, fundamentals, price_series=POWER_PRICE_SERIES,
            names=CLOUD_MARGIN_NAMES, leads=H9_LEAD_QUARTERS,
            pub_lag=INDICATOR_PUB_LAG_MONTHS, iters=BOOTSTRAP_ITERS, seed=RANDOM_SEED)
        con.register("h9t", h9)
        con.execute("CREATE OR REPLACE TABLE power_margins AS SELECT * FROM h9t")
        con.unregister("h9t")
        print(f"power_margins: wrote {len(h9)} price rows")
    present_names = set(returns["ticker"].unique()) if len(returns) else set()
    if any(s in present for s in POWER_DEMAND_SERIES) and any(n in present_names for n in POWER_NAMES):
        from analysis.power_demand import power_demand_table
        h10 = power_demand_table(
            macro, returns, demand_series=POWER_DEMAND_SERIES,
            names=[n for n in POWER_NAMES if n in present_names],
            horizons=H10_HORIZON_MONTHS, pub_lag=INDICATOR_PUB_LAG_MONTHS,
            iters=BOOTSTRAP_ITERS, seed=RANDOM_SEED)
        con.register("h10t", h10)
        con.execute("CREATE OR REPLACE TABLE power_demand AS SELECT * FROM h10t")
        con.unregister("h10t")
        print(f"power_demand: wrote {len(h10)} (name x horizon) rows")
```

> `returns` already contains the power tickers (Task 2 ingests them; the `returns` mart computes log returns for every ticker). `fundamentals` has `gross_margin` for the cloud names.

- [ ] **Step 2: Smoke-run locally (requires ingested data)**

Run: `uv run python -m analysis.leadlag`
Expected: `power_margins: wrote 1 ...` and `power_demand: wrote 18 ...` (6 names × 3), or skipped if the new FRED ids didn't ingest.

- [ ] **Step 3: Commit**

```bash
git add analysis/leadlag.py
git commit -m "feat: compute + persist power_margins / power_demand tables"
```

---

### Task 11: Web — map stage + chart blocks

**Files:** Modify `atlas/web/export_data.py`, `atlas/web/src/components/SignalCard.svelte`, the web stage-order constant

- [ ] **Step 1: Add `power` to the exported stages**

In `atlas/web/export_data.py`, update the hard-coded stages list in `export_all`:

```python
    stages = ["equipment", "foundry", "chips", "cloud", "power"]
```

- [ ] **Step 2: Add `power` to the web stage layout**

Find the stage-order constant in the web app:

Run: `cd web && grep -rn "equipment" src/lib src/components`

In the file that lists the stage order (e.g. `src/lib/layout.ts` or `src/lib/scenes.ts`), append `"power"` to the stages array so the map lays out the new column. Match the existing literal exactly.

- [ ] **Step 3: Add the two chart blocks to `SignalCard.svelte`** (after the existing `{#if signal.chart.type === ...}` blocks, before `{#each signal.caveats ...}`)

```svelte
  {#if signal.chart.type === "power_margins"}
    <p class="legend">Δgross-margin on −(electricity price YoY); slope &gt; 0 = compression</p>
    <ul class="edges">
      {#each signal.detail_rows as r}
        <li><span>{r.indicator}</span>
          <b>compression {Number(r.slope).toFixed(3)}</b>
          <span class="ci">[{Number(r.slope_lo).toFixed(3)}, {Number(r.slope_hi).toFixed(3)}]</span>
          <span class="lag">lead {r.best_lead}Q · q={Number(r.q_value).toFixed(2)} · n={r.n_obs}</span></li>
      {/each}
    </ul>
  {/if}
  {#if signal.chart.type === "power_demand"}
    <p class="legend">Electricity demand YoY → forward power-name return (monthly walk-forward, FDR)</p>
    <ul class="edges">
      {#each signal.detail_rows as r}
        <li><span>{r.name} · {r.horizon}m</span>
          <b>slope {Number(r.slope).toFixed(2)}</b>
          <span class="ci">[{Number(r.slope_lo).toFixed(2)}, {Number(r.slope_hi).toFixed(2)}]</span>
          <span class="lag">q={Number(r.q_value).toFixed(2)} · sign {Number(r.oos_sign_rate).toFixed(2)}</span></li>
      {/each}
    </ul>
  {/if}
```

- [ ] **Step 4: Verify the web build**

Run: `cd web && npm ci && npm run build`
Expected: build succeeds (pre-existing a11y warnings may remain). Spot-check the map renders a `power` column.

- [ ] **Step 5: Commit**

```bash
git add web/export_data.py web/src/components/SignalCard.svelte web/src/lib
git commit -m "feat: render power stage on map + power_margins/power_demand cards"
```

---

## Final verification

- [ ] **Full suite + coverage**: `uv run pytest --cov --cov-report=term-missing` — all green; new analysis modules 80%+ (network/`run()` excluded). Confirm the existing leadlag/H0 tests still pass (the stage guard must not change them).
- [ ] **Lint**: `uv run ruff check .` — no NEW issues.
- [ ] **End-to-end (if online)**: `uv run make all && uv run python web/export_data.py --db data/atlas.duckdb --out web/static/data` — `signals.json` contains H9 and H10; `graph.json` shows the `power` stage. Confirm the 2 new FRED ids ingested and the 6 power tickers have prices; fix ids in config if not.
- [ ] **Report verdicts honestly** — read H9/H10 from `signals.json`, report exactly as produced. Do NOT push; hand back for Phase 3 review (esp. H9's compression sign and H10's short-history names / contradicts-null boundary).

---

## Self-check (done while writing this plan)

- Config + power-ticker ingest + FRED ids → Tasks 1, 2, 10.
- `power` graph stage (Stage Literal + YAML nodes/edges) → Task 3.
- Stage-exclusion guard protecting H0–H5 (with regression test) → Task 4.
- H9 cost→margin compression (negated predictor, Δmargin, selection-aware, CI, FDR, no walk-forward) → Tasks 5–7.
- H10 demand→power-name returns (monthly walk-forward, selection-aware, FDR) → Tasks 8–9.
- Reuse of Track 1/2 helpers + `bh_fdr`/`bootstrap_slope_ci`/`walk_forward_folds`, no new thresholds → Tasks 6, 8.
- Orchestration + DuckDB tables + `build_signal_records` wiring → Tasks 7, 9, 10.
- Map Layer-3 render + chart types → Task 11.
- Honest caveats (blended margin/PPA-hedged; economy-wide demand; short histories) → Tasks 7, 9.
