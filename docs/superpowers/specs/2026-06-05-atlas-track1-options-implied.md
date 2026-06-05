# Atlas Track 1 — Options-Implied Data (H6 + H7 + Collector B)

**Date:** 2026-06-05
**Status:** Design approved — ready for implementation plan
**Program:** Atlas Signal Lab (see `2026-06-04-atlas-signal-lab-roadmap.md`)

## Narrative placement

Atlas's story so far: the value chain propagates **economically** (H1 confirmed:
capex → downstream revenue) but equity markets price the slow signal **efficiently**
(H5/H2 null: capex is already in the price). Track 1 adds the **risk** dimension from
the options market:

- **H6 (confirm-likely):** the options market prices *risk* informatively — the
  variance risk premium exists and implied vol carries forecast content.
- **H7 (genuinely uncertain):** but that risk signal is itself largely efficient —
  the vol term-structure slope does not reliably time forward sector returns.

One-line extension: *the chain propagates economically (H1); equity markets price the
slow signal efficiently (H5/H2); the options market prices risk informatively (H6) —
yet that risk signal too is largely priced in (H7).*

## Hard data constraint (the reason this track is shaped as it is)

**There is no free historical single-name implied-vol data.** `yfinance` option chains
are a **live snapshot only** — no history. So "upstream IV leads downstream IV across
the chain" cannot be backtested today.

What *is* free with deep history is **index/sector-level** vol:

- VIX term structure: `^VIX9D`, `^VIX`, `^VIX3M`, `^VIX6M` (CBOE/yfinance), FRED
  fallbacks `VIXCLS`.
- VXN (Nasdaq-100 30-day implied): `^VXN`, FRED `VXNCLS`.
- Realized vol — computable from any price series we already hold (SPY/SOXX/IGV/15
  names), plus **QQQ** which we add as VXN's matched underlying.

There is **no free semiconductor implied-vol index with history**, so semis enters via
**realized vol only**, with an explicit caveat. This constraint is reported honestly on
the cards — it is not worked around with loose proxies.

## Scope (Hybrid)

1. **Ship now:** two Signal Lab cards, **H6** and **H7**, sharing one vol-data ingest,
   each producing an honest verdict.
2. **Start in parallel (silent infra):** **Collector B**, a daily single-name IV
   snapshot pipeline that accumulates a per-name panel for a future chain-propagation
   card. No card ships until it has enough history to earn a verdict.

## Data ingest

### `ingest/vol.py` (network; `# pragma: no cover` on fetchers)
- Fetch daily history for `^VIX9D, ^VIX, ^VIX3M, ^VIX6M, ^VXN` via yfinance index
  quotes. **FRED fallback** (`VIXCLS`, `VXNCLS`) when index symbols return empty.
- Normalize to long format `(date, series, close)`, validated by a pandera schema in
  the style of `PRICE_SCHEMA`.
- Atomic-write parquet under `data/raw/vol/`.

### Config additions (`config.py`)
- Add `QQQ` to the auxiliary/factor tickers ingested by `prices.py` (VXN's matched
  underlying for H6). It is **not** a value-chain node — purely a realized-vol match.
- Add `VOL_SERIES` (the index symbols + FRED fallback map) and Track 1 parameters
  (forward windows, horizons, predictor definition) alongside the existing H2/H5
  parameter blocks.

### Realized vol
Computed in analysis from existing price parquet — close-to-close log-return realized
volatility, annualized, over the matched forward window. No new raw data needed.

## H6 — Variance risk premium & implied-vol information content

**Module:** `analysis/vol_premium.py` (pure functions: DataFrame in → dict/df out).

**Pairs:** market (VIX ↔ SPY), tech (VXN ↔ QQQ).

**VRP measurement.** For each day *t*: implied variance = (IV_t / 100)² (annualized);
realized variance = annualized variance of forward 21-trading-day log returns of the
matched underlying. VRP_t = implied² − realized². The premium is judged present if
mean VRP > 0 with a **block-bootstrap CI excluding 0**, block length from the
Politis–White estimator (`auto_block_length` in `analysis/significance.py`), seed from
`config.RANDOM_SEED`. Overlapping forward windows → use block bootstrap, not iid.

**Information content.** Does IV(t) forecast forward RV incrementally over lagged RV?
Anchored walk-forward (reuse `analysis/oos.py` patterns): compare out-of-sample
predictive R² of an (IV + lagged-RV) model against an (RV-only) model. IV "carries
information" if it adds significant OOS predictive content.

**Verdict logic** (vocabulary: confirmed | suggestive | null | contradicts):
- **confirmed:** mean VRP > 0 with CI excluding 0 **and** IV adds significant OOS
  forecast content (positive incremental OOS R²).
- **suggestive:** one of the two holds; the other is directionally right but inside CI.
- **null:** neither holds.
- **contradicts:** statistically significant *negative* VRP (implied < realized) —
  would require a CI strictly below 0; a near-zero negative is null, not a reversal.

**Evidence chain stages:** implied vol → realized vol → premium (annualized vol pts) →
OOS incremental R².

## H7 — Vol term-structure slope as a forward-return timer

**Module:** `analysis/vol_termstructure.py` (pure functions).

**Predictor:** S&P term-structure slope, defined as the VIX/VIX3M ratio (> 1 =
backwardation/stress; < 1 = contango/calm). One-sided declared direction a priori,
matching the existing selection-aware framework. (VXN has no free term structure, so the
slope signal is S&P-only; it may predict any target.)

