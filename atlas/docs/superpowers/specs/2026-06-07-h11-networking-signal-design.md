# H11/H12 — Networking Signal Design Spec

**Date:** 2026-06-07
**Status:** Approved (design), pending implementation plan
**Scope:** Two new Signal Lab cards testing the networking stage (added in the map expansion). **No existing verdict touched** — protected by a byte-identical regression gate on H1/H5. This is the first of two planned signal specs (the second, H15 link-momentum, is a separate spec).

---

## 1. Goal & rationale

The map expansion added a `networking` stage (ANET, MRVL, ALAB) but no signal tests it. This spec adds two cards that mirror the existing **H1/H5 pairing** — same names, two methods, honest about which finds an edge:

- **H11 (propagation):** Does hyperscaler **capex lead networking-supplier revenue**? → tests whether the economics propagate. Prior: likely **confirms** (networking gear is a complement bought per GPU cluster).
- **H12 (pricing):** Is that buildout link **already priced into ANET/MRVL forward equity returns**? → tests whether there is an *edge*. Prior: likely **null** (efficient pricing, consistent with H5).

This deliberately parallels H1 (confirmed propagation) + H5 (null pricing): the chain propagates *economically* but is priced *efficiently*. Reporting both — even when H11 confirms the obvious and H12 finds nothing — is the honest, methodologically consistent result.

**Verdict discipline:** verdicts are reported exactly as produced (confirmed / suggestive / null / contradicts). No threshold tuning. If H11 comes back null or H12 confirms, that is the result.

---

## 2. Universe & data

| Name | Ticker | Role | In signal? |
|---|---|---|---|
| Arista Networks | ANET | networking supplier | **Yes** (long history) |
| Marvell Technology | MRVL | networking supplier | **Yes** (long history) |
| Astera Labs | ALAB | networking supplier | **No** — IPO 2024, ~6 quarters / ~1.5y returns; insufficient history. Stays on the map; excluded from the signal with an honest caveat. |

