# H4 — Macro Cycle → Sector (Outline)

**Date:** 2026-06-04
**Status:** Design **outline** — to be detailed before implementation (last).
**Parent:** `2026-06-04-atlas-signal-lab-roadmap.md`
**Sequence:** 5th (last). Hardens the existing un-hardened macro scan.

> Outline rationale: lowest economic prior, so specced last; reuses the existing
> macro scan plumbing in `analysis/leadlag.py`.

---

## Claim & mechanism

**Claim:** The semiconductor industrial cycle (FRED `IPG3344S`) and rates
(`DGS10`) lead the sector / value-chain stages at **monthly** horizon.

**Mechanism:** a slow cross-frequency channel — the physical semi cycle leads
company performance/sentiment; long-duration tech valuations respond to rates.
Slower than daily, so less arbitraged, but macro→equity links are notoriously
noisy → lower prior.

## Estimator (to finalize)

1. **Resolve levels-vs-changes / mixed-frequency first** (the open decision the
   Priority 1 spec deferred): macro at native frequency, first-differenced for
   stationarity (`IPG3344S` MoM growth; `DGS10` level change); returns aggregated
   to monthly.
2. Cross-correlate monthly macro changes (lead) vs forward monthly **sector /
   stage** residual returns over lags [1, 12] months, one-sided where a
   directional prior exists.
3. Apply the Priority 1 hardening: de-beta returns (M2), selection-aware null,
   BH-FDR over the macro family.

## Validation

Monthly horizon → more observations than fundamentals, fewer than daily.
**Monthly walk-forward** is viable (fewer folds); report OOS sign-retention +
correlation distribution. FDR over the macro-series × stage family.

**Verdict mapping:** Confirmed if a macro→stage lead survives FDR + monthly OOS;
Suggestive if right sign, marginal; Null otherwise.

## Data

FRED `IPG3344S`, `DGS10`, `DFF` — already ingested (`macro_daily`).

## App presentation

Card with a **macro-indicator vs sector overlay** and a lead annotation; stat =
peak lag (months), corr, q, OOS sign-rate.

## Open questions (resolve before implementation)

- Levels vs changes vs growth for each series (rates differ from IP index).
- Stage aggregation: per-stage composite vs whole-sector.
- Whether monthly sample (~15 years ≈ 180 months) gives enough OOS folds at
  12-month max lag.

## Honesty guardrails

- Macro→equity noise stated; lowest-prior hypothesis, reported as such.
- Levels/changes choice made explicit (the main stationarity assumption).
