# H11/H12 Networking Signal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two Signal Lab cards testing the networking stage — H11 (does hyperscaler capex lead ANET/MRVL revenue?) and H12 (is that link already priced into ANET/MRVL equity?) — reusing the H1/H5 engines, without changing any existing H0–H10 verdict.

**Architecture:** Mirror the existing "power" partition pattern. `analysis/leadlag.py::run()` already excludes the `power` stage from core scans (`exclude_stage`) and runs dedicated power analysis (H9/H10). We do the same for `networking`: exclude it from the H1/H5 core families, and add a dedicated `analysis/networking_signal.py` module (like `power_demand.py`) that reuses `capex_revenue_edges` (H1) and `capex_price_edges` (H5) on a **reversed** edge subset (hyperscaler→networking, so the engines compute *customer capex → supplier revenue/returns* — the demand-pull direction). Two new persisted tables feed two new record builders.

**Tech Stack:** Python 3.13 (duckdb, pandas, numpy, pydantic), pytest. Frontend unchanged (reuses existing `capex_revenue_overlay` / `capex_price` chart types).

**Reference spec:** `docs/superpowers/specs/2026-06-07-h11-networking-signal-design.md`

**Run python via the venv:** `/Users/kaushalchitturu/Data_Quant_project/atlas/.venv/bin/python`. Work from `/Users/kaushalchitturu/Data_Quant_project/atlas` on a feature branch.

---

## Key facts established during design (do not re-derive)

- **Direction:** `capex_revenue_edges` and `capex_price_edges` compute `from_id`.capex → `to_id`.(revenue|forward-returns). H1's claim is *upstream capex → downstream revenue*. H11/H12 want the **opposite**: *customer (hyperscaler) capex → supplier (networking) revenue/returns*. So we pass **reversed** edges: for each graph edge `networking→cloud` (e.g. `arista→microsoft`), feed the engine `cloud→networking` (`microsoft→arista`).
- **CIKs (from EDGAR `company_tickers.json`):** ANET = `0001596532`, MRVL = `0001835632`. (ALAB = `0001736297`, excluded — short history.)
- **De-beta:** H12's `capex_price_edges` de-beta's the `to_id` (now the networking supplier) by `STAGE_SECTOR[to_id.stage]`. `STAGE_SECTOR` has no `networking` key → must add `"networking": "semis"` (MRVL is in SOXX; ANET trades semis-like) for proper M2 de-beta.
- **Partition:** `run()` line ~480 does `core_nodes, core_edges = exclude_stage(nodes, edges, "power")`. Add a second exclusion for `networking` so H1/H5/H0 families are unchanged. The networking module uses the **full** `nodes, edges` (to find the networking→cloud edges), not `core_*`.
- **FDR family:** passing only the ≤4 networking edges to each engine makes the networking edges their own FDR family automatically (the engines run BH-FDR over the edges passed in).
- **Networking→cloud graph edges** present in the seed: `arista→microsoft`, `arista→meta`, `marvell→amazon`, `marvell→microsoft`.

---

## File structure

| File | Responsibility | Action |
|---|---|---|
| `config.py` | `STAGE_SECTOR` | Modify (add `networking`) |
| `seeds/value_chain.yml` | node CIKs | Modify (ANET, MRVL) |
| `analysis/networking_signal.py` | reversed-edge builder + H11/H12 table functions | **Create** |
| `analysis/leadlag.py` | `run()` orchestration | Modify (exclude networking; persist 2 tables) |
| `analysis/signals.py` | `h11_record`, `h12_record`, wiring | Modify |
| `tests/test_networking_signal.py` | unit tests for the new module | **Create** |
| `tests/test_signals.py` | unit tests for the new records | Modify |

---

## Task 1: Config + CIKs (data layer)

**Files:**
- Modify: `config.py:72` (`STAGE_SECTOR`)
- Modify: `seeds/value_chain.yml` (arista, marvell nodes)
- Test: `tests/test_graph.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_graph.py`:

```python
def test_networking_nodes_have_ciks():
    from config import SEED_PATH, STAGE_SECTOR

    nodes, _ = load_graph(SEED_PATH)
    cik = dict(zip(nodes["id"], nodes["cik"]))
    assert cik["arista"] == "0001596532"
    assert cik["marvell"] == "0001835632"
    # de-beta sector wired for the networking stage
    assert STAGE_SECTOR.get("networking") == "semis"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/kaushalchitturu/Data_Quant_project/atlas && .venv/bin/python -m pytest tests/test_graph.py::test_networking_nodes_have_ciks -v`
