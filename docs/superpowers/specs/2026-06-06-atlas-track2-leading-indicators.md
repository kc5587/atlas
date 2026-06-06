# Atlas Track 2 — Real Economic Leading Indicators (H8 + H4)

**Date:** 2026-06-06
**Status:** Design approved — ready for implementation plan
**Program:** Atlas Signal Lab (see `2026-06-04-atlas-signal-lab-roadmap.md`)

## Narrative placement

Track 2 adds the **physical-economy** dimension to the board. Atlas already shows
that the value chain propagates economically (H1: capex → downstream revenue) but
markets price the slow fundamental signal efficiently (H5/H2 null), while the options
market prices *risk* informatively (H6/H7 confirmed risk premia). Track 2 tests
whether the **semiconductor industrial cycle / global-trade canary** leads chip-maker
fundamentals, and whether that public signal is already in the price:

- **H8 (new; economic; confirm-likely):** the chip-cycle leading indicators (Korea
  exports + semis-production series) **lead chip-maker revenue**.
- **H4 (the long-planned roadmap card; efficiency; null-likely):** that same cycle is
  **already priced into semis equity returns** — a public canary everyone watches.

This finally builds the roadmap's H4 ("Macro cycle → sector", monthly walk-forward +
FDR), enriched with the new indicator set, and pairs it with a new H8 so the track
mirrors the H1/H5 motif. H3 (cross-sectional residual structure) remains reserved.

## Data (all FRED — keyless CSV, deep history — reuses the existing macro ingest)

Leading-indicator family. Exact series IDs are **verified at ingest**; the macro
pipeline already skips a bad/unreachable series gracefully (as DFF/DGS10 did). Each
indicator is transformed to **YoY growth** and **publication-lagged** (see PIT below).

| Role | Series (candidate FRED id) | Note |
|---|---|---|
| Global-demand canary | Korea total exports `XTEXVA01KRM664S` (OECD MEI, monthly) | confirm id at ingest; OECD-sourced, total (not semis-only) |
| Physical production | Semiconductor IP `IPG3344S` | already ingested |
| Capacity | Semis & electronic-components capacity utilization `CAPUTLG3344S` | confirm id |
| Pricing/demand | PPI semiconductors `PCU334413334413` | confirm id |
| Forward demand | New orders, computers & electronic products `A34SNO` | confirm id (Census M3) |

No new ingest module: add these ids to `FRED_SERIES` in `config.py`; `ingest/macro.py`
+ dbt `stg_macro`/`macro_daily` already expose them. A dedicated `LEADING_INDICATORS`
tuple in `config.py` names the subset used by Track 2 (so unrelated macro series such
as rates are not swept into the indicator family).

## H8 — chip-cycle indicators lead chip-maker revenue *(economic; confirm-likely)*

**Module:** `analysis/leading_indicators.py` (pure functions: DataFrame → dict/df).

**Target.** Semiconductor-sector revenue YoY growth:
- **Primary (aggregate):** cross-sectional **median** YoY revenue across the 6 US semis
  filers with SEC revenue — **AMAT, LRCX, NVDA, AMD, AVGO, MU** (ASML/TSM excluded, no
  SEC fundamentals). The canary is sector-wide, so the sector aggregate is the natural
  target (analogous to H1's cross-sectional cycle factor).
- **Secondary (per-name):** the same test per filer, surfaced in `detail_rows`.

**Predictor.** Each indicator's YoY growth, reduced to a quarterly value (calendar-
quarter mean of the monthly YoY series) after the PIT lag.

**Method.** Monthly→quarterly; one-sided lead search over **{1, 2} quarters**;
per (indicator × target) the best-lead **selection-aware p** via the single-series
block-resample null (`block_resample_one`), **block-bootstrap slope CI**
(`bootstrap_slope_ci`), and **BH-FDR over the eligible family**. **No walk-forward**
(small ~30–50-quarter sample) — effect sizes + CIs + FDR, exactly like H1
(`analysis/fundamentals_leadlag.py`). Reuse `yoy_growth`, `bootstrap_slope_ci`,
`bh_fdr`, `block_resample_one`.

**Verdict** (confirmed | suggestive | null | contradicts):
- **confirmed:** ≥1 indicator with q ≤ `FDR_ALPHA` (0.10), positive slope (canary up →
  revenue up), CI excluding 0.
- **suggestive:** ≥1 with q ≤ 0.25, right sign, CI lower > 0.
- **contradicts:** ≥1 with q ≤ `FDR_ALPHA` and the wrong (negative) sign — a
  statistically significant reversal, never a near-zero negative.
- **null:** otherwise; surface the closest-to-significant indicator.

**Evidence chain:** indicator YoY → best lead (Q) → slope (revenue YoY per indicator
YoY) → selection-aware q.

## H4 — is the chip cycle priced into semis equity? *(efficiency; null-likely)*

**Module:** `analysis/macro_sector.py` (pure functions).

**Target.** Forward **SOXX** returns (the semis sector), monthly sampled, horizons
**{1, 2, 3} months**.

**Predictor.** Same indicator family (YoY growth, PIT-lagged), monthly.

