# H3 — Cross-Sectional Residual Structure (Outline)

**Date:** 2026-06-04
**Status:** Design **outline** — to be detailed before implementation (after H1).
**Parent:** `2026-06-04-atlas-signal-lab-roadmap.md`
**Sequence:** 3rd (after H0, H1). Reuses the de-beta'd residuals from Priority 1.

> Outline rationale: the final design should be informed by H1's findings and the
> realized board ergonomics. Mechanism, estimator, and validation are fixed here;
> parameter choices (lookback, rebalance) are finalized at implementation.

---

## Claim & mechanism

**Claim:** The *cross-section* of de-beta'd value-chain residuals has exploitable
structure — even though pairwise time-series lead/lag (H0) does not.

**Mechanism:** cross-sectional momentum and short-horizon reversal are among the
most robust equity anomalies; they survive where pairwise correlations don't
because they aggregate weak per-name signals into a diversified spread. We already
produce the residuals (market/sector-removed), so this reframes the dead
time-series question into a cross-sectional one.

## Estimator (to finalize at implementation)

Two sub-tests, both on M2 (sector-controlled) daily residuals:

1. **Cross-sectional momentum/reversal:** each rebalance, rank names by trailing
   residual return over lookback `L` (candidates: 5, 21, 63 d); form a long-short
   (top minus bottom) portfolio held `H` days; measure forward residual return.
2. **Stage-spread mean-reversion:** construct stage composites (equipment,
   foundry, chips, cloud) from residuals; test whether stage-vs-stage spreads
   mean-revert (estimate half-life via AR(1)) and whether a spread-reversion rule
   has positive expectancy.

## Validation

Daily panel → **walk-forward IS viable** (unlike H1). Anchored walk-forward;
report out-of-sample **Sharpe**, **turnover**, and net-of-cost Sharpe under a
simple per-side cost assumption (e.g., 5–10 bps). FDR across the {L, H} grid
searched (selection-aware — the grid is a multiple-comparison surface).

**Verdict mapping:** Confirmed if OOS net Sharpe is positive and stable across
folds after cost; Suggestive if gross positive but cost/instability kills it;
Null otherwise.

## App presentation

Card with a small **long-short equity curve** (OOS) + a stage-spread time series;
stat = OOS Sharpe [CI], turnover, net-of-cost Sharpe.

## Open questions (resolve before implementation)

- Universe is only ~13–15 names → cross-sectional breadth is thin; is the
  long-short too concentrated to be meaningful? (Likely a key caveat / possible
  Null driver.)
- Rebalance frequency vs turnover/cost trade-off.
- Whether to include the sector ETFs as additional cross-sectional members.

## Honesty guardrails

- Thin universe stated prominently; report turnover and net-of-cost, not just
  gross. Small-N cross-section is the main reason this could be Null.
