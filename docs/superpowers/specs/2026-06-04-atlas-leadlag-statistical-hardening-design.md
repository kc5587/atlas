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
- One-sided (directional) selection-aware significance over positive lags, with
  wrong-direction peaks bucketed as contradicting the thesis.
- Anchored/expanding walk-forward out-of-sample validation as the **primary** OOS;
  single 70/30 split kept as one illustrative example.
- BH-FDR applied per spec over the pre-registered family of 19 edges (m = 19 each).

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

**Data-power confirmation (computed 2026-06-04 against `data/atlas.duckdb`),
against the *primary* walk-forward scheme — not the single split.** Scheme:
anchored/expanding, fixed 252-day (1-year) test window stepped by 252 days,
initial train ≈ 50% of the pair's overlap, `MAX_LAG_DAYS` (20 d) embargo at each
train/test boundary. Per-fold usable test window is therefore a constant
252 − 20 = **232 trading days (~11 months) for every fold, regardless of series
length** — short series simply yield fewer folds, not thinner ones.

| Edge group | Overlap (daily obs) | Walk-forward folds | Per-fold usable test |
|---|---|---|---|
| 16 edges (full 2010– history) | 4,128 | 8 | 232 d |
| 2 edges involving META (2012–) | 3,529 | 7 | 232 d |
| 2 edges involving DELL (relisted 2016-08) | 2,461 | 4 | 232 d |

DELL is the shortest series and the thinnest at **4 folds**. Min-folds guard:
require ≥ 3 folds/edge; all 19 pass. The single 70/30 split (illustrative only)
leaves a much larger one-shot test window (~718 d for DELL up to ~1,218 d), but
that is secondary — power is governed by the walk-forward folds above.

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

**The SOXX~SPY (and IGV~SPY) orthogonalization is itself fit train-only, per
fold** — consistent with the no-look-ahead claim for the per-name betas. The
factor-on-factor beta is empirically very stable, so per-fold refitting changes
`sector_pure` only marginally, but fitting it on the full sample would leak a
(small) look-ahead into every fold's factor, so we do not.

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

### 6.1 Directional pre-registration (one-sided)

The 19 edges are pre-registered as **directional**: upstream (the edge's
`from_id`, mapped to `left`) leads downstream (`to_id`, `right`). In the
`cross_correlations` convention, *positive lag ⇒ left leads right*, so the
hypothesized region is **positive lags only**.

- **Search domain = lags ∈ [1, `MAX_LAG_DAYS`]** (the hypothesized direction).
  This is the truly pre-registered, one-sided test: it is more powerful, and the
  selection-aware null's maximum is taken over ~20 lags, not 41.
- **Lag 0 (contemporaneous)** is computed and reported as context, but is not a
  "lead" and is excluded from the lead statistic.
- **Negative lags (downstream leads upstream)** are computed but routed to a
  distinct **`contradicts_thesis`** diagnostic — never counted as a confirmation
  and never entered into the FDR family. An edge whose strongest relationship is
  at a negative lag *contradicts* the pre-registered hypothesis; reporting it as a
  "significant edge" (as the current pipeline would) is exactly the conflation
  this fixes.

Confirmation additionally requires the **economically-expected sign** (positive
residual co-movement at a positive lag — complementary propagation up the chain).
A negative correlation at a positive lag is reported as an `inverse_lead`
anomaly, not a clean confirmation. (§8 ties sign + direction into the
confirmation rule.)

### 6.2 Selection-aware null over the search domain

Replace "bootstrap p at the pre-chosen peak lag" with a null over the **same
one-sided search** the observed statistic used:

- Observed statistic — **signed** to match the directional *and* sign hypothesis
  exactly: `peak = max (+corr_resid(left, right; lag))` over lags
  ∈ [1, `MAX_LAG_DAYS`]. Using signed `+corr` (not `|corr|`) means the null is
  calibrated precisely to the "positive lead correlation" hypothesis — negative
  correlations don't inflate `null_max`, so the test is neither anti-conservative
  nor needlessly conservative. An `inverse_lead` edge (negative corr at a positive
  lag) simply produces a low signed peak and fails significance, which is correct;
  it is still surfaced descriptively (§6.1).
- Null: perturb **one** residual series independently so cross-dependence is
  destroyed while each series keeps its own autocorrelation. Recompute the signed
  max `+corr` across the same positive-lag domain each iteration.
