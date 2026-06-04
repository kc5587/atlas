# Atlas — Lead/Lag Statistical Hardening (Priority 1)

**Date:** 2026-06-04
**Status:** Design (approved in principle; pending written-spec review)
**Builds on:** `2026-06-02-atlas-value-chain-design.md` (§9 roadmap), Layer 1 price
lead/lag and Layer 2 fundamentals (shipped).
**Audience for the project:** systematic quant research (highest bar); also quant
dev, data science, equity research.

---

## 1. Motivation

The current lead/lag (`analysis/leadlag.py`) is more advanced than a naïve Pearson
scan — it already has a stationary block bootstrap, BH-FDR q-values, and a
two-halves stability flag. But it has three defensibility gaps that a systematic
quant reviewer will flag immediately:

1. **No de-beta.** Cross-correlations run on raw daily log returns, and there is
   no market or sector factor anywhere in the pipeline. For a universe of ~10
   semis + hyperscalers that co-move heavily, a measured "edge" is largely shared
   market/sector beta, not value-chain propagation.
2. **Peak-lag selection bias.** The code selects `argmax|corr|` across lags
   −20…+20, then computes a bootstrap p-value *at that single chosen lag*. The
   null does not account for the max-over-41-lags search, so p-values are
   optimistic.
3. **Crude out-of-sample test.** `_stable_across_halves` only checks that the
   peak-lag *sign* matches across two in-sample halves — no held-out
   measurement, no magnitude, no honest failure reporting.

This document scopes the fix for **Priority 1**: make the price-edge lead/lag
statistically defensible. Priority 2 (economic-significance backtest) and
Priority 3 (Layer 3 "forgotten plays" ranking) are out of scope here.

## 2. Scope

**In scope — full hardening template, applied to the 19 pre-registered directed
value-chain price edges only:**

- Dual-spec de-beta (market-only **and** market + orthogonalized sector).
- Selection-aware significance (max-|corr|-over-lags null).
- Walk-forward (rolling-origin) out-of-sample validation as the **primary** OOS;
  single 70/30 split kept as one illustrative example.
- BH-FDR over the pre-registered family of 19 edges.

**Fast-follow — sample-appropriate variant (NOT this template), deferred:**

- Fundamental scans (`fund_capex_price`, `fund_capex_rev`): de-beta the price
  leg + selection-aware null + BH-FDR, but **no walk-forward**. Quarterly pairs
  have ~20–40 observations; carving rolling test folds would measure correlation
  on a handful of quarters — noise, not validation. Use a full-sample estimate
  plus an explicit "insufficient OOS power (n quarters)" caveat, or a single
  holdout at most. Declining walk-forward here is a *correctness* decision.
- Macro scans: additionally require resolving levels-vs-changes / mixed-frequency
  semantics before any hardening pass. Excluded from Priority 1 entirely.

**Non-goals (Priority 1):**

- No trading backtest, Sharpe, turnover, or transaction-cost modelling (that is
  Priority 2). The OOS here measures *signal stability*, not P&L.
- No new graph nodes or universe expansion (that is Priority 3 / Layer 3).
- No change to the daily ingest cadence or GitHub Pages deploy flow.

## 3. The pre-registered hypothesis family

The 19 directed edges in `value_chain.yml` are *a priori* hypotheses ("upstream
leads downstream"). Restricting the FDR family to these 19 (one selected lag
each, m = 19) is both more powerful and more defensible than an N×N scan. Macro
and fundamental scans are separate declared families with their own m.

**Data-power confirmation (computed 2026-06-04 against `data/atlas.duckdb`):**
all 19 edges have sufficient daily history for a 70/30 split + `MAX_LAG_DAYS`
embargo to leave a real test window.

| Edge group | Overlap (daily obs) | Approx. test window |
|---|---|---|
| 16 edges (full 2010– history) | 4,128 | ~1,218 d |
| 2 edges involving META (2012–) | 3,529 | ~1,038 d |
| 2 edges involving DELL (relisted 2016-08) | 2,461 | ~718 d |

DELL is the shortest series; no edge is thin enough to collapse walk-forward
folds. This will be re-asserted as a guard in code (see §9).

## 4. Component 1 — Factor data ingest

Add factor tickers, kept **separate** from `UNIVERSE` so they are never graph
nodes:

- `SPY` — market.
- `SOXX` — semiconductor sector (maps to stages: equipment, foundry, chips).
  Chosen over SMH: broader, less dominated by NVDA/TSM.
- `IGV` — software/cloud sector (maps to stage: cloud).

Ingested through the existing `ingest/prices.py` path (free via yfinance). A new
config map `FACTOR_TICKERS` and a stage→sector mapping live in `config.py`. A new
dbt model `factor_returns` exposes daily log returns for the factors, parallel to
`returns`.

## 5. Component 2 — Residualization (`analysis/residualize.py`, new)

