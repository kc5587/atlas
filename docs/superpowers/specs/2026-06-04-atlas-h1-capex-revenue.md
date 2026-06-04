# H1 — Capex → Downstream Revenue (Quarterly)

**Date:** 2026-06-04
**Status:** Design (in depth) — strongest economic prior in the Signal Lab.
**Parent:** `2026-06-04-atlas-signal-lab-roadmap.md`
**Depends on:** H0 (Signal Lab board + `signals.json` surface); Layer 2 SEC
fundamentals (`fundamentals_quarterly`).

---

## 1. Claim, mechanism, verdict space

**Claim:** Upstream **capex growth** leads downstream **revenue growth** by 1–4
quarters along the value chain.

**Mechanism:** real physical lead times — equipment orders → fab capacity →
chip shipments → customer revenue — and the market updates on quarterly guidance,
so the linkage diffuses over quarters rather than instantly. This is the channel
with a genuine *clock*, unlike daily returns (H0).

**Possible verdicts:** Confirmed / Suggestive / Null / Contradicts (revenue leads
capex). The small sample means **Suggestive** is the most likely *good* outcome —
and that is honestly reported, not inflated to Confirmed.

## 2. Why the existing path is insufficient

`analysis/leadlag.py` already computes `fund_capex_rev` rows, but naively:
correlates capex **levels** vs revenue **levels** (dominated by shared
trend/seasonality → spurious), two-sided `|corr|` peak (not the one-sided
hypothesis), no growth transform, no cycle control, no confidence interval, no
restricted FDR family. H1 replaces this with a defensible estimator.

## 3. Estimator

For each eligible edge (upstream `U`, downstream `D`):

1. **Series:** quarterly capex for `U`, quarterly revenue for `D`, point-in-time
   on **filed date** (already how `fundamentals_quarterly` is built).
2. **Stationarity — year-over-year growth.** Fundamentals are seasonal and
   trending; use **YoY growth** (4-quarter difference of logs):
   `g_t = ln(x_t) - ln(x_{t-4})`. This removes seasonality and most trend, giving
   a stationary-ish growth series. (Document the choice; QoQ-with-seasonal-adjust
   is the alternative, rejected for simplicity given sample size.)
3. **Cycle control (the de-beta analog).** Downstream revenue growth partly just
   tracks the whole semiconductor cycle. Control it: regress `D` revenue growth on
   a contemporaneous **cycle factor** — the cross-sectional mean revenue growth of
   the universe (leave-one-out, excluding `D`), and optionally the FRED
   semiconductor IP index growth (`IPG3344S`). Use the **residual** revenue growth
   as the dependent signal. This is the evidence-chain "raw → controlled" step.
4. **One-sided lead search.** Cross-correlate `U` capex growth (lead) vs `D`
   residual revenue growth over quarterly lags **[1, 4]** (hypothesized
   direction). Lag 0 reported as context; negative lags → `contradicts_thesis`
   diagnostic (revenue leads capex), never a confirmation.
5. **Effect size.** At the selected lag, fit the simple regression
   `D_resid_growth_t = a + b · U_capex_growth_{t-lag}` and report slope `b`
   (economic magnitude) and `corr`.

## 4. Validation (sample-appropriate — NO walk-forward)

Quarterly pairs give ~20–40 observations. Walk-forward folds would measure
correlation on a handful of quarters — noise, not validation. Instead:

- **Selection-aware p** over the small lag domain [1,4], single-series stationary
  block bootstrap (block ≈ 2 quarters) on one growth series — same invariant as
  Priority 1 (perturb one series, not the pair).
- **Bootstrap confidence interval** on the slope `b` (block bootstrap, ~2-quarter
  blocks) — the primary honesty device given small `n`.
- **Single chronological holdout** as a *directional check only*: fit on the first
  ~70% of quarters, report sign + magnitude on the last ~30%, with an explicit
  "thin holdout (k quarters)" caveat. Not a pass/fail gate.
- **BH-FDR** over the H1 family (see §5), `FDR_ALPHA = 0.10`.

**Verdict mapping:**
- **Confirmed:** q ≤ 0.10, positive slope, CI excludes 0, holdout sign holds.
- **Suggestive:** positive slope + CI excludes 0, but fails FDR or holdout.
- **Contradicts:** dominant relationship at a negative lag (revenue leads capex).
- **Null:** otherwise.

## 5. Eligible edges & FDR family

Only edges where **both** endpoints are US filers with SEC fundamentals qualify
(ASML/TSM have no CIK → excluded; foreign-filer fundamentals deferred to Layer
2b). Of the 19 directed edges, the eligible subset is those whose upstream node
has capex data and downstream node has revenue data (≈ the edges among the 13
US filers). The H1 FDR family = this eligible subset; its size `m` is computed and
shown on the card. Edges dropped for missing fundamentals are listed as a caveat.

## 6. Components / files

- `analysis/fundamentals_leadlag.py` (new) — `yoy_growth`, `cycle_control`
  (leave-one-out cross-sectional mean + optional IP index), `capex_revenue_edges`
  returning per-edge rows {lag, corr, slope, slope_ci, p_selection, q_value,
  contradicts_thesis, n_quarters, holdout_sign_ok}. Pure; unit-tested with
  synthetic quarterly series (a known capex→revenue lead).
- `analysis/significance.py` — reuse `selection_aware` (lag domain [1,4]); add a
  `bootstrap_slope_ci` helper (or place it here).
- `analysis/signals.py` — emit the H1 `signals.json` record (verdict from §4) and
  per-edge `detail_rows`.
- `analysis/leadlag.py` — replace the naive `_fund_capex_revenue_rows` with the
  hardened path (or write to a separate `fundamentals_leadlag` table consumed by
  `signals.py`); keep `fund_capex_price` rows untouched.
- Web: H1 card + a `capex_revenue_overlay` chart renderer (capex growth vs
  forward revenue growth, lag-aligned), registered in `SignalCard.svelte`.

## 7. Testing (TDD)

- `yoy_growth`: 4-quarter log difference; drops first 4; matches hand-computed.
- `cycle_control`: residual orthogonal to the cycle factor; leave-one-out excludes
  the target.
- `capex_revenue_edges`: a synthetic series with capex leading revenue by 2Q is
  detected at lag 2 with positive slope; a revenue-leads series is flagged
  `contradicts_thesis`; selection-aware p small for the real case, large for
  independent series; slope CI excludes 0 for the strong synthetic case.
- `signals.py`: H1 record verdict mapping (Confirmed/Suggestive/Null/Contradicts)
  from crafted inputs.
- Web: H1 card renders evidence chain + slope CI; overlay chart renders.

## 8. App presentation

H1 card: claim, mechanism, evidence chain `raw corr → cycle-controlled corr →
holdout corr`, stat `slope [CI], q, n quarters`, verdict badge, and the
capex-vs-forward-revenue overlay. Drill-down: per-edge table (lag, slope, q,
n_quarters, verdict). Caveat line always shows `n` quarters and "small-sample:
CIs, no walk-forward."

## 9. Honesty guardrails

- Small `n` stated on the card; CI is the headline, not the point estimate.
- Cycle-controlled correlation shown next to raw, so a reviewer sees how much is
  incremental over the common semiconductor cycle.
- Ex-post universe-selection caveat inherited from the board.
- If the result is Null/Suggestive (likely), present it as such — the rigor is the
  deliverable.
