# Atlas Signal Lab — Program Roadmap

**Date:** 2026-06-04
**Status:** Design (program-level; individual hypothesis specs link from here)
**Builds on:** `2026-06-02-atlas-value-chain-design.md`, Layer 2 fundamentals,
and `2026-06-04-atlas-leadlag-statistical-hardening-design.md` (Priority 1).
**Audience:** systematic quant research (highest bar); also quant dev, data
science, equity research.

---

## 1. Why this exists

Priority 1 hardening produced a clean, honest result: **daily price→price
lead/lag across the value chain is shared market/sector beta — 0 of 19 edges
survive de-beta + selection-aware FDR + walk-forward OOS** (contemporaneous
co-movement collapses 0.14 → 0.04 once the semiconductor sector is removed).

That is the *right* finding, not a failure — but it tells us where **not** to
look. The Signal Lab reorients the search using one principle:

> **Predictability survives where information diffuses slowly and arbitrage is
> costly.** Move along two axes away from daily price→price: a **slower horizon**
> (quarters, multi-week event windows) and **harder-to-arbitrage information**
> (fundamentals, surprises, cross-sectional structure).

The Signal Lab is the app surface + the research program that tests a small set
of economically-motivated hypotheses this way, and **shows every result —
including nulls — with its full evidence chain.**

## 2. The credibility thesis

For a quant audience, a confident **Null** with rigor behind it is more credible
than an unexplained green light. The Signal Lab makes the *method* the product:
each hypothesis is shown as `Claim → Mechanism → Evidence chain → Verdict`, so a
reviewer sees judgment about *what the statistics can and cannot claim*. "I
tested the obvious thing, proved it's beta, and moved to where the economics have
a clock" is the narrative.

## 3. Shared app surface — the Signal Lab board

A new view in the Svelte app (mode toggle alongside Story / Explore), rendered
from a single static JSON (`signals.json`). One **hypothesis card** per
hypothesis:

```
┌─────────────────────────────────────────────────────────┐
│ H1  Capex → downstream revenue            [ SUGGESTIVE ] │
│ Claim:     Upstream capex leads downstream revenue 1–4Q   │
│ Mechanism: Real lead times; quarterly guidance → slow      │
│ Evidence:  raw 0.41 → de-beta'd 0.33 → holdout 0.28        │
│ Stat:      slope 0.6 [0.2, 1.0]  ·  q=0.04  ·  n=34Q       │
│ [ ── chart: capex vs forward revenue overlay ── ]          │
│ Caveat:    ~34 quarters → CIs, no walk-forward             │
└─────────────────────────────────────────────────────────┘
```

### Verdict taxonomy (shared, fixed vocabulary)

| Badge | Meaning |
|---|---|
| **Confirmed** | Passes the hypothesis's pre-registered inferential gate (FDR and/or OOS as the sample allows) with the expected sign/direction. |
| **Suggestive** | Right sign + economically meaningful effect size, but does not clear the inferential gate (e.g. small-sample CI overlaps 0, or fails OOS). |
| **Null** | No effect beyond controls (the H0 result is the canonical example). |
| **Contradicts** | Effect is real but in the *opposite* direction to the hypothesis. |

Every badge links to the numbers; nothing is asserted without the stat shown.

### Evidence-chain data model (shared `signals.json` schema)

Each hypothesis emits one record:

```jsonc
{
  "id": "H1",
  "title": "Capex → downstream revenue",
  "claim": "Upstream capex leads downstream revenue by 1–4 quarters",
  "mechanism": "Real lead times; markets update on quarterly guidance",
  "horizon": "quarterly",
  "verdict": "suggestive",                 // confirmed | suggestive | null | contradicts
  "evidence_chain": [                        // ordered raw → controlled → validated
    {"stage": "raw",        "metric": "corr", "value": 0.41},
    {"stage": "de-beta'd",  "metric": "corr", "value": 0.33},
    {"stage": "holdout",    "metric": "corr", "value": 0.28}
  ],
  "stat": {"name": "slope", "value": 0.6, "ci": [0.2, 1.0], "q_value": 0.04, "n": 34},
  "caveats": ["~34 quarterly observations → CIs, no walk-forward"],
  "chart": {"type": "overlay", "ref": "h1_capex_revenue"},  // chart payload key
  "detail_rows": []                          // per-edge / per-event rows for drill-down
}
```

