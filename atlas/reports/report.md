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