- **CIKs:** add `cik` to the ANET and MRVL nodes in `seeds/value_chain.yml`. CIK values must be looked up from SEC EDGAR `company_tickers.json` (https://www.sec.gov/files/company_tickers.json) at plan time — **do not fabricate**. (Note MRVL reincorporated in 2021; use the *current* CIK that `company_tickers.json` maps `MRVL` to.)
- **Fundamentals ingest:** `ingest/fundamentals.py:_load_nodes()` selects `id, tickers, cik from graph_nodes where cik is not null and cik != ''`. Once ANET/MRVL carry a CIK, re-running the fundamentals ingest pulls their revenue/capex/gross_margin from the SEC companyconcept API into `fundamentals_quarterly`. No new ingest code is required — only the CIKs in the seed and a pipeline re-run.
- **Predictor (customer capex):** the hyperscaler capex series (MSFT/AMZN/META) is already ingested for H1. No new macro/fundamental source.

---

## 3. Methods (mirror H1 and H5 exactly)

### H11 — propagation (engine: `analysis/fundamentals_leadlag.py::capex_revenue_edges`)

- Per networking→cloud edge, **customer (hyperscaler) capex YoY growth (lead)** vs **cycle-controlled networking-supplier revenue YoY growth**.
- Quarterly, lead search lags **1–4Q**; cycle factor = leave-one-out cross-sectional mean of downstream revenue growth (scoped to the networking family — see §4).
- Block-bootstrap slope CI; selection-aware perturbation p-value; **BH-FDR over the networking family**; **NO walk-forward** (small quarterly sample — sample-appropriate per project methodology).
- Edge set: the 4 networking→cloud edges that connect a networking supplier to a hyperscaler customer (e.g. `arista→microsoft`, `arista→meta`, `marvell→amazon`, `marvell→microsoft`). Eligibility still requires both endpoints to have the needed fundamentals.

### H12 — pricing (engine: `analysis/capex_price.py`)

- Per same networking→cloud edge: **customer capex growth, known at the SEC filing date (PIT)** → **networking-supplier M2-residual forward excess returns** over horizons **1–2Q**.
- Effect sizes + block-bootstrap CIs + BH-FDR over the networking-pricing family; **NO walk-forward** (quarterly-anchored to filing events, per H5).
- De-beta: M2 (market + orthogonalized sector) residual returns, identical to H5's `forward_excess_return`.

Both engines are reused **as-is** on a networking-restricted edge subset; no methodology is re-invented.

---

## 4. Protecting H1/H5 (the one real risk)

Once ANET/MRVL have fundamentals, the 4 networking edges become *eligible* in the H1 (`capex_revenue_edges`) and H5 (`capex_price`) drivers and would be **silently absorbed into H1's and H5's existing families** — changing their established verdicts and numbers. This violates the "no verdict changes without re-deriving" rule.

**Orchestration context:** `analysis/leadlag.py::run()` (the `make analyze` step) is the single orchestrator. It already calls `capex_revenue_edges(...)` → `CREATE OR REPLACE TABLE fundamentals_leadlag` (feeds H1) and `capex_price_edges(...)` → `CREATE OR REPLACE TABLE capex_price` (feeds H5). H11/H12 wire in here.

**Fix — partition the edge sets, in `run()`:**

- The existing H1 and H5 calls in `run()` pass an edge subset that **explicitly excludes networking-stage suppliers** (from the edge set **and** the cycle-control / cross-sectional pools), so each keeps exactly today's family.
- Add **two new calls** in `run()` that invoke the **same engines** on **only** the networking→cloud edges, persisting two new tables: `CREATE OR REPLACE TABLE networking_propagation` (from `capex_revenue_edges`) and `CREATE OR REPLACE TABLE networking_pricing` (from `capex_price_edges`). Each is its **own declared FDR family**.
- The cleanest implementation is a stage/edge-subset parameter on the drivers (e.g. an `include_stages` / `exclude_stages` filter applied before edge iteration AND before computing the cycle pool); existing callers pass the non-networking subset, new callers pass the networking subset.

**Regression gate (hard stop):** after the change, the **H1 and H5 records in `signals.json` must be byte-identical** to a pre-change baseline. If they differ, the partition leaked — stop and fix before proceeding. (Same discipline as the H10 gate used in the map-expansion work.)

---

## 5. Signal records & frontend

- Add pure builders `h11_record(rows)` and `h12_record(rows)` to `analysis/signals.py` (DataFrame in, dict out), with the same verdict logic shape as `h1_record` / `h5_record` (confirmed / suggestive / null / contradicts based on FDR-eligible cells, slope sign, and CI). Wire both into `build_signal_records`, which reads the new `networking_propagation` / `networking_pricing` tables (guarded by the same `_has_table` pattern the other builders use) and appends the records.
- **Reuse existing chart types** — no `SignalCard.svelte` changes:
  - H11 → `chart.type = "capex_revenue_overlay"` (detail_rows: `left, right, slope, slope_lo, slope_hi, lag, n_quarters`).
  - H12 → `chart.type = "capex_price"` (detail_rows: `left, right, slope, slope_lo, slope_hi, horizon, n_obs`).
- Each record carries: id, title, verdict, claim, mechanism, evidence_chain, stat (name/value/CI/q/n), detail_rows, caveats (incl. the ALAB-excluded caveat and the ex-post chain caveat).
- The two new cards appear automatically in the Signal Lab via `build_signal_records` → `signals.json`.

---

## 6. Testing & verification

- **Unit:** `h11_record` / `h12_record` verdict mapping on synthetic fixtures (each of confirmed / suggestive / null / contradicts).
- **Engine:** the networking-restricted edge subset yields the expected per-edge stats; H1/H5 subsets exclude networking suppliers (assert ANET/MRVL absent from H1/H5 edge lists and cycle pools).
- **Regression gate:** H1 + H5 records in regenerated `signals.json` byte-identical to baseline.
- **Pipeline:** full re-run (CIK seed edit → `ingest.fundamentals` → dbt build → `export_data.py`); assert `fundamentals_quarterly` now contains ANET/MRVL; assert ALAB present on the map graph but absent from H11/H12 detail_rows.
- **Frontend:** existing web tests still pass; the two new cards validate against the signals schema with their reused chart types.
- Report verdicts exactly as produced.

---

## 7. Non-goals (explicit)

- No H15 link-momentum work (separate spec).
- No new chart type or `SignalCard.svelte` changes (reuse existing renderers).
- No change to any existing H0–H10 verdict, stat, or number (enforced by the §4 regression gate).
- No ALAB in the signal; no new map nodes/edges.
- No walk-forward for either card (sample-appropriate: both are quarterly-anchored).

---

## 8. Open items for the implementation plan

- Confirm ANET and MRVL CIKs from EDGAR `company_tickers.json` at plan/execute time.
- Confirm the exact networking→cloud edge subset that is fundamentals-eligible (depends on which hyperscaler customers ANET/MRVL connect to in the seed; current edges: `arista→microsoft`, `arista→meta`, `marvell→amazon`, `marvell→microsoft`).
- Confirm `h5_record` exists / its exact name in `analysis/signals.py` to mirror (the H5 builder), and the precise verdict-logic to copy.
- Decide the `id` strings ("H11", "H12") and titles displayed on the cards.
