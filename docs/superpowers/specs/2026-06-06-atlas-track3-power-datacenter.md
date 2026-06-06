# Atlas Track 3 — Power / Datacenter (H9 + H10)

**Date:** 2026-06-06
**Status:** Design approved — ready for implementation plan
**Program:** Atlas Signal Lab (see `2026-06-04-atlas-signal-lab-roadmap.md`)

## Narrative placement

Track 3 extends the value chain to its **forgotten Layer 3** — the power, cooling, and
utility names that the AI-datacenter buildout pulls on — using real, free energy data.
Two cards:

- **H9 (economic; clean/keyless):** does rising **electricity cost** compress **cloud
  gross margins**? Power is a genuine datacenter operating cost.
- **H10 (Layer-3 market test):** are the AI-power **"forgotten plays"** (VST, NRG, CEG,
  ETN, VRT, D) already **pricing in** the electricity-demand boom, or does demand growth
  still predict their returns?

This adds the power layer to the value-chain map and keeps the board's honest arc: real
economic links, tested rigorously, reported as produced.

## Data constraint (the reckoning, same as Tracks 1–2)

EIA's richest data (hourly/regional demand by balancing authority, EIA-930) needs a
**free API key** and there is **no clean free "datacenter power demand" series**. To
stay consistent with the project's keyless-FRED pattern we use FRED only:

- **Cost** is easy: electricity **price** indices (keyless, deep history).
- **Demand** is proxied by electricity **output/utilities industrial production** YoY —
  **economy-wide, not datacenter-specific** (stated honestly on H10's caveats).
- The 6 power-layer **prices** come from yfinance (trivial).

Exact FRED ids are **verified at ingest**; `ingest/macro.py` skips an unreachable/invalid
series gracefully (as DFF/DGS10 did).

| Role | Candidate FRED id | Note |
|---|---|---|
| Electricity price (H9) | `WPU0543` (PPI electric power) and/or `APU000072610` (avg price/kWh) | confirm at ingest; producer-price proxy, not PPA-contracted |
| Electricity demand (H10) | `IPG2211A2N` / `IPUTIL` (electric-power / utilities IP) | confirm at ingest; deep history, keyless |

## H9 — electricity cost → cloud margins *(economic)*

**Module:** `analysis/power_margins.py` (pure functions: DataFrame → dict/df).

**Target.** Quarterly **change in gross margin** (first difference Δ, for stationarity —
gross margin is a level/ratio), cross-sectional **median** across the cloud names with
SEC gross margin: **MSFT, GOOGL, AMZN, ORCL**.

**Predictor.** Electricity price YoY, **PIT-lagged**, lead **{0, 1, 2} quarters** (cost
passes into margin with a lag).

**Direction.** Hypothesis is **negative** (cost ↑ → margin ↓). To reuse the existing
one-sided positive-slope machinery unchanged, the predictor is **negated** (use
`-price_yoy`); then a positive slope of Δmargin on `-price_yoy` = margin falls as price
rises. **confirmed = a statistically significant cost→margin compression.**

**Method.** Best-lead **selection-aware p** (single-series block-resample null on the
predictor), **block-bootstrap slope CI**, **BH-FDR** over the eligible family.
**No walk-forward** (small ~30–50-quarter sample) — effect sizes + CIs + FDR, like
H1/H8.

**Verdict** (confirmed | suggestive | null | contradicts):
- **confirmed:** q ≤ `FDR_ALPHA` (0.10), slope > 0 on the negated predictor (i.e.
  compression), CI excluding 0.
- **suggestive:** q ≤ 0.25, right sign, CI lower > 0.
- **contradicts:** q ≤ `FDR_ALPHA` with the wrong sign (cost *raises* margin —
  implausible) — significant only, never near-zero.
- **null:** otherwise.

**Honest prior:** electricity is a small fraction of blended megacap COGS and the cloud
providers sign long-term PPAs, so this is **expected to be null/suggestive** — reported
exactly as produced. Gross margin is **blended**, not datacenter-segment, which dilutes
the signal (caveat).

**Evidence chain:** electricity price YoY → best lead (Q) → cost→margin slope → q.

## H10 — electricity demand → power-layer returns *(forgotten plays)*

**Module:** `analysis/power_demand.py` (pure functions).

**Target.** Forward **returns** of the 6 power-layer names — **VST, NRG, CEG, ETN, VRT,
D** — monthly, horizons **{1, 2, 3} months**.

**Predictor.** Electricity-demand YoY (FRED), **PIT-lagged**. Positive direction (demand
growth ↑ → power names ↑).

**Method.** Per (name × horizon): selection-aware single-series null, **anchored
walk-forward OOS** (`analysis/oos.py`), OOS sign-retention vs the 0.6 floor, **BH-FDR**
over the name×horizon family, `contradicts` only on a significant reversal. Reuses the
generic `vol_termstructure` helpers (`aligned_forward`, `selection_pvalue_one_series`,
`oos_sign_rate`, `_corr_slope`) and the H8 monthly-YoY/PIT and `monthly_returns`
patterns. Per-name samples vary (ETN/NRG/D long; VST ~9y; VRT ~5y; CEG ~4y) — handled by
per-name n and FDR; short-history names caveated.

**Verdict** mirrors H4/H7's select-then-classify: confirmed if a name×horizon cell
passes FDR with the right sign and OOS sign ≥ 0.6; suggestive / contradicts / null per
the shared rules; null surfaces the closest-to-significant cell ("priced in").

**Evidence chain:** demand YoY → best-cell forward-return slope → q → OOS sign-retention.

## Value-chain map — Layer-3 expansion (guarded)

Add a **`power`** stage to `value_chain.yml` with the 6 names as nodes and **cloud →
power** edges, so the map shows the forgotten Layer 3 and the AI-buildout's downstream.

**Guard (critical):** the existing leadlag / H0–H5 edge scans must be **explicitly
scoped to exclude the `power` stage**, so shipped verdicts (H0/H1/H2/H5) are
**unchanged**. H10 reads its basket from a config `POWER_NAMES` list, **not** the edge
scan. Concretely: the daily lead/lag scan and the capex→revenue/price/event scans filter
to the original four stages (`equipment`, `foundry`, `chips`, `cloud`); the `power`
stage is map-only + H10-only.

## Code shape (mirrors existing patterns)

- `config.py`: extend `FRED_SERIES`; add `POWER_NAMES = ["VST","NRG","CEG","ETN","VRT","D"]`,
  `POWER_PRICE_SERIES`, `POWER_DEMAND_SERIES`, `H9_LEAD_QUARTERS = (0,1,2)`,
  `H10_HORIZON_MONTHS = (1,2,3)`, and `INDICATOR_PUB_LAG_MONTHS` entries; add `POWER_NAMES`
  to the price ingest list (alongside `UNIVERSE`/`FACTOR_TICKERS`/`AUX_TICKERS`).
- `ingest/prices.py`: include `POWER_NAMES` in the default ticker list.
- `seeds/value_chain.yml`: add the `power` stage nodes + `cloud→power` edges.
- `analysis/power_margins.py` (H9) + `analysis/power_demand.py` (H10): pure functions,
  TDD with synthetic fixtures.
- `analysis/signals.py`: `h9_record`, `h10_record`; `build_signal_records` reads new
  tables `power_margins` / `power_demand`, presence-guarded.
- `analysis/leadlag.py`: compute + write both tables in `run()`; **add the power-stage
  exclusion guard** to the existing edge scans.
- **Reuse** `FDR_ALPHA`, `OOS_SIGN_RATE_FLOOR`, the single-series null, `bh_fdr`,
  `bootstrap_slope_ci`, `walk_forward_folds`, and the H8/`vol_termstructure` helpers.
  **No new thresholds.**
- Web: two chart types in `SignalCard.svelte` (`power_margins`, `power_demand`); the map
  (`ValueChainMap.svelte`) renders the new `power` stage from `graph.json` automatically.

## Testing (TDD)

Pure functions test-first against synthetic fixtures: a price series constructed to
compress a margin series at a known lead (H9 must confirm with the negative-direction
convention); a flat predictor (null); a demand series that leads a name's returns (H10
must confirm); a planted reversal (contradicts only when significant). The **edge-scan
exclusion guard** gets a regression test: adding a `power`-stage node/edge must NOT
change the set of edges H0 scans. Network/`run()` glue is `# pragma: no cover`. 80%+ on
new analysis modules.

