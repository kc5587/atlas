# Atlas Layer 2 — SEC EDGAR Fundamentals (Scope / Design)

**Date:** 2026-06-02
**Status:** Scoped — decisions confirmed; ready for an implementation plan
**Builds on:** `2026-06-02-atlas-value-chain-design.md` (§9 roadmap, Layer 2)

---

## 1. Goal

Add company **fundamentals** (revenue, capex, gross margin) from SEC EDGAR and surface the
thesis-relevant relationship the slice couldn't: **does upstream/AI-buildout capex lead
downstream revenue and prices?** Capex is the headline "AI buildout" signal — hyperscaler
and foundry capex commitments should precede downstream revenue and, potentially, price.

## 2. Data source — SEC EDGAR XBRL API (free, no key)

- **Endpoint:** `https://data.sec.gov/api/xbrl/companyconcept/CIK{10-digit}/us-gaap/{Concept}.json`
  (single concept time series — smaller/cleaner than `companyfacts`).
- **Auth:** none, but SEC **mandates a descriptive `User-Agent`** header (e.g.
  `atlas-research contact@example.com`) and rate-limits ~10 req/s. We'll throttle.
- **Frequency:** quarterly (10-Q) + annual (10-K). Native frequency = **quarterly**.

## 3. The hard part — XBRL tag inconsistency (drives the non-goals)

us-gaap concept tags vary by filer, so each metric needs a **fallback list**, tried in order:
- **Revenue:** `RevenueFromContractWithCustomerExcludingAssessedTax` → `Revenues` →
  `SalesRevenueNet`.
- **Capex:** `PaymentsToAcquirePropertyPlantAndEquipment` →
  `PaymentsToAcquireProductiveAssets`.
- **Gross margin:** `GrossProfit` / revenue, else `(Revenue − CostOfRevenue) / Revenue`.

A small per-concept resolver picks the first tag that returns data for a CIK; unresolved
(metric, company) pairs are recorded and skipped, not faked.

## 4. Point-in-time correctness (critical — avoids lookahead bias)

EDGAR facts carry both a period `end` date and a `filed` date. **All analysis aligns on the
`filed` date** (when the number became public), never the period-end — otherwise lead/lag
results are contaminated by lookahead. We keep first-filed values; restatements are out of
scope (see non-goals).

## 5. Integration with the existing architecture

- **Node schema:** add `cik` to each node in `value_chain.yml` (SEC Central Index Key).
- **`ingest/fundamentals.py`:** per (cik, concept) pull → normalize to long format
  `[cik, ticker, concept, period_end, filed, fiscal_period, form, value, unit, accn]`,
  pandera-validated, atomic Parquet. Reuses `_base.py` + `with_retry` + throttle.
- **dbt:** `stg_fundamentals` → mart `fundamentals_quarterly` (pivoted: revenue, capex,
  gross_margin per ticker per quarter, **indexed by `filed` date**), plus quality tests
  (not_null on key, unique on (cik, concept, period_end, accn), accepted units).
- **Analysis:** extend `leadlag.py` to a **quarterly** pair type — capex→downstream-revenue
  (edge-aware) and capex→price. Reuses the native-frequency + effective-obs + block-bootstrap
  + BH-FDR machinery already built for macro.
- **App:** a "Fundamentals" view (capex/revenue trend lines, gross-margin) + fundamental
  edges flagged in the lead/lag table.

## 6. Non-goals (Layer 2)

1. **No restatement/full point-in-time vendor reconstruction** — first-filed values only.
2. **No foreign-filer fundamentals initially** — ASML (NL) and TSMC (TW) file 20-F as foreign
   private issuers with sparse/irregular XBRL; their fundamentals are deferred to Layer 2b.
   (Their *prices* and *graph position* stay; only fundamentals are deferred.)
3. **No analyst estimates, no segment-level breakdowns** — reported actuals only.
4. **Quarterly granularity** — consistent with the daily-backbone / native-frequency rules.
5. **Still descriptive, not predictive** — same correlation≠causation framing as the slice.

## 7. Decisions (confirmed 2026-06-02)

- **D1 — Universe:** ✅ **US filers first** (NVDA, AMD, AVGO, MU, AMAT, LRCX, MSFT, GOOGL,
  AMZN, META, ORCL, DELL, SMCI). ASML/TSM fundamentals deferred to Layer 2b (prices + graph
  position retained).
- **D2 — Metrics:** ✅ **revenue + capex + gross margin** only.
- **D3 — Headline analysis:** ✅ quarterly **capex→downstream-revenue** (edge-aware) and
  **capex→price** lead/lag, point-in-time on the SEC `filed` date.

## 8. Rough task outline (becomes the plan once decisions confirmed)

1. Add `cik` to `value_chain.yml` + node schema/loader validation.
2. `ingest/fundamentals.py` + pandera schema + concept-fallback resolver (TDD).
3. SEC throttle + `User-Agent` config.
4. dbt `stg_fundamentals` + `fundamentals_quarterly` mart + tests.
5. Extend `leadlag.py` with the quarterly fundamentals pair type (filed-date aligned).
6. App "Fundamentals" view + lead/lag table integration.
7. CI fixtures (tiny fundamentals parquet) + coverage; extend nightly release row_counts.
8. README/report updates; manifest `schema_version` bump (2) since marts change.
