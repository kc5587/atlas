# H2 — Event-Conditioned Drift (Capex Surprise → Downstream Drift)

**Date:** 2026-06-04 (detailed 2026-06-05)
**Status:** Design (in depth)
**Parent:** `2026-06-04-atlas-signal-lab-roadmap.md`
**Builds on:** H5 (filing-date PIT forward returns) and the H0/H1 de-beta machinery.

---

## 1. Claim, mechanism, verdict

**Claim:** An upstream capex **surprise** (the *unexpected* component of capex
growth) predicts downstream forward de-beta'd returns over multiple weeks —
post-announcement under-reaction (PEAD-style).

**Mechanism:** markets price the *expected* part of capex immediately (H5 showed
capex *level/growth* is already in the price), but may under-react to the
*surprise* — the part that deviates from what the company's own trend implied.
Isolating the surprise is the theoretically-correct PEAD test.

**Verdict:** Confirmed = drift exists (under-reaction) / Null = no drift (efficient;
expected given H5) / Contradicts = significant reversal (over-reaction).

**Honest prior:** after H5's "priced in", **Null is the likely outcome.** That is
still a clean, on-message result and sharpens the H5 story ("not even the surprise
component drifts").

## 2. The surprise definition (the key design decision)

**Chosen: a standardized capex-growth surprise (a free SUE-analog).** For upstream
`U`, using capex YoY growth `g_t` (reuse `yoy_growth`), indexed by **filing date**:

```
expected_t = mean(g over the trailing K quarters before t)     # K = 4
sigma_t    = std(g over the trailing K quarters before t)
surprise_t = (g_t - expected_t) / sigma_t                       # standardized, PIT
```

Rationale: it is free, point-in-time (uses only past quarters), and standardizing
makes surprises comparable across companies for pooling. **Rejected alternative:**
the announcement-window return as a surprise proxy — it is price-based and
partly circular with the price-drift target. (Trailing-mean expectation is the
deliberately simple choice over AR(1) given ~25 quarters per name.)

## 3. Estimator (pooled event study)

Different from H5's per-edge correlation: H2 **pools events** across cross-edges
to gain power on the surprise signal.

1. **Events:** for each cross-edge (U→D), each filing date `f_t` is an event with
   standardized surprise `surprise_t` (from U) and target = `D`'s forward
   de-beta'd (M2) cumulative return over `(f_t, f_t + H]`, reusing
   `forward_excess_return`. Horizons **H ∈ {21, 42, 63}** trading days (the
   multi-week PEAD window).
2. **Pooled regression:** across all events, regress forward return on
   `surprise` (one slope = the drift-per-unit-surprise). Report slope + CI.
3. **Sign split:** mean forward return for positive vs negative surprises (drift
   should be directional under under-reaction).
4. **Horizon selection:** selection-aware over the 3 horizons (single-series
   perturbation of the surprise vector; reuse the H5 horizon-selection approach).

## 4. Validation (event-time, NO walk-forward)

- **Block bootstrap by calendar quarter** over events — events overlap in time
  (multiple edges file near each other; forward windows overlap), so resampling
  must be by time block, not i.i.d., or CIs are anti-conservative. This is the
  headline rigor for H2.
- **Period stability:** report the pooled slope on a pre-2021 vs 2021+ split as a
  descriptive robustness check (not a gate).
- **Event count:** ~ (eligible edges) × (~25 quarters) ≈ low hundreds, but the
  *effective* count is much smaller due to time-clustering — state both.
- **BH-FDR / selection-aware** across the horizon set.

**Verdict mapping:**
- **Confirmed:** pooled slope > 0, selection-aware q ≤ 0.10, CI excludes 0.
- **Suggestive:** slope > 0, CI excludes 0, but fails FDR.
- **Contradicts:** *significant* negative pooled slope (q ≤ 0.10 & slope < 0).
- **Null:** otherwise.

(The "contradicts requires significance" rule is carried over from the H5 fix —
a near-zero negative slope is null, not a reversal.)

## 5. Eligibility & family

Cross-edges where `U` has ≥ K+5 capex quarters (to form standardized surprises)
and `D` has daily returns. ASML/TSM excluded as upstream (no capex). The H2
"family" is the **3 horizons** of one pooled test (m = 3 for the selection-aware
correction), not the edges — because H2 pools edges into a single slope.

## 6. Components / files

- `analysis/event_drift.py` (new) — `capex_surprise(fundamentals, ticker, *, k=4)`
  (standardized, filing-indexed), `pooled_events(fundamentals, returns, factors,
  nodes, edges, horizon)` → `(surprise[], forward_return[])`, `event_drift(...)`
  (pooled slope + selection-aware horizon p + sign-split + bootstrap-by-quarter CI).
  Reuses `yoy_growth`, `forward_excess_return`, `bootstrap_slope_ci`,
  `block_resample_one`, `bh_fdr`.
- `analysis/leadlag.py` `run()` — write an `event_drift` (single-row summary +
  per-horizon detail) table.
- `analysis/signals.py` — `h2_record` (significance-gated verdict, sign-split in
  evidence chain).
- `web/src/components/SignalCard.svelte` — `event_drift` chart branch
  (cumulative-abnormal-return-by-surprise-sign bars + pooled slope).

## 7. Testing (TDD)

- `capex_surprise`: standardized, PIT (uses only trailing K quarters), mean≈0/std≈1
  on a stationary synthetic; drops the first K.
- `pooled_events`: forward windows strictly after filing; pools across edges
  correctly; empty-safe.
- `event_drift`: a synthetic where positive surprises precede positive drift is
  detected (slope > 0, small p); an i.i.d. control is Null; a significant reversal
  is `contradicts`; block-by-quarter bootstrap used (not i.i.d.).
- `h2_record`: verdict mapping incl. significance-gated contradicts; sign-split
  fields present; NaN-guarded.

## 8. App presentation

H2 card: claim, mechanism, evidence chain (positive-surprise drift vs
negative-surprise drift → pooled slope), stat (slope [CI], q, n events, horizon),
verdict badge, and per-sign bars. Caveat: "event-clustered; block-bootstrap by
quarter; effective n ≪ event count; observational."

## 9. Honesty guardrails

- The standardized-surprise definition is the key modeling assumption — state it
  on the card.
- Time-clustering handled by quarter-block bootstrap; report effective vs raw n.
- A **Null** sharpens the H5 result and is reported plainly.
- Observational; no costs/turnover (a backtest would only follow a Confirmed).