**Orthogonalized sector factor (must-fix for multicollinearity).** Sector ETFs
are ~0.8+ correlated with the market, so a raw 2-factor OLS yields unstable,
uninterpretable betas. Before the per-name regression, build a *pure* sector
factor:

```
sector_pure_t = resid( SOXX_t ~ α + β·SPY_t )      # and likewise IGV ~ SPY
```

`{SPY, sector_pure}` are then near-orthogonal, giving stable betas and clean
market-vs-sector attribution.

**Two specifications, reported side by side (do not choose one):**

- **M1 (market-only):** `r_i = α + β_mkt·SPY + ε`.
- **M2 (market + sector):** `r_i = α + β_mkt·SPY + β_sec·sector_pure + ε`.

The residual `ε` is the idiosyncratic return that downstream cross-correlation
consumes. Reporting both makes the thesis honest: raw co-movement → what survives
market de-beta → what survives sector de-beta. The collapse or survival under
sector control **is** a headline result (M2 answers a sharper "who leads beyond
common semis beta" question; M1 answers "does the chain co-move with lead/lag").

**Point-in-time betas (no look-ahead).** Betas are estimated on each
walk-forward fold's training portion and held fixed when computing that fold's
test residuals. For the single illustrative split, betas are estimated on the
train window only. Full-sample betas are never used to produce residuals that
feed an OOS measurement.

**Constituent attenuation caveat.** Because our names are ETF constituents, M2
residuals slightly over-remove own-name effect. For heavy constituents (ETF
weight > ~10%, e.g. NVDA in SOXX), provide a **leave-one-out peer-composite**
sector factor (equal-weight mean of same-stage peers excluding the name) as a
robustness variant for those names only. Each name's ETF weight is recorded in
the output caveat.

This module is pure (NumPy/pandas in, residual series out) and unit-tested.

## 6. Component 3 — Selection-aware significance

Replace "bootstrap p at the pre-chosen peak lag" with a null over the **same
search** the observed statistic used:

- Observed statistic: `peak = max_lag |corr_resid(left, right; lag)|` over lags
  −`MAX_LAG_DAYS`…+`MAX_LAG_DAYS`.
- Null: perturb **one** residual series independently so cross-dependence is
  destroyed while each series keeps its own autocorrelation. Recompute the max
  |corr| across all lags each iteration.
- `p_selection = (1 + #{ null_max ≥ peak }) / (iters + 1)`.

**Invariant (must-fix for null correctness) — stated in the module docstring and
asserted by a test:** the resampling perturbs a *single* series, never the pair
jointly. Joint block-bootstrap of the pair preserves the lead/lag being tested
and yields a wrong null.

- **Primary perturbation:** random **circular rotation** of one series
  (preserves each series' full autocorrelation exactly, destroys cross-corr).
- **Cross-check:** independent single-series stationary block bootstrap (reuses
  the existing `stationary_bootstrap_pvalue` block machinery on one series).
- **Test:** the null distribution of cross-corr is centered on ~0 (mean ≈ 0
  within tolerance), confirming cross-dependence is broken.

## 7. Component 4 — Out-of-sample validation

**Primary: rolling-origin walk-forward.** K folds over the daily history. Each
fold:

1. Estimate factor betas + select peak lag and sign on the fold's training slice
   (using residuals from train-only betas).
2. Apply a `MAX_LAG_DAYS` embargo gap at the train/test boundary to prevent lag
   leakage.
3. Measure `corr_resid` at the **fixed** selected lag on the fold's test slice.

Report the **distribution** of `corr_test` across folds per edge: median, IQR,
and the sign-retention rate (fraction of folds whose test corr keeps the train
sign). This is the honest OOS signal-stability measure.

**Illustrative: single 70/30 chronological split.** Kept as one labeled example
per edge (`corr_train`, `corr_test`, sign retained, shrinkage) for narrative
clarity — explicitly secondary to the walk-forward distribution.

A pair is **"confirmed"** only if it passes BH-FDR on `p_selection` (q ≤ 0.10)
**and** retains its train sign in a majority of walk-forward folds
(`oos_sign_rate ≥ 0.6`, configurable). Both thresholds live in `config.py`.
Failures are reported, not hidden.

## 8. Component 5 — FDR family & output

BH-FDR (`FDR_ALPHA = 0.10`) applied **within** the declared 19-edge family
(m = 19), on `p_selection`. The output records `m` and the family label so the
multiple-testing scope is explicit and auditable.

**Extended `leadlag` schema** (per edge × {M1, M2}):

| Field | Meaning |
|---|---|
| `factor_model` | `"M1_market"` or `"M2_market_sector"` |
| `corr_raw` | pre-residual Pearson corr at selected lag (for contrast) |
| `corr_resid` | residual corr at selected lag |
| `lag` | selected lag (days; positive ⇒ left leads right) |
| `p_selection` | selection-aware (max-over-lags) p-value |
| `q_value` | BH-FDR q within the 19-edge family |
| `oos_corr_median` | median `corr_test` across walk-forward folds |
| `oos_corr_iqr` | IQR of `corr_test` across folds |
| `oos_sign_rate` | fraction of folds retaining train sign |
| `n_folds` | walk-forward fold count |
| `split_corr_train` / `split_corr_test` | single 70/30 illustrative values |
| `survives_sector_control` | true if confirmed under M2, not just M1 |
| `n_eff` | effective sample size used |

Existing consumers (web `export_data.py`, Zod schema in `web/src/lib/types.ts`,
`leadlag.json`) are updated additively; the map labels edges by confirmed status
and can contrast raw vs residual corr so the data-story stays honest:
*"N of 19 edges survive de-beta + FDR + OOS; most do not."*

## 9. Reproducibility & data-quality (quant-dev angle)

These feed the planned `ARCHITECTURE.md`:

- **Determinism:** all bootstrap/rotation uses `RANDOM_SEED`; identical inputs ⇒
  identical `leadlag` table.
- **Idempotency:** re-running the analysis on unchanged marts reproduces row-for-
  row identical output (verified by a hash/row-count check).
- **Data-quality tests (new):**
  - factor coverage: every factor ticker has daily returns spanning the universe
    window;
  - orthogonality: `corr(residual, factor) ≈ 0` per name/spec (tolerance-bounded);
  - null sanity: bootstrap null cross-corr mean ≈ 0;
  - power guard: every edge's post-split/embargo test window ≥ a configured
    minimum, else the edge is flagged (not silently fit).

## 10. Module / file plan

- `config.py` — add `FACTOR_TICKERS`, stage→sector map, walk-forward params
  (`OOS_FOLDS`, `OOS_TEST_FRAC`, `OOS_EMBARGO_DAYS = MAX_LAG_DAYS`), leave-one-out
  weight threshold.
- `ingest/prices.py` — ingest factor tickers (no graph coupling).
- `dbt_project/models/marts/factor_returns.sql` — factor daily log returns.
- `analysis/residualize.py` *(new)* — orthogonalized sector factor, per-name M1/M2
  OLS, point-in-time residuals, leave-one-out variant. Pure + unit-tested.
- `analysis/significance.py` *(new)* — max-over-lags selection-aware p (circular
  rotation + single-series block bootstrap), single-series-perturbation invariant.
  Pure + unit-tested.
- `analysis/oos.py` *(new)* — rolling-origin walk-forward + single-split
  illustrative; returns per-edge OOS distribution. Pure + unit-tested.
- `analysis/leadlag.py` — orchestrate: residualize → cross-correlate residuals →
  selection-aware p → walk-forward OOS → BH-FDR over the 19-edge family → extended
  rows. The macro and fundamental scans remain on their current path this pass,
  unchanged (hardened later via the sample-appropriate variant).
- `web/export_data.py`, `web/src/lib/types.ts`, web UI — additive schema + edge
  labeling.

Many small, focused modules (each <300 lines), high cohesion, testable in
isolation — consistent with the repo's existing analysis structure.

## 11. Testing plan (TDD)

- `residualize`: orthogonality of `sector_pure` vs SPY; residual orthogonal to
  factors; train-only betas never see test data; leave-one-out excludes the name.
- `significance`: single-series-perturbation invariant; null cross-corr centered
  on 0; p monotone in peak magnitude; deterministic under seed.
- `oos`: embargo removes the boundary window; fold count/sizes correct; sign-
  retention computed correctly on a synthetic lead/lag series.
- `leadlag` integration: extended schema present; FDR family m = 19; M1 and M2
  both emitted; power guard flags a deliberately-short synthetic edge.
- Data-quality tests wired into the dbt/make pipeline.

Coverage target ≥ 80% on the new analysis modules, per repo testing standard.

## 12. Honesty framing (README / interview narrative)

- "Walk-forward OOS applied only where the sample supports it; explicitly
  declined on quarterly fundamentals because the OOS power isn't there."
- "Both market-only and sector-controlled specs reported; the result is what
  survives sector de-beta, not a single cherry-picked number."
- "Pre-registered the 19 directed edges as the hypothesis family before testing."

## 13. Deferred (explicitly not Priority 1)

- Fundamental scans → sample-appropriate hardening (de-beta price leg +
  selection-aware null + FDR + full-sample/holdout caveat; no walk-forward).
- Macro scans → resolve levels-vs-changes / mixed-frequency first.
- Priority 2 backtest (Sharpe/turnover/cost sensitivity) on the strongest
  surviving edge — separate spec; may reuse the walk-forward harness.
- Priority 3 Layer 3 "forgotten plays" ranking estimator — separate spec.