Expected: FAIL — arista/marvell have empty cik; `STAGE_SECTOR` has no `networking` key.

- [ ] **Step 3: Add the networking sector mapping**

In `config.py:72`, change:

```python
STAGE_SECTOR: dict[str, str] = {
    "equipment": "semis", "foundry": "semis", "chips": "semis", "cloud": "cloud",
}
```

to:

```python
STAGE_SECTOR: dict[str, str] = {
    "equipment": "semis", "foundry": "semis", "chips": "semis", "cloud": "cloud",
    "networking": "semis",
}
```

- [ ] **Step 4: Add CIKs to the networking nodes**

In `seeds/value_chain.yml`, find the `arista` and `marvell` node entries and add a `cik` line to each (match existing indentation; cik sits under the node like other nodes):

```yaml
  - id: arista
    name: Arista Networks
    tickers: [ANET]
    stage: networking
    region: US
    cik: "0001596532"
  - id: marvell
    name: Marvell Technology
    tickers: [MRVL]
    stage: networking
    region: US
    cik: "0001835632"
```

(Leave `astera_labs` without a cik — it is intentionally excluded from the signal.)

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /Users/kaushalchitturu/Data_Quant_project/atlas && .venv/bin/python -m pytest tests/test_graph.py::test_networking_nodes_have_ciks tests/test_graph.py -v`
Expected: PASS (new test + all existing graph tests).

- [ ] **Step 6: Commit**

```bash
cd /Users/kaushalchitturu/Data_Quant_project
git add atlas/config.py atlas/seeds/value_chain.yml atlas/tests/test_graph.py
git commit -m "feat: add networking sector mapping + ANET/MRVL CIKs for H11/H12"
```

---

## Task 2: Reversed-edge builder (`networking_signal.py`)

**Files:**
- Create: `analysis/networking_signal.py`
- Test: `tests/test_networking_signal.py`

The builder selects graph edges that go `networking → cloud` and returns them **reversed** (`cloud → networking`), so downstream engines compute *customer capex → supplier response*.

- [ ] **Step 1: Write the failing test**

Create `tests/test_networking_signal.py`:

```python
import pandas as pd

from analysis.networking_signal import networking_capex_edges

NODES = pd.DataFrame([
    {"id": "microsoft", "tickers": '["MSFT"]', "stage": "cloud"},
    {"id": "meta", "tickers": '["META"]', "stage": "cloud"},
    {"id": "amazon", "tickers": '["AMZN"]', "stage": "cloud"},
    {"id": "arista", "tickers": '["ANET"]', "stage": "networking"},
    {"id": "marvell", "tickers": '["MRVL"]', "stage": "networking"},
    {"id": "nvidia", "tickers": '["NVDA"]', "stage": "chips"},
])
EDGES = pd.DataFrame([
    {"from_id": "arista", "to_id": "microsoft", "relationship": "supplies"},
    {"from_id": "arista", "to_id": "meta", "relationship": "supplies"},
    {"from_id": "marvell", "to_id": "amazon", "relationship": "supplies"},
    {"from_id": "marvell", "to_id": "microsoft", "relationship": "supplies"},
    {"from_id": "nvidia", "to_id": "microsoft", "relationship": "supplies"},  # not networking
])


def test_networking_capex_edges_reverses_and_filters():
    out = networking_capex_edges(NODES, EDGES)
    pairs = set(zip(out["from_id"], out["to_id"]))
    # reversed: customer (cloud) -> supplier (networking)
    assert pairs == {
        ("microsoft", "arista"), ("meta", "arista"),
        ("amazon", "marvell"), ("microsoft", "marvell"),
    }
    # the chips->cloud edge is excluded (not a networking edge)
    assert ("microsoft", "nvidia") not in pairs
    assert ("nvidia", "microsoft") not in pairs
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/kaushalchitturu/Data_Quant_project/atlas && .venv/bin/python -m pytest tests/test_networking_signal.py -v`
Expected: FAIL — module `analysis.networking_signal` does not exist.

- [ ] **Step 3: Create the module with the edge builder**

Create `analysis/networking_signal.py`:

```python
"""H11/H12: networking-stage signals.

Reuses the H1 (capex->revenue) and H5 (capex->price) engines on a REVERSED edge
subset so they compute *customer (hyperscaler) capex -> supplier (networking)
revenue / forward returns* -- the demand-pull direction, opposite to H1's
upstream->downstream orientation. Networking is excluded from the H1/H5 core
families (see analysis/leadlag.py::run) so those verdicts are unchanged.
"""
from __future__ import annotations

