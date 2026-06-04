# H2 — Event-Conditioned Drift (Outline)

**Date:** 2026-06-04
**Status:** Design **outline** — to be detailed before implementation (after H3).
**Parent:** `2026-06-04-atlas-signal-lab-roadmap.md`
**Sequence:** 4th. Needs an earnings-date / surprise source (new data step).

> Outline rationale: needs a new free data source (earnings dates); design the
> surprise definition and data plumbing once the board + H1 patterns are proven.

---

## Claim & mechanism

**Claim:** An **upstream capex/guidance surprise** predicts **downstream**
returns over the following 2–6 weeks.

**Mechanism:** post-earnings-announcement drift (PEAD) — persistent
under-reaction to earnings information — is one of the most durable anomalies,
precisely because the adjustment is slow. Conditioning on an information *event*
plus a multi-week horizon is where predictability concentrates.

## Estimator (to finalize)

1. **Define the event & surprise** for upstream names: capex (or revenue/EPS)
   actual vs an expectation proxy. With free data, the consensus is hard to get;
   candidate proxies: deviation from trailing trend / a simple AR forecast, or
   the immediate announcement-window return as a surprise proxy.
2. **Event study:** for each upstream event, measure the **downstream** cumulative
   abnormal return (de-beta'd, M2 residuals) over windows [+1d, +10d], [+1d,
   +21d], [+1d, +42d].
3. Aggregate across events; split positive vs negative surprises (drift should be
   signed).

## Validation

Event-time aggregation with **bootstrap CIs across events** (events are the
sampling unit). Period split (e.g., pre-2021 vs post) for stability. Selection
across the window grid is FDR-controlled.

**Verdict mapping:** Confirmed if signed drift is significant and stable across
periods; Suggestive if right sign but CI marginal / period-unstable; Null
otherwise; Contradicts if the drift reverses (over-reaction).

## Data (new)

Free earnings dates: SEC 8-K/10-Q filing dates (already retrievable via EDGAR — we
have the filer CIKs), or a free calendar source. Surprise from EDGAR fundamentals
we already ingest. No paid consensus feed.

## App presentation

Card with the **average cumulative-abnormal-return curve** around the event (with
confidence band), split by surprise sign; stat = drift at +21d [CI], n events.

## Open questions (resolve before implementation)

- Best free surprise proxy without a consensus feed (trend-deviation vs
  announcement-return proxy) — materially affects power and interpretation.
- Event count: ~13 filers × ~40 quarters ≈ few hundred events, but overlapping
  windows induce dependence → bootstrap by event with care.
- Whether to study upstream-event → downstream-return only, or also own-name PEAD
  as a sanity benchmark.

## Honesty guardrails

- Surprise-proxy choice stated explicitly (it is the main modeling assumption).
- Overlapping-window dependence handled in the bootstrap; n events on the card.
