# H0 — Daily Lead/Lag Null + Signal Lab Board

**Date:** 2026-06-04
**Status:** Design (in depth) — first hypothesis in the Signal Lab program.
**Parent:** `2026-06-04-atlas-signal-lab-roadmap.md`
**Depends on:** Priority 1 hardening (shipped) — `leadlag` table already contains
the 38 hardened edge rows (19 × {M1, M2}).

---

## 1. Claim & verdict

**Claim:** Upstream daily returns lead downstream daily returns along the value
chain. **Verdict: NULL** (and the contemporaneous link is sector beta).

This phase does **no new statistics** — Priority 1 already produced the result.
Its job is to (a) build the shared **Signal Lab board** and `signals.json`
pipeline, and (b) present the H0 result honestly as the program's rigor anchor.

## 2. The evidence to surface (from the existing `leadlag` table)

Computed 2026-06-04 against `data/atlas.duckdb`:

- Contemporaneous |corr| median: **0.142** (M1, market-removed) → **0.038** (M2,
  market + sector removed). The chain co-moves; most of it is sector beta.
- Lead/lag peak |corr| (residual, lags 1–20): **~0.035** — noise level.
- Edges clearing FDR (q ≤ 0.10): **0 / 19** in both specs.
- Median walk-forward OOS sign-retention: **0.50** (coin flip).
- 7/19 edges have their strongest relationship at a *negative* lag
  (`contradicts_thesis`).

**Evidence chain for the card:** `raw 0.14 → de-beta'd (sector) 0.04 → OOS sign
0.50`. **Stat:** best q = 0.17, 0/19 confirmed. **Verdict:** Null.

## 3. Scope

**In scope:**
- Shared Signal Lab infrastructure (board, `signals.json`, `SignalZ`, verdict
  taxonomy) — built here, reused by H1–H4.
- One H0 card summarizing the daily null, plus a map recolor showing raw vs
  sector-controlled edge correlation.
- An `analysis/signals.py` adapter that derives the H0 record from the `leadlag`
  table.

**Out of scope:** any new statistical computation; H1–H4 content.

## 4. Architecture / components

1. **`analysis/signals.py` (new)** — `build_signal_records(con) -> list[dict]`
   reads marts and emits `signals.json` records (§3 of roadmap). For H0:
   aggregates the `leadlag` edge rows into the H0 evidence chain + verdict. Pure
   apart from the DB read; unit-tested against a synthetic `leadlag` frame.
2. **`web/export_data.py` (modify)** — write `signals.json` from
   `build_signal_records`.
3. **`web/src/lib/signals.ts` + `SignalZ` (new)** — typed loader/validator for
   `signals.json` (verdict enum, evidence-chain array, stat object).
4. **`web/src/components/SignalLab.svelte` + `SignalCard.svelte` (new)** — board
   view; card renders Claim → Mechanism → Evidence chain → Verdict badge → chart.
   A `mode` value `"lab"` is added to the store alongside `story`/`explore`.
5. **Map recolor (modify `ValueChainMap.svelte`)** — edge stroke encodes
   `corr_raw` vs `corr_resid` (M2) so the "co-moves but doesn't lead" story is
   visible on the map too; label edges `sector beta`.

## 5. Evidence-chain & verdict contract

Conforms to roadmap §3. H0 record:

```jsonc
{
  "id": "H0", "title": "Daily lead/lag is sector beta", "horizon": "daily",
  "claim": "Upstream daily returns lead downstream daily returns",
  "mechanism": "If real, fast diffusion — but daily liquid names arbitrage it away",
  "verdict": "null",
  "evidence_chain": [
    {"stage": "raw contemporaneous",   "metric": "|corr|", "value": 0.14},
    {"stage": "sector de-beta'd",      "metric": "|corr|", "value": 0.04},
    {"stage": "OOS sign-retention",    "metric": "rate",   "value": 0.50}
  ],
  "stat": {"name": "edges_confirmed", "value": 0, "q_value": 0.17, "n": 19},
  "caveats": ["7/19 edges' strongest relationship is at a negative lag"],
  "chart": {"type": "edge_corr_bars", "ref": "h0"},
  "detail_rows": [ /* per-edge corr_raw, corr_resid, lag, q, oos_sign_rate */ ]
}
```

## 6. Testing (TDD)

- `analysis/signals.py`: H0 record has `verdict == "null"`, evidence chain ordered
  raw→controlled→OOS, `n == 19`, detail rows = 19 (M2). Synthetic `leadlag` frame.
- Web: `SignalZ` parses a valid record and rejects an invalid verdict; the board
  renders one card per record; the null badge renders.
- E2E smoke: Signal Lab mode toggles and shows the H0 card.

## 7. Honesty framing

The H0 card is the anchor: it openly shows the project's first hypothesis failing
the rigorous bar, with the sector-decomposition as the explanation. This sets the
standard every other card is held to.