**Targets × horizons:** {SPY, SOXX, IGV} × {21, 42, 63} trading days → a **9-cell
family**. Targets are raw forward returns (a timing decision is in/out of the asset);
SPY is the market baseline, SOXX/IGV are the chain sectors.

**Rigor (reuse existing machinery):**
- Selection-aware significance with the **single-series perturbation null** (never
  joint) — `analysis/significance.py`.
- **BH-FDR over the full 9-cell family**, computed over eligible cells only.
- **Anchored walk-forward OOS** (`analysis/oos.py`) — daily data supports it; report
  OOS sign-retention against the existing 0.6 floor (descriptive, not a test).
- `contradicts` requires a **statistically significant reversal** (negative slope
  passing FDR); a near-zero negative is null.

**Verdict logic** mirrors H5's selection-then-classify:
- **confirmed:** ≥1 cell with q ≤ `FDR_ALPHA` (0.10), correct sign, OOS sign ≥ 0.6.
- **suggestive:** ≥1 cell q ≤ 0.25, correct sign, bootstrap CI excluding 0.
- **contradicts:** ≥1 cell q ≤ `FDR_ALPHA` with the wrong sign.
- **null:** otherwise — surface the closest-to-significant cell so the card shows even
  the strongest link does not pass ("priced in").

**Evidence chain stages:** term-structure slope → best-cell forward-return slope →
selection-aware p / FDR q → OOS sign-retention.

## Collector B — single-name IV snapshot pipeline (silent infra)

**Module:** `ingest/iv_snapshot.py`.

- Daily `yf.Ticker(t).option_chain()` for the 15 universe names.
- Per name, per day compute and store: **30-day constant-maturity ATM IV**
  (interpolated across the two bracketing expiries), **25-delta risk-reversal skew**,
  **term-structure slope** (near vs far expiry ATM IV), **put/call open-interest ratio**.
- Append **one idempotent row per (ticker, date)** to a panel parquet under
  `data/raw/iv_snapshots/`. Re-running on the same date overwrites that date's rows, not
  duplicates.
- Runs inside the **existing `update-data.yml` daily workflow** so the panel
  self-accumulates on the deploy cadence.
- **No Signal Lab card** until the panel has enough history; its analysis/verdict is a
  future spec.

## Assembly & web

- `analysis/signals.py`: add `h6_record` and `h7_record` (pure: DataFrame → dict).
  `build_signal_records` reads new DuckDB tables `vol_premium` and `vol_termstructure`,
  presence-guarded exactly like H1/H5/H2.
- **Reuse** `FDR_ALPHA = 0.10`, `OOS_SIGN_RATE_FLOOR = 0.6`, selection-aware null, and
  bootstrap-CI helpers. **No new thresholds.**
- DuckDB tables: `vol_indices` (raw), `vol_premium` (H6), `vol_termstructure` (H7);
  `iv_snapshots` panel for Collector B.
- Web: `web/src/lib/signals.ts` `SignalZ` schema is **unchanged** (it is generic). Add
  two chart types rendered by `SignalCard.svelte`: **`vrp_term`** (H6: implied vs
  realized vol + premium) and **`termstructure_timing`** (H7: slope-vs-forward-return
  scatter / best-cell bars).

## Testing (TDD)

- Pure analysis functions (`vol_premium.py`, `vol_termstructure.py`, the snapshot
  feature computations) are developed test-first (RED → GREEN) against **synthetic
  vol/price fixtures** with known properties (e.g., a constructed series with a known
  positive VRP; a slope series with a planted forward-return relationship; a flat series
  that must yield null).
- Network fetchers (`ingest/vol.py`, `ingest/iv_snapshot.py` download paths) are marked
  `# pragma: no cover`, as `prices.py` is.
- Coverage target 80%+ on the new analysis modules.

## Verdict honesty (non-negotiable)

Report H6 and H7 verdicts **exactly as produced**. No threshold loosening to manufacture
a confirm. H6 is *expected* to confirm because the variance risk premium is a genuine,
documented effect reproduced on new free data — that is the legitimate way to grow the
board's confirms. H7 is expected to be null/suggestive and that is a result, not a
failure. The semis-implied-unavailable limitation is stated on H6's caveats.

## Out of scope

- Single-name IV *analysis*/verdict (deferred until Collector B accumulates history).
- Any paid or rate-limited third-party options source (Alpha Vantage, DoltHub, OptionMetrics).
- Loose semis-implied proxies (e.g., using VXN as a stand-in for semiconductor IV).
- The two pre-existing repo lint/a11y issues (out of scope, tracked separately).

## Deliverables checklist

- [ ] `ingest/vol.py` + `VOL_SERIES`/params + `QQQ` in config
- [ ] `ingest/iv_snapshot.py` (Collector B) wired into `update-data.yml`
- [ ] `analysis/vol_premium.py` (H6) + tests
- [ ] `analysis/vol_termstructure.py` (H7) + tests
- [ ] `h6_record` / `h7_record` + `build_signal_records` wiring + tests
- [ ] DuckDB tables: `vol_indices`, `vol_premium`, `vol_termstructure`, `iv_snapshots`
- [ ] Web chart types `vrp_term`, `termstructure_timing` in `SignalCard.svelte`
- [ ] Verify live `data/signals.json` after deploy