**Method.** Per (indicator × horizon): selection-aware single-series null, **anchored
walk-forward OOS** (`analysis/oos.py`; ~180 monthly obs supports folds at these short
horizons), report OOS sign-retention against the existing 0.6 floor, **BH-FDR over the
indicator×horizon family**, `contradicts` only on a significant reversal. Mirrors
H5/H7. Reuse `walk_forward_folds`, `bootstrap_slope_ci`, `bh_fdr`, the selection-aware
null.

**Verdict** mirrors H7's select-then-classify:
- **confirmed:** ≥1 cell q ≤ `FDR_ALPHA`, correct sign, OOS sign ≥ 0.6.
- **suggestive:** ≥1 cell q ≤ 0.25, correct sign, CI excluding 0.
- **contradicts:** ≥1 cell q ≤ `FDR_ALPHA` with wrong sign.
- **null:** otherwise; surface the closest-to-significant cell ("priced in").

**Evidence chain:** indicator YoY → best-cell forward-return slope → selection-aware q
→ OOS sign-retention.

## Point-in-time (the look-ahead guard)

FRED CSV returns **final-revised** values dated to the *reference* period, but those
values were not knowable then. Each indicator is **lagged by a conservative fixed
publication delay (≥ 1 month; series-specific where known)** before any alignment to
revenue quarters or forward-return windows. Revenue uses SEC **filing dates** (already
point-in-time in the fundamentals). The forward windows open strictly **after** the
indicator's effective availability date. This is observational, not a tradeable
backtest with costs.

## Code shape (mirrors existing patterns)

- `analysis/leading_indicators.py` (H8) and `analysis/macro_sector.py` (H4): pure
  functions, DataFrame in → dict/df out, TDD with synthetic fixtures.
- `analysis/signals.py`: add `h8_record`, `h4_record`; `build_signal_records` reads new
  DuckDB tables `leading_revenue` (H8) and `macro_sector` (H4), presence-guarded like
  H1/H5/H2/H6/H7.
- `analysis/leadlag.py::run()`: compute + `CREATE OR REPLACE TABLE` both; pull the
  indicator series from `macro_daily`, revenue from `fundamentals_quarterly`, SOXX
  returns from `returns`.
- **Reuse** `FDR_ALPHA = 0.10`, `OOS_SIGN_RATE_FLOOR = 0.6`, the single-series null,
  `bh_fdr`, `bootstrap_slope_ci`, `yoy_growth`, `walk_forward_folds`. **No new
  thresholds.**
- `config.py`: extend `FRED_SERIES`; add `LEADING_INDICATORS`, `SEMIS_REVENUE_NAMES`,
  `H8_LEAD_QUARTERS = (1, 2)`, `H4_HORIZON_MONTHS = (1, 2, 3)`, and a
  `INDICATOR_PUB_LAG_MONTHS` map.
- Web: `signals.ts` `SignalZ` unchanged (generic); two chart types rendered in
  `SignalCard.svelte`: **`leading_revenue`** (H8) and **`macro_sector`** (H4).

## Testing (TDD)

Pure functions developed test-first against **synthetic fixtures** with known
structure: an indicator constructed to lead a revenue series (must confirm); a flat /
unrelated indicator (must be null); a planted reversal (must read contradicts only when
significant). PIT-lag alignment tested explicitly (a value must not be usable before
its lagged availability date). Network/`run()` glue is `# pragma: no cover`. Target
80%+ on the new analysis modules.

## Verdict honesty (non-negotiable)

Report H8/H4 verdicts **exactly as produced**. H8 is *expected* to confirm because the
chip cycle genuinely leads the sector's fundamentals — a real economic relationship,
not threshold-tuned. H4 is *expected* to be null/suggestive (a public canary is largely
priced in) and that is a result. Korea exports are **total** (not semis-only) and is
labelled so on H8's caveats; the publication-lag PIT assumption is stated on both cards.

## Out of scope

- Taiwan exports, SIA/WSTS billings, SEMI book-to-bill (no clean free machine-readable
  history — deferred; the Track-1 data-risk lesson).
- Rates (`DGS10`) as a predictor — the original H4 outline mentioned it, but Track 2's
  family is the *demand/production* canary; rates can be a later addition.
- Tradeable backtest with costs/turnover; cross-sectional long-short (that is H3).
- The two pre-existing repo lint/a11y issues (tracked separately).

## Deliverables checklist

- [ ] `config.py`: `FRED_SERIES` additions + `LEADING_INDICATORS`, `SEMIS_REVENUE_NAMES`,
      `H8_LEAD_QUARTERS`, `H4_HORIZON_MONTHS`, `INDICATOR_PUB_LAG_MONTHS`
- [ ] `analysis/leading_indicators.py` (H8) + tests
- [ ] `analysis/macro_sector.py` (H4) + tests
- [ ] `h8_record` / `h4_record` + `build_signal_records` wiring + tests
- [ ] `analysis/leadlag.py::run()` writes `leading_revenue`, `macro_sector`
- [ ] Web chart types `leading_revenue`, `macro_sector` in `SignalCard.svelte`
- [ ] Verify exact FRED ids resolve at ingest; verify live `signals.json` after deploy