import pandas as pd

NETWORKING_STAGE = "networking"
CUSTOMER_STAGE = "cloud"


def networking_capex_edges(nodes: pd.DataFrame, edges: pd.DataFrame) -> pd.DataFrame:
    """Graph edges networking->cloud, returned REVERSED as cloud->networking.

    Result rows have from_id = hyperscaler customer, to_id = networking supplier,
    so capex_revenue_edges / capex_price_edges test customer.capex -> supplier.*.
    """
    stage = dict(zip(nodes["id"], nodes["stage"]))
    rows = []
    for e in edges.itertuples():
        if stage.get(e.from_id) == NETWORKING_STAGE and stage.get(e.to_id) == CUSTOMER_STAGE:
            rows.append({"from_id": e.to_id, "to_id": e.from_id,
                         "relationship": "supplies"})
    return pd.DataFrame(rows, columns=["from_id", "to_id", "relationship"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/kaushalchitturu/Data_Quant_project/atlas && .venv/bin/python -m pytest tests/test_networking_signal.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/kaushalchitturu/Data_Quant_project
git add atlas/analysis/networking_signal.py atlas/tests/test_networking_signal.py
git commit -m "feat: networking_capex_edges reversed-edge builder for H11/H12"
```

---

## Task 3: H11/H12 table functions (thin wrappers over the H1/H5 engines)

**Files:**
- Modify: `analysis/networking_signal.py`
- Test: `tests/test_networking_signal.py`

These wrap the existing engines on the reversed edge set. They are thin by design — the heavy lifting (lags, bootstrap CI, FDR, de-beta) lives in the reused engines.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_networking_signal.py`:

```python
import numpy as np

from analysis.networking_signal import networking_propagation


def _fundamentals_fixture():
    # 16 quarters; MSFT capex leads ANET revenue with a clear positive slope.
    qs = pd.period_range("2020Q1", periods=16, freq="Q").to_timestamp()
    msft_capex = np.linspace(10.0, 26.0, 16)
    anet_rev = np.concatenate([[np.nan], np.linspace(5.0, 18.0, 16)[:-1]])  # lag 1
    other_rev = np.linspace(7.0, 9.0, 16)  # flat-ish peer for the cycle factor
    frames = []
    for ticker, col, vals in [("MSFT", "capex", msft_capex),
                              ("ANET", "revenue", anet_rev),
                              ("NVDA", "revenue", other_rev)]:
        df = pd.DataFrame({"ticker": ticker, "period_end": qs,
                           "revenue": np.nan, "capex": np.nan, "gross_margin": np.nan,
                           "filed": qs})
        df[col] = vals
        frames.append(df)
    return pd.concat(frames, ignore_index=True)


def test_networking_propagation_runs_on_reversed_edges():
    fundamentals = _fundamentals_fixture()
    out = networking_propagation(fundamentals, NODES, EDGES, iters=200, seed=0)
    # one row per reversed networking edge that has fundamentals on both sides
    assert ("microsoft", "arista") in set(zip(out["left"], out["right"]))
    assert "slope" in out.columns and "q_value" in out.columns
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/kaushalchitturu/Data_Quant_project/atlas && .venv/bin/python -m pytest tests/test_networking_signal.py::test_networking_propagation_runs_on_reversed_edges -v`
Expected: FAIL — `networking_propagation` not defined.

- [ ] **Step 3: Add the two table functions**

Append to `analysis/networking_signal.py`:

```python
def networking_propagation(fundamentals: pd.DataFrame, nodes: pd.DataFrame,
                           edges: pd.DataFrame, *, iters: int, seed: int) -> pd.DataFrame:
    """H11: hyperscaler capex -> networking-supplier revenue (reuses H1 engine)."""
    from analysis.fundamentals_leadlag import capex_revenue_edges

    rev_edges = networking_capex_edges(nodes, edges)
    return capex_revenue_edges(fundamentals, nodes, rev_edges, iters=iters, seed=seed)


def networking_pricing(fundamentals: pd.DataFrame, returns: pd.DataFrame,
                       factors: dict, nodes: pd.DataFrame, edges: pd.DataFrame,
                       *, horizons, iters: int, seed: int) -> pd.DataFrame:
    """H12: is the buildout priced into networking equity? (reuses H5 engine)."""
    from analysis.capex_price import capex_price_edges

    rev_edges = networking_capex_edges(nodes, edges)
    return capex_price_edges(fundamentals, returns, factors, nodes, rev_edges,
                             horizons=horizons, iters=iters, seed=seed)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/kaushalchitturu/Data_Quant_project/atlas && .venv/bin/python -m pytest tests/test_networking_signal.py -v`
Expected: PASS (all tests in the file). If the propagation row is absent, check the fixture has ≥12 quarters and overlapping calendar quarters (the engine bins to calendar quarters).

- [ ] **Step 5: Commit**

```bash
cd /Users/kaushalchitturu/Data_Quant_project
git add atlas/analysis/networking_signal.py atlas/tests/test_networking_signal.py
git commit -m "feat: networking_propagation/networking_pricing wrappers (H11/H12)"
```

---

## Task 4: Wire into `run()` — exclude networking from core + persist 2 tables

**Files:**
- Modify: `analysis/leadlag.py` (`run()`, ~lines 480 and ~517)

`run()` is `# pragma: no cover` (orchestration). Correctness is verified by the full pipeline + regression gate in Task 6. Make the edits exactly.

- [ ] **Step 1: Exclude networking from the core family**

In `analysis/leadlag.py`, find (around line 480):

```python
    core_nodes, core_edges = exclude_stage(nodes, edges, "power")
```

and add a second exclusion immediately after it:

```python
    core_nodes, core_edges = exclude_stage(nodes, edges, "power")
    core_nodes, core_edges = exclude_stage(core_nodes, core_edges, "networking")
```

- [ ] **Step 2: Persist the two networking tables**

In `analysis/leadlag.py`, find the end of the H5 block (after `con.unregister("h5t")` and its `print(...)`, around line 517). Insert immediately after it:

```python
    from analysis.networking_signal import networking_propagation, networking_pricing
    h11 = networking_propagation(fundamentals, nodes, edges,
                                 iters=BOOTSTRAP_ITERS, seed=RANDOM_SEED)
    con.register("h11t", h11)
    con.execute("CREATE OR REPLACE TABLE networking_propagation AS SELECT * FROM h11t")
    con.unregister("h11t")
    print(f"networking_propagation: wrote {len(h11)} capex->revenue edge rows")
    h12 = networking_pricing(fundamentals, returns, _factors, nodes, edges,
                             horizons=H5_FORWARD_HORIZONS,
                             iters=BOOTSTRAP_ITERS, seed=RANDOM_SEED)
    con.register("h12t", h12)
    con.execute("CREATE OR REPLACE TABLE networking_pricing AS SELECT * FROM h12t")
    con.unregister("h12t")
    print(f"networking_pricing: wrote {len(h12)} capex->price edge rows")
```

(`nodes`, `edges`, `fundamentals`, `returns`, `_factors`, `BOOTSTRAP_ITERS`, `RANDOM_SEED`, `H5_FORWARD_HORIZONS` are all already in scope at this point in `run()`. Use the **full** `nodes, edges` here — not `core_*` — so the networking→cloud edges are visible to the builder.)

- [ ] **Step 3: Sanity-compile**

Run: `cd /Users/kaushalchitturu/Data_Quant_project/atlas && .venv/bin/python -c "import analysis.leadlag"`
Expected: imports with no syntax/name errors.

- [ ] **Step 4: Commit**

```bash
cd /Users/kaushalchitturu/Data_Quant_project
git add atlas/analysis/leadlag.py
git commit -m "feat: exclude networking from core; persist networking_propagation/pricing"
```

---

## Task 5: Record builders `h11_record` / `h12_record` + wire into `build_signal_records`

**Files:**
- Modify: `analysis/signals.py`
- Test: `tests/test_signals.py`

H11 mirrors `h1_record` (chart `capex_revenue_overlay`); H12 mirrors `h5_record` (chart `capex_price`).

- [ ] **Step 1: Write the failing tests**

First inspect the existing patterns to copy verdict logic exactly:
Run: `cd /Users/kaushalchitturu/Data_Quant_project/atlas && sed -n '423,535p' analysis/signals.py`
(That prints `h4_record` and `h5_record`; copy `h5_record`'s structure for `h12_record` and `h1_record`'s for `h11_record`.)

Add to `tests/test_signals.py`:

```python
def test_h11_record_confirmed_on_positive_significant_edge():
    from analysis.signals import h11_record
    rows = pd.DataFrame([{
        "left": "microsoft", "right": "arista", "lag": 1, "corr": 0.7,
        "slope": 0.8, "slope_lo": 0.2, "slope_hi": 1.4, "p_selection": 0.001,
        "q_value": 0.01, "n_quarters": 16, "contradicts_thesis": False,
    }])
    rec = h11_record(rows)
    assert rec["id"] == "H11"
    assert rec["verdict"] == "confirmed"
    assert rec["chart"]["type"] == "capex_revenue_overlay"


def test_h12_record_null_when_not_priced():
    from analysis.signals import h12_record
    rows = pd.DataFrame([{
        "left": "microsoft", "right": "arista", "horizon": 63, "corr": 0.05,
        "slope": 0.01, "slope_lo": -0.3, "slope_hi": 0.32, "p_selection": 0.8,
        "q_value": 0.9, "n_obs": 18, "contradicts_thesis": False,
    }])
    rec = h12_record(rows)
    assert rec["id"] == "H12"
    assert rec["verdict"] == "null"
    assert rec["chart"]["type"] == "capex_price"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/kaushalchitturu/Data_Quant_project/atlas && .venv/bin/python -m pytest tests/test_signals.py::test_h11_record_confirmed_on_positive_significant_edge tests/test_signals.py::test_h12_record_null_when_not_priced -v`
Expected: FAIL — `h11_record` / `h12_record` not defined.

- [ ] **Step 3: Implement the record builders**

Add to `analysis/signals.py` (place near `h1_record` / `h5_record`). `h11_record` copies `h1_record`'s verdict logic and detail columns; only id/title/claim/mechanism/caveats differ:

```python
def h11_record(rows: pd.DataFrame) -> dict:
    elig = rows[(rows["n_quarters"] > 0) & rows["slope"].notna()]
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
        verdict = "null"
        best = rows.iloc[0] if len(rows) else pd.Series(dtype=float)
    return {
        "id": "H11", "title": "Does the buildout pull networking revenue?",
        "horizon": "quarterly",
        "claim": "Hyperscaler capex leads networking-supplier revenue by 1–4 quarters",
        "mechanism": "Switches/optics are bought per GPU cluster — direct complements",
        "verdict": verdict,
        "evidence_chain": [
            {"stage": "raw |corr|", "metric": "|corr|",
             "value": _num(elig["corr"].abs().median()) if len(elig) else 0.0},
            {"stage": "best edge corr", "metric": "corr", "value": _num(best.get("corr"))},
            {"stage": "best edge slope", "metric": "slope", "value": _num(best.get("slope"))},
        ],
        "stat": {"name": "slope", "value": _num(best.get("slope")),
                 "ci": [_num(best.get("slope_lo")), _num(best.get("slope_hi"))],
                 "q_value": _num(best.get("q_value")), "n": n},
        "caveats": [f"~{int(elig['n_quarters'].median()) if len(elig) else 0} quarters/edge → CIs, no walk-forward",
                    "ANET/MRVL only; ALAB excluded (insufficient history)",
                    "Chain specified ex-post; tests propagation given the chain"],
        "chart": {"type": "capex_revenue_overlay", "ref": "h11"},
        "detail_rows": elig[["left", "right", "lag", "corr", "slope", "slope_lo",
                             "slope_hi", "q_value", "n_quarters"]].to_dict("records"),
    }
```

Then add `h12_record`, copying `h5_record`'s exact verdict logic and detail columns (read them in Step 1). Change only the identity/text fields and keep its chart type:

```python
def h12_record(rows: pd.DataFrame) -> dict:
    # Verdict logic: copy h5_record's body verbatim (eligibility on n_obs + finite
    # slope, the confirmed/suggestive/contradicts/null tiers, and best-row pick).
    # Only the returned dict's identity fields differ:
    rec = h5_record(rows)
    rec["id"] = "H12"
    rec["title"] = "Is the networking buildout already priced in?"
    rec["claim"] = "Is hyperscaler capex already priced into ANET/MRVL forward returns?"
    rec["mechanism"] = "If markets price the complement promptly, no forward edge remains"
    rec["caveats"] = ["ANET/MRVL only; ALAB excluded (insufficient history)",
                      "PIT on filing date; M2-residual forward returns; no walk-forward",
                      "Confirmed = NOT yet priced in · Null = priced in"]
    rec["chart"] = {"type": "capex_price", "ref": "h12"}
    return rec
```

NOTE: confirm by reading Step 1's output that `h5_record` returns a fresh dict each call (it does — it builds a literal), so mutating the returned dict is safe. If `h5_record`'s detail columns differ from the H12 table columns, the reuse still works because `h12_record` passes the H12 `rows` straight through `h5_record`.

- [ ] **Step 4: Wire both into `build_signal_records`**

Inspect the wiring pattern:
Run: `cd /Users/kaushalchitturu/Data_Quant_project/atlas && sed -n '540,600p' analysis/signals.py`
You will see guarded blocks like:
```python
        if _has_table(con, "capex_price"):
            h5 = con.execute('SELECT * FROM capex_price').df()
            records.append(h5_record(h5))
```
Add two analogous blocks (next to the H1 and H5 blocks), using the same `_has_table` guard helper already used there:

```python
        if _has_table(con, "networking_propagation"):
            h11 = con.execute('SELECT * FROM networking_propagation').df()
            records.append(h11_record(h11))
        if _has_table(con, "networking_pricing"):
            h12 = con.execute('SELECT * FROM networking_pricing').df()
            records.append(h12_record(h12))
```

(If the existing code uses a differently-named table-existence guard, match it exactly — read the surrounding lines.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/kaushalchitturu/Data_Quant_project/atlas && .venv/bin/python -m pytest tests/test_signals.py -v`
Expected: PASS (new records + all existing signal tests).

- [ ] **Step 6: Commit**

```bash
cd /Users/kaushalchitturu/Data_Quant_project
git add atlas/analysis/signals.py atlas/tests/test_signals.py
git commit -m "feat: h11_record/h12_record + wire into build_signal_records"
```

---

## Task 6: Full pipeline regen + H1/H5 regression gate + verification

**Files:** none (regeneration + verification).

- [ ] **Step 1: Snapshot the H1/H5 baseline cards**

Run:
```bash
cd /Users/kaushalchitturu/Data_Quant_project/atlas
.venv/bin/python -c "
import json
s=json.load(open('web/static/data/signals.json'))
by={r['id']:r for r in s}
json.dump({'H1':by['H1'],'H5':by['H5']}, open('/tmp/h1h5.before.json','w'), sort_keys=True, indent=2)
print('baseline H1/H5 saved')
"
```

- [ ] **Step 2: Re-ingest fundamentals (pulls ANET/MRVL from SEC)**

Run: `cd /Users/kaushalchitturu/Data_Quant_project/atlas && .venv/bin/python -m ingest.graph && .venv/bin/python -m ingest.fundamentals`
Expected: graph re-ingests (29 nodes); fundamentals ingest runs and now includes ANET/MRVL (it reads nodes `where cik is not null`). If the SEC fetch is rate-limited/offline, retry; the companyconcept API needs network.

- [ ] **Step 3: Rebuild dbt + re-run analysis + re-export**

Run:
```bash
cd /Users/kaushalchitturu/Data_Quant_project/atlas/dbt_project && \
ATLAS_DATA_RAW="$(cd .. && pwd)/data/raw" ATLAS_DUCKDB_PATH="$(cd .. && pwd)/data/atlas.duckdb" ../.venv/bin/dbt build --profiles-dir . >/tmp/dbt.log 2>&1 && tail -3 /tmp/dbt.log
cd /Users/kaushalchitturu/Data_Quant_project/atlas && .venv/bin/python -m analysis.leadlag
.venv/bin/python web/export_data.py --db data/atlas.duckdb --out web/static/data
```
Expected: dbt completes; analysis prints `networking_propagation: wrote N ...` and `networking_pricing: wrote N ...`; export writes JSON.

- [ ] **Step 4: H1/H5 REGRESSION GATE (hard stop)**

Run:
```bash
cd /Users/kaushalchitturu/Data_Quant_project/atlas && .venv/bin/python -c "
import json
s={r['id']:r for r in json.load(open('web/static/data/signals.json'))}
before=json.load(open('/tmp/h1h5.before.json'))
after={'H1':s['H1'],'H5':s['H5']}
import json as j
assert j.dumps(after['H1'],sort_keys=True)==j.dumps(before['H1'],sort_keys=True), 'H1 CHANGED'
assert j.dumps(after['H5'],sort_keys=True)==j.dumps(before['H5'],sort_keys=True), 'H5 CHANGED'
print('H1/H5 UNCHANGED ✓')
"
```
Expected: `H1/H5 UNCHANGED ✓`. **If it fails, STOP** — the networking partition leaked into the core families. Re-check the two `exclude_stage` calls in Task 4 Step 1 before continuing.

- [ ] **Step 5: Verify the new cards + ALAB exclusion**

Run:
```bash
cd /Users/kaushalchitturu/Data_Quant_project/atlas && .venv/bin/python -c "
import json
s={r['id']:r for r in json.load(open('web/static/data/signals.json'))}
assert 'H11' in s and 'H12' in s, 'missing new cards'
print('H11 verdict:', s['H11']['verdict'], '| H12 verdict:', s['H12']['verdict'])
rows = s['H11']['detail_rows'] + s['H12']['detail_rows']
names = {r.get('left','')+r.get('right','') for r in rows}
assert not any('astera' in n or 'ALAB' in n for n in names), 'ALAB leaked into signal'
# ANET/MRVL fundamentals present
import duckdb
con=duckdb.connect('data/atlas.duckdb', read_only=True)
ft=set(con.execute(\"select distinct ticker from fundamentals_quarterly\").df()['ticker'])
assert {'ANET','MRVL'} <= ft, f'missing fundamentals: {{\"ANET\",\"MRVL\"}}-{ft}'
print('ANET/MRVL fundamentals present; ALAB absent from signal ✓')
"
```
Expected: prints H11/H12 verdicts (report them as-is — H11 likely confirmed, H12 likely null, but whatever they are is the result) and the two ✓ lines.

- [ ] **Step 6: Full test suite + lint + web build**

Run:
```bash
cd /Users/kaushalchitturu/Data_Quant_project/atlas && .venv/bin/python -m pytest -q 2>&1 | tail -1 && .venv/bin/ruff check . && cd web && npm run test 2>&1 | grep -E "Tests " && npm run build 2>&1 | tail -2
```
Expected: all green; the two new cards render via the reused chart types (no frontend change needed).

- [ ] **Step 7: Commit any regenerated tracked artifacts**

```bash
cd /Users/kaushalchitturu/Data_Quant_project
git add -A atlas
git commit -m "chore: regenerate analysis tables for H11/H12 networking signal" || echo "nothing tracked to commit (web/static/data is gitignored)"
```

---

## Self-review notes (for the executor)

- **Spec coverage:** §1 two cards → Tasks 5; §2 universe/CIK → Task 1; §3 methods (reuse H1/H5 engines, reversed edges, no walk-forward) → Tasks 2–4; §4 protect H1/H5 (exclude_stage + regression gate) → Task 4 Step 1 + Task 6 Step 4; §5 records + reuse chart types → Task 5; §6 testing → all tasks + Task 6.
- **Direction is the critical correctness point:** H11/H12 reverse the graph edges (customer→supplier) because the engines compute `from`.capex → `to`.response and we want hyperscaler capex → networking response. Task 2's test pins this.
- **No verdict tuning:** report H11/H12 exactly as produced. If H11 is null or H12 confirms, that is the finding.
- **`web/static/data` is gitignored** (regenerated by the deploy workflow) — Task 6 Step 7 will no-op on it; that's expected.
- **Confirmed:** `h5_record` eligibility is `(rows["n_obs"] > 0) & rows["slope"].notna()` and it reads columns `left,right,horizon,corr,slope,slope_lo,slope_hi,q_value,n_obs,contradicts_thesis` — exactly what `capex_price_edges` (and therefore `networking_pricing`) produces, and exactly what the Task 5 H12 fixture supplies. The `h12_record = call h5_record then override identity` reuse is safe (h5_record builds a fresh literal dict and reads only the passed rows).