- `p_selection = (1 + #{ null_max ≥ peak }) / (iters + 1)`.

**Block length (the one null parameter a reviewer can attack).** The stationary
bootstrap's expected block length is **not** hardcoded; it is set **per series**
by **Politis–White (2004) automatic block-length selection** (the standard
data-driven rule, tied to the residual's decorrelation time). Too-short blocks
destroy residual autocorrelation (anti-conservative p); too-long blocks leave too
few effective resamples. The chosen block length per series is recorded in the
output and asserted in the data-quality checks (§9). The existing
`BOOTSTRAP_BLOCK = 20` becomes a fallback only.

**Invariant (must-fix for null correctness) — stated in the module docstring and
asserted by a test:** the resampling perturbs a *single* series, never the pair
jointly. Joint block-bootstrap of the pair preserves the lead/lag being tested
and yields a wrong null.

- **Primary perturbation:** independent **single-series stationary block
  bootstrap** (reuses the existing `stationary_bootstrap_pvalue` block machinery
  on one series). Preferred as primary because it produces many genuinely distinct
  resamples.
- **Cross-check:** random **circular rotation** of one series — preserves each
  series' autocorrelation exactly, but yields only ~T highly-dependent distinct
  shifts plus a wrap-around seam, so it is a robustness cross-check, not the
  primary null. This caveat is noted in the module.
- **Test:** the null distribution of cross-corr is centered on ~0 (mean ≈ 0
  within tolerance), confirming cross-dependence is broken.

## 7. Component 4 — Out-of-sample validation

**Primary: anchored/expanding walk-forward (rolling origin).** Scheme fixed in
§3: training window is *anchored* (grows from the start, never slides off old
data — maximizes beta stability in late folds), fixed 252-day test windows
stepped by 252 days, `MAX_LAG_DAYS` embargo at each boundary. Each fold:

1. On the fold's training slice: fit the SOXX~SPY orthogonalization, fit per-name
   M1/M2 betas, residualize, and select the peak lag + sign over lags
   [1, `MAX_LAG_DAYS`].
2. Embargo `MAX_LAG_DAYS` days at the train/test boundary.
3. Residualize the test slice with the train-fit betas and measure `corr_resid`
   at the **fixed** selected lag.

Report the **distribution** of `corr_test` across folds per edge — median, IQR,
and sign-retention rate — together with **per-fold date ranges**. The date ranges
make walk-forward double as a **regime-robustness** check: folds span COVID
(2020), the 2022 drawdown, and the 2023+ AI boom, so a signal that holds across
folds is demonstrably not just an artifact of the 2023+ regime. This is a strong
narrative point.

**Illustrative: single 70/30 chronological split.** One labeled example per edge
(`corr_train`, `corr_test`, sign retained, shrinkage) for narrative clarity —
explicitly secondary to the walk-forward distribution.

**On interpreting `oos_sign_rate` (your reviewer's caution).** Walk-forward folds
are **not independent** — anchored training windows overlap and daily returns are
autocorrelated — so `oos_sign_rate` must **not** be read as a Bernoulli success
probability or converted into a p-value. The inferential gate is BH-FDR on
`p_selection`; `oos_sign_rate` and the `corr_test` distribution are reported
**descriptively** as supporting stability evidence. Fold count `K` is reported
per edge (4–8 here). The "confirmed" label (§8) uses FDR as the gate plus a
descriptive stability floor, explicitly flagged as a heuristic, not a second
significance test.

## 8. Component 5 — FDR family & output

BH-FDR (`FDR_ALPHA = 0.10`) applied on `p_selection` **within each spec
separately** — m = 19 for M1 and m = 19 for M2, **not** pooled into m = 38. This
is deliberate: M1 and M2 answer *different questions* ("does the chain co-move
with a lead?" vs "who leads beyond common sector beta?"), so they are distinct
hypothesis families, each pre-registered over the same 19 directed edges. The
output records `m` and the family label per spec so the multiple-testing scope is
explicit and auditable.

**Confirmation rule (ties together §6.1, §7, §8).** Within a spec, an edge is
`confirmed` iff: (a) `q_value ≤ 0.10`; (b) the peak lies in the hypothesized
direction (positive lag — guaranteed by the one-sided search domain); (c) the
residual correlation has the economically-expected positive sign; and (d) it
clears the descriptive stability floor (`oos_sign_rate ≥ 0.6`, a flagged
heuristic, not an independent significance test). Edges failing (b)/(c) are
surfaced as `contradicts_thesis` / `inverse_lead`; edges failing only (d) are
reported as "significant in-sample, unstable OOS." Nothing is hidden.

**Extended `leadlag` schema** (per edge × {M1, M2}):

| Field | Meaning |
|---|---|
| `factor_model` | `"M1_market"` or `"M2_market_sector"` |
| `m` | hypothesis count for this spec's FDR family (= 19) |
| `corr_raw` | pre-residual Pearson corr at selected lag (for contrast) |
| `corr_resid` | residual corr at selected lag |
| `lag` | selected lag (days; in [1, `MAX_LAG_DAYS`], positive ⇒ left leads right) |
| `corr_contemporaneous` | residual corr at lag 0 (context, not a lead) |
| `p_selection` | selection-aware, signed max-over-positive-lags p-value (full-sample) |
| `q_value` | BH-FDR q within this spec's 19-edge family (full-sample) |
| `block_len` | Politis–White block length used for this series' null |
| `oos_corr_median` | median `corr_test` across walk-forward folds |
| `oos_corr_iqr` | IQR of `corr_test` across folds |
| `oos_sign_rate` | fraction of folds retaining train sign (descriptive) |
| `n_folds` | walk-forward fold count `K` (4–8 here) |
| `fold_date_ranges` | per-fold test-window date ranges (regime narrative) |
| `split_corr_train` / `split_corr_test` | single 70/30 illustrative values |
| `best_neg_lag_corr` | strongest corr in the negative-lag (contradicting) region |
| `contradicts_thesis` | true if the dominant relationship is at a negative lag |
| `inverse_lead` | true if positive-lag peak has the wrong (negative) sign |
| `confirmed` | passes the §8 confirmation rule for this spec |
| `survives_sector_control` | confirmed under M2, not just M1 |
| `n_eff` | effective sample size: `n / VIF`, where the variance-inflation factor accounts for residual autocorrelation (≈ `n` for near-white daily residuals) |

**Top-line vs OOS lags (disambiguation).** The top-line fields `lag`,
`p_selection`, `q_value`, `corr_resid` are the **full-sample, in-sample** statistic
(the inferential gate). The walk-forward OOS (§7) **reselects the peak lag per
fold** on each fold's train slice; `oos_corr_*` / `oos_sign_rate` summarize those
per-fold-reselected lags. The two are deliberately distinct — one fixed lag does
not drive both.

Existing consumers (web `export_data.py`, Zod schema in `web/src/lib/types.ts`,
`leadlag.json`) are updated additively; the map labels edges by confirmed status
and can contrast raw vs residual corr so the data-story stays honest:
*"N of 19 edges survive de-beta + FDR + OOS; most do not."*

## 9. Reproducibility & data-quality (quant-dev angle)

These feed the planned `ARCHITECTURE.md`:

- **Determinism:** all bootstrap/rotation uses `RANDOM_SEED`; identical inputs ⇒
  identical `leadlag` table. The reproducibility claim is anchored to the
  **frozen atomic Parquet snapshot**, not to yfinance — yfinance silently
  restates/adjusts history, so "identical inputs" means the pinned `data/raw`
  Parquet, which is the immutable input of record. The analysis is a pure
  function of that snapshot + seed.
- **Idempotency:** re-running the analysis on the unchanged snapshot reproduces
  row-for-row identical output (verified by a hash/row-count check).
- **Data-quality tests (new):**
  - factor coverage: every factor ticker has daily returns spanning the universe
    window;
  - orthogonality: `corr(residual, factor) ≈ 0` per name/spec (tolerance-bounded);
  - null sanity: bootstrap null cross-corr mean ≈ 0;
  - block length: Politis–White block length is finite, ≥ 1, and within a sane
    bound per series (else fall back to `BOOTSTRAP_BLOCK` and flag);
  - power guard: every edge's post-split/embargo test window ≥ a configured
    minimum, else the edge is flagged (not silently fit).

## 10. Module / file plan

- `config.py` — add `FACTOR_TICKERS`, stage→sector map; lag-search domain
  `LAG_MIN = 1`, `LAG_MAX = MAX_LAG_DAYS` (one-sided); walk-forward params
  `OOS_TEST_DAYS = 252`, `OOS_STEP_DAYS = 252`, `OOS_INIT_TRAIN_FRAC = 0.5`,
  `OOS_EMBARGO_DAYS = MAX_LAG_DAYS`, `OOS_MIN_FOLDS = 3`; `OOS_SIGN_RATE_FLOOR =
  0.6` (descriptive heuristic); `LEAVE_ONE_OUT_WEIGHT = 0.10`.
- `ingest/prices.py` — ingest factor tickers (no graph coupling).
- `dbt_project/models/marts/factor_returns.sql` — factor daily log returns.
- `analysis/residualize.py` *(new)* — orthogonalized sector factor, per-name M1/M2
  OLS, point-in-time residuals, leave-one-out variant. Pure + unit-tested.
- `analysis/significance.py` *(new)* — one-sided (positive-lag) max-over-lags
  selection-aware p; single-series stationary block bootstrap (primary) +
  circular rotation (cross-check); single-series-perturbation invariant;
  negative-lag `contradicts_thesis` diagnostic. Pure + unit-tested.
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
  on 0; signed one-sided statistic (negative-corr-at-positive-lag → low signed
  peak → `inverse_lead`, not significant); one-sided search ignores negative lags;
  a synthetic downstream-leads series is bucketed `contradicts_thesis`, not
  confirmed; Politis–White block length is finite/bounded with fallback on
  degenerate input; p monotone in peak magnitude; deterministic under seed.
- `oos`: anchored expanding folds with fixed 252-d test windows; embargo removes
  the boundary window; per-fold train-only orthogonalization (no full-sample
  leak); `OOS_MIN_FOLDS` guard flags a deliberately-short synthetic edge; sign-
  retention computed correctly on a synthetic lead/lag series.
- `leadlag` integration: extended schema present; FDR applied per-spec with
  m = 19 each (not pooled to 38); M1 and M2 both emitted; confirmation rule
  enforces direction + expected sign; `inverse_lead` flagged.
- Data-quality tests wired into the dbt/make pipeline.

Coverage target ≥ 80% on the new analysis modules, per repo testing standard.

## 12. Honesty framing (README / interview narrative)

- "Walk-forward OOS applied only where the sample supports it; explicitly
  declined on quarterly fundamentals because the OOS power isn't there."
- "Both market-only and sector-controlled specs reported; the result is what
  survives sector de-beta, not a single cherry-picked number."
- "Pre-registered the 19 directed edges as the hypothesis family before testing."
- "Tested the hypothesis I actually registered: a one-sided 'upstream leads
  downstream' search, and reported edges where downstream leads as
  *contradicting* the thesis rather than as confirmations."
- "Walk-forward folds span COVID, the 2022 drawdown, and the 2023+ AI boom —
  signals that hold across folds aren't just the recent-regime artifact."

**Known limitations (state these first, before a reviewer does):**

- **Ex-post universe/value-chain selection (the deepest limitation).** The
  universe and the 19 edges were specified *now*, knowing the AI boom happened.
  No amount of per-edge de-beta fixes that the chain itself is defined ex-post:
  *"This tests propagation **given** the chain, not the ex-ante discoverability of
  it. The walk-forward OOS mitigates regime-fitting on the signal, but not
  selection of the universe."* Naming this is a strength — an interviewer thinks
  it within 30 seconds; saying it first separates "ran statistics" from
  "understands what the statistics can't claim."
- **Cross-family FWER.** Running M1 and M2 as two families each controlled at
  FDR 0.10 means the document-wide false-confirmation rate exceeds 0.10. This is
  defensible because the families are pre-registered a priori and answer
  different questions — but it is noted here as a known limitation rather than
  left for a reviewer to raise.

## 13. Deferred (explicitly not Priority 1)

- Fundamental scans → sample-appropriate hardening (de-beta price leg +
  selection-aware null + FDR + full-sample/holdout caveat; no walk-forward).
- Macro scans → resolve levels-vs-changes / mixed-frequency first.
- Priority 2 backtest (Sharpe/turnover/cost sensitivity) on the strongest
  surviving edge — separate spec; may reuse the walk-forward harness.
- Priority 3 Layer 3 "forgotten plays" ranking estimator — separate spec.