`web/export_data.py` writes `signals.json`; a Zod schema (`SignalZ`) validates it;
a `SignalCard.svelte` renders the card and dispatches on `chart.type`. Adding a
hypothesis = appending one record + (if new) one chart renderer. The board is
built once in the H0 phase; H1–H4 each just add a record + chart.

## 4. The five hypotheses

Each links to its own spec. H0 and H1 are specified in depth now; H2–H4 are
design **outlines** to be detailed when reached (deliberately — H1's findings and
the realized board ergonomics should inform their final design; this is sequenced
de-risking, not a placeholder).

| # | Hypothesis | Horizon | Economic prior | Likely to show | Validation method | Spec |
|---|---|---|---|---|---|---|
| **H0** | Daily price→price lead/lag is sector beta | daily | — | ✅ as rigor anchor | already done (Priority 1) | `…-h0-daily-null-and-board.md` |
| **H1** | Capex → downstream revenue | quarterly | **High** | **High** | effect size + bootstrap CI + single holdout (no walk-forward) | `…-h1-capex-revenue.md` |
| **H3** | Cross-sectional residual structure | daily/weekly | Med | Med | walk-forward long-short (Sharpe, turnover) | `…-h3-cross-sectional.md` (outline) |
| **H2** | Event-conditioned drift (capex/earnings surprise) | multi-week | High | Med-High | event-time bootstrap; period split | `…-h2-event-drift.md` (outline) |
| **H4** | Macro cycle → sector | monthly | Med | Low-Med | monthly walk-forward + FDR | `…-h4-macro-sector.md` (outline) |

## 5. Sequencing & rationale

**H0 → H1 → H3 → H2 → H4.**

1. **H0** first — it requires no new compute (the Priority 1 result exists) and it
   builds the shared **Signal Lab board + `signals.json` + verdict taxonomy** that
   every later hypothesis plugs into. Ship the rigor anchor and the surface
   together.
2. **H1** next — strongest economic prior, data in hand (SEC EDGAR), on-thesis.
   The first card that can show real structure.
3. **H3** — reuses the de-beta'd residuals already produced; daily panel supports
   real walk-forward, so it can earn a **Confirmed** badge if structure exists.
4. **H2** — higher potential but needs an earnings-date/surprise source; specced
   after the board and H1 patterns are proven.
5. **H4** — hardens the existing macro scan; lowest prior, so last.

Each hypothesis is an independent spec → plan → execute cycle (Phase 2 = Codex),
adding exactly one board card. No hypothesis blocks another except H0 (which
builds the shared surface).

## 6. Shared infrastructure (built in H0, reused by all)

- `analysis/signals.py` — assembles `signals.json` records from each hypothesis's
  output table (a thin adapter layer; the statistics live in per-hypothesis
  modules).
- `web/export_data.py` — emit `signals.json`.
- `web/src/lib/signals.ts` + `SignalZ` — typed loader.
- `web/src/components/SignalLab.svelte` + `SignalCard.svelte` + chart renderers.
- Verdict taxonomy + evidence-chain schema (this doc, §3).

## 7. Non-goals

- No paid/alternative data; free sources only (yfinance, FRED, SEC EDGAR).
- No live trading, execution, or portfolio construction beyond H3's illustrative
  long-short equity curve.
- No claim of tradeable alpha unless a hypothesis earns **Confirmed** on its
  pre-registered gate. The board's value is rigor + honesty, not a promise.

## 8. Honesty guardrails (apply to every card)

- Show the full evidence chain, never just the verdict.
- State `n` and the validation method on every card; if the sample can't support
  walk-forward, say so on the card (H1, H2 small-sample).
- Carry the ex-post universe-selection caveat (from the Priority 1 spec §12) at
  the board level: "the value chain is specified ex-post; these test propagation
  *given* the chain, not its ex-ante discoverability."
- Multiple-testing: each hypothesis controls its own family; the board notes that
  running several hypotheses inflates program-wide FWER (declared, not hidden).
