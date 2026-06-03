# Atlas AI Value-Chain Report

## Value-Chain Overview

Atlas traces the core AI infrastructure chain from upstream semiconductor
equipment through foundries, chip designers, and downstream hyperscalers. The
validated graph in `seeds/value_chain.yml` is the source of truth for nodes,
ticker aliases, directional upstream-to-downstream edges, evidence, and
provenance dates.

## Method: Lead/Lag Analysis

The analysis reads daily price returns, native-frequency macro series, and the
validated graph from DuckDB. For each value-chain edge, it searches a fixed lag
window using the convention that a positive lag means the left-hand series leads
the right-hand series. Macro comparisons resample price returns to the macro
series frequency and express lags in months.

Inference preserves temporal structure through stationary block bootstrap
p-values, then applies Benjamini-Hochberg false-discovery-rate correction.
Results include effective observations and a cross-subperiod stability flag.
Daily price pairs require at least 250 observations; macro comparisons require
at least 36 native-frequency observations.

## Findings

This section is populated from the `leadlag` table after `make all`.

```sql
select
  pair_type,
  left,
  right,
  lag,
  corr,
  p_value,
  q_value,
  n_eff,
  stable
from leadlag
order by q_value, abs(corr) desc;
```

Report the strongest corrected relationships first. Label any raw peak shown
outside this table as uncorrected, and separate stable findings from
subperiod-sensitive findings.

## Capex as the AI-buildout signal

Layer 2 adds SEC EDGAR fundamentals for US filers and treats capex as the
reported AI-buildout signal. Capex captures the cash commitment behind compute
capacity, data-center expansion, semiconductor equipment, and integration spend.
It is reported less frequently than prices, so fundamentals are analyzed at
quarterly cadence rather than stretched onto the daily backbone.

## Method (point-in-time, quarterly, filed-date aligned)

Fundamental observations use the SEC `filed` date, not the fiscal period-end
date, so the analysis only uses values after they were public. Revenue and capex
come from filer-specific us-gaap concept fallback lists; gross margin is reported
as `GrossProfit / revenue` when available, otherwise `(revenue - cost of revenue)
/ revenue`. Restatements are not reconstructed: Atlas keeps first-filed values.

Fundamental lead/lag rows are emitted into the same `leadlag` table as price and
macro rows. `fund_capex_rev` compares upstream capex to downstream revenue along
graph edges. `fund_capex_price` compares a company's capex to its own quarterly
price-return intervals aligned to filing dates.

## Capex->downstream-revenue findings (reads `leadlag` where `pair_type` in fund_*)

Use the query below after `make all` to isolate Layer 2 fundamentals rows:

```sql
select
  pair_type,
  left,
  right,
  lag,
  corr,
  p_value,
  q_value,
  n_eff,
  stable
from leadlag
where pair_type in ('fund_capex_rev', 'fund_capex_price')
order by q_value, abs(corr) desc;
```

Read positive lags as capex leading the downstream revenue or price-return
series by that many quarters. Treat any row with low effective observations,
weak stability, or high q-value as a research lead rather than a finding.

## Caveats (US filers only; foreign filers deferred; first-filed, no restatements)

Layer 2 covers US filers first: NVDA, AMD, AVGO, MU, AMAT, LRCX, MSFT, GOOGL,
AMZN, META, ORCL, DELL, and SMCI. ASML and TSMC remain in prices and graph
relationships, but their fundamentals are deferred to Layer 2b. The data uses
reported actuals only, first-filed values only, and no segment-level or analyst
estimate reconstruction.

## Hypotheses: Where To Look Next

- Which upstream equipment or foundry signals consistently lead downstream chip
  designers after false-discovery-rate correction?
- Which downstream relationships remain stable across subperiods?
- Do native-frequency macro relationships suggest useful research windows for
  follow-up event studies?
- Where should fundamentals, filings, or additional graph evidence be added in
  the next research layer?

## Caveats

Correlation does not imply causation. Lead/lag results are exploratory,
descriptive signals rather than forecasts, trading recommendations, or evidence
of alpha. Free data sources, daily granularity, bounded history, and a curated
graph limit the scope of any conclusion.
