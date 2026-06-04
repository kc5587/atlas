# H5 — Is Upstream Capex Priced Into Downstream Equity?

**Date:** 2026-06-04
**Status:** Design (in depth) — the thesis capstone of the Signal Lab.
**Parent:** `2026-06-04-atlas-signal-lab-roadmap.md`
**Builds on:** H1 (capex→revenue, Confirmed) and the H0/H1 de-beta + FDR machinery.

---

## 1. Claim, mechanism, verdict (note the inversion)

**Claim:** Upstream capex growth predicts **downstream forward equity returns** —
i.e., the value-chain signal that H1 showed propagates to *revenue* is **not yet
priced into the customer's stock**.

**Mechanism:** if markets under-react to a supplier's capex (a slow, real
leading indicator of downstream demand), the customer's stock should drift after
the capex becomes public. Efficient markets say it's already discounted.

**Verdict vocabulary (inverted vs H1 — state clearly on the card):**
- **Confirmed** = capex *does* predict forward downstream returns → **NOT yet
  priced in** (the alpha claim; the surprising result).
- **Null** = no forward predictability → **priced in** (the efficient-market
  result; the *expected* and still-publishable outcome).
- **Contradicts** = capex predicts *lower* forward returns (over-reaction/reversal).

The most likely honest outcome is **Null / priced-in**. That is a clean,
on-message finding for the board, not a failure.

## 2. The critical methodological point: point-in-time on the FILING date

Capex is only public when the filing is submitted (`filed`, ~40 days after
`period_end`). The forward-return window therefore **must start strictly after
the filing date**, or the test leaks look-ahead and stops being a tradeability
test. This is the defining difference from H1 (which compared two fundamentals on
`period_end`). H5 aligns the capex signal to `filed` and measures forward price
*after* `filed`.

## 3. Estimator

For each eligible cross-edge (upstream `U` → downstream `D`):

1. **Signal:** `U` capex **YoY log-growth** (`yoy_growth`, reused from H1),
   indexed by **filing date** `f_t`.
2. **Target:** `D`'s **forward de-beta'd cumulative return** over the window
   `(f_t, f_t + h]` for **h ∈ {1Q ≈ 63 trading days, 2Q ≈ 126}**. The return is
   the sum of `D`'s daily **M2 residual** returns (market + orthogonalized sector
   removed, reusing `residual_for_spec`).
3. **No-look-ahead de-beta:** `D`'s factor betas are estimated **point-in-time on
   an expanding window up to `f_t`**, then applied to residualize the forward
   slice. The control never uses data from after the window opens.
4. **Horizon selection:** evaluate both horizons; the signed selection-aware
   p-value corrects for searching over the 2 horizons (reuse `selection_aware`
   logic, domain = the horizon set rather than lags).
5. **Effect size:** regress forward residual return on capex growth at the
   selected horizon; report slope + **block-bootstrap CI** (`bootstrap_slope_ci`),
   blocks sized to span overlapping windows.

## 4. Validation (sample-appropriate — NO walk-forward)

~25 quarterly filings per edge → effect sizes + CIs, not walk-forward (same
rationale as H1). Specifics:

- **Overlapping-window dependence:** the 2Q (126-day) forward windows overlap
  across consecutive quarters, inducing autocorrelation. The block bootstrap must
  use blocks ≥ the overlap (≈ 2 quarters) so CIs and the selection-aware null are
  not anti-conservative. State this on the card.
- **BH-FDR** over the eligible-edge family (`FDR_ALPHA = 0.10`), eligible =
  finite slope (degenerate edges excluded, per the H1 review fix).

**Verdict mapping:**
- **Confirmed (not priced in):** q ≤ 0.10, positive slope, expected sign, not
  contradicting.
- **Suggestive:** positive slope + CI excludes 0, but fails FDR.
- **Contradicts:** dominant negative slope (reversal).
- **Null (priced in):** otherwise.

## 5. Eligible edges & family

Cross-edges where `U` has capex filings and `D` has daily returns. ASML/TSM as
**upstream** drop out (no SEC capex); as downstream they have prices but H5 keys
on the upstream capex signal, so edges with ASML/TSM upstream are excluded.
Family = eligible edges; size `m` shown on the card; dropped edges listed as a
caveat.

## 6. Components / files

- `analysis/capex_price.py` (new) — `forward_residual_return(resid_daily, filed,
  horizon_days)`, `capex_price_edge(...)`, `capex_price_edges(fundamentals,
  returns, factors, nodes, edges, *, horizons, iters, seed)`. Reuses
  `yoy_growth`, `residual_for_spec`, `selection_aware`, `bootstrap_slope_ci`,
  `bh_fdr`.
- `analysis/leadlag.py` `run()` — write a `capex_price` table.
- `analysis/signals.py` — `h5_record(rows)` with the inverted verdict vocabulary;
  append to `build_signal_records` when the table exists.
- `web/src/components/SignalCard.svelte` — a `capex_price` chart branch
  (per-edge forward-return-vs-capex slope bars, like H1's overlay) + a one-line
  "Confirmed = not priced in / Null = priced in" legend so the inversion is clear.
- No new Zod fields (reuses the `SignalZ` record shape).

## 7. Testing (TDD)

- `forward_residual_return`: window starts strictly after `filed` (a return on
  `filed` itself is excluded); sums the correct daily residual slice; empty when
  no data after `filed`.
- Point-in-time de-beta: betas for window opening at `f_t` use only data ≤ `f_t`
  (synthetic check that a post-`f_t` shock does not change the beta).
- `capex_price_edge`: a synthetic series where capex growth precedes a downstream
  forward drift is detected with positive slope + small p; an i.i.d. control is
  Null; a reversal is `contradicts`.
- `h5_record`: verdict inversion (forward-predictive → "confirmed/not priced in";
  flat → "null/priced in"); eligible-only `n`; NaN-guarded fields.

## 8. App presentation

H5 card: claim, mechanism, evidence chain (raw forward corr → de-beta'd →
selected horizon), stat (slope [CI], q, n edges, horizon), verdict badge with the
priced-in legend, and per-edge bars. Caveat line: "~N filings/edge; overlapping
forward windows; CIs + FDR, no walk-forward; Confirmed ⇒ not-yet-priced-in."

## 9. Honesty guardrails

- The point-in-time filing alignment is the headline rigor; state it on the card.
- A **Null** ("priced in") is reported plainly as the expected efficient-market
  result — it closes the thesis loop just as well as a Confirmed.
- Inherits the ex-post universe caveat from the board.
- This is observational, not a trading backtest: no costs/turnover claimed (that
  would be a separate Priority-2 step if a Confirmed result warranted it).