## Verdict honesty (non-negotiable)

Report H9/H10 exactly as produced. H9 is *expected* null/suggestive (power is a small,
hedged input to blended megacap margins) — that is a result. H10's electricity-demand
proxy is **economy-wide, not datacenter-specific**, and several power names have short
histories — both stated on caveats. No threshold tuning.

## Out of scope

- EIA API key / EIA-930 regional demand (keeps the keyless pattern; deferred).
- Datacenter-segment margins (only blended SEC gross margin is free).
- Power-names *revenue* economic test (H10 is returns-only this track).
- The two pre-existing repo lint/a11y issues.

## Deliverables checklist

- [ ] `config.py`: `FRED_SERIES` + `POWER_NAMES`, price/demand series, H9/H10 params, PIT lags
- [ ] `ingest/prices.py`: ingest `POWER_NAMES`
- [ ] `seeds/value_chain.yml`: `power` stage nodes + `cloud→power` edges
- [ ] `analysis/leadlag.py`: power-stage exclusion guard on existing edge scans (+ regression test)
- [ ] `analysis/power_margins.py` (H9) + tests
- [ ] `analysis/power_demand.py` (H10) + tests
- [ ] `h9_record` / `h10_record` + `build_signal_records` wiring + tests
- [ ] `analysis/leadlag.py::run()` writes `power_margins`, `power_demand`
- [ ] Web chart types `power_margins`, `power_demand` in `SignalCard.svelte`
- [ ] Verify FRED ids + power-ticker prices ingest; verify live `signals.json` + map after deploy
