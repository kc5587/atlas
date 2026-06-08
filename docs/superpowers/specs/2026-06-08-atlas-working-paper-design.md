# Atlas Working Paper — Design Spec

**Status:** approved aesthetic (look-and-feel slice signed off 2026-06-08)
**Slice reference:** `docs/mockups/atlas-paper-slice.html`
**Register chosen:** Working paper / LaTeX · long-form narrative (single scrollytelling document)

## 1. Goal & non-goals

**Goal.** Replace the generic dashboard framing of the Atlas front-end with a single, rigorous
**quantitative working paper** that reads like an arXiv/SSRN preprint: abstract → value chain →
testing campaign → method → per-hypothesis figures → thesis. It must surface *every* Atlas feature
(the data, the methodology, the 13 hypotheses, the thesis) in the academic register, driven by the
real exported data.

**Non-goals.** No 3D/WebGL, no glassmorphism, no marketing-hero theatrics. No second framework
(stays Svelte 5 + Vite + TS + D3). Not a redesign of the analysis pipeline — only additive export
changes.

## 2. Aesthetic system (locked — from the slice)

- **Type:** EB Garamond (headings + body, incl. italic); **IBM Plex Mono** for all numerals,
  statistics, labels, and code. Tabular-nums on figures/tables.
- **Palette:** paper `#fbfaf6`, ink `#1b1a17`, soft ink `#403c34`, rule `#d9d3c6`; **one** data-blue
  `#2a4b8d`; muted red `#9b2d2d` reserved for the FDR line and `contradicts`/negative effects.
  Color encodes data only.
- **Layout:** centered reading measure (~680px) + right **sidenote rail** (Tufte); 12-col discipline
  for figures that break out full width. Hairline rules, never boxes. Small-caps mono section labels,
  numbered sections (`1`, `1.1`), drop cap on the lede.
- **Figures:** numbered `Figure N` + italic caption; SVG, ink-on-paper, top/bottom hairline frame.
- **Motion (motion-framer principles, restrained):** reveal-on-scroll (fade + 14px rise, once);
  scroll-linked progress for the value-chain figure as the argument unfolds. `prefers-reduced-motion`
  honored. No parallax, no glow.

## 3. Structure (the document)

1. **Masthead + Abstract** — title, subtitle, byline, justified abstract.
2. **§1 The value chain** — prose + **Figure 1 (value-chain DAG)**; methodology sidenotes.
3. **§2 The campaign at a glance** — **Figure 2 (volcano plot)**; **Table 1 (results)**.
4. **§3 Method** — de-beta (M1/M2), selection-aware null + block length, BH-FDR per family, OOS,
   point-in-time alignment. Mostly prose + sidenotes + a small **evidence-chain strip** figure.
5. **§4 Findings** — per-hypothesis subsections, each with its proper figure (see §4 inventory).
6. **§5 Thesis** — efficient pricing vs. compensated risk premia; the role of the nulls.
7. **Appendix / Table 1 (full)** — all 13 hypotheses.

## 4. Figure inventory → data mapping

| Fig | Type | Source | Notes |
|-----|------|--------|-------|
| 1 | Value-chain DAG | `graph.json` (nodes/edges) + `meta.stages` | confirmed edges flagged from `leadlag.json`/signals detail |
| 2 | Volcano plot | `signals.json`: x = per-hyp effect size, y = −log10(q), color = verdict | **needs a consistent effect-size accessor** (H0=edges_confirmed, H6=mean_vrp, others=slope); q from `stat.q_value` or record gating-q |
| 3 | Forest / coefficient plot | `signals.json` `stat.value` ± `stat.ci` | one row per hypothesis; zero line; verdict color |
| 4 | Cross-correlogram + CI | **per-lag corr curve** | ⚠ not exported — needs `export_data` extension (emit lag sweep for key pairs, e.g. H1/H0) |
| 5 | Event-study CAR ± CI (H2) | **drift-by-horizon curve** | ⚠ needs export extension (event_drift detail) |
| 6 | Variance-premium series (H6) | **implied² vs realized² series** | ⚠ needs export extension (vol_premium detail) |
| — | Evidence-chain strip | `signals.json` `evidence_chain[]` | already present per record |
| T1 | Results table | `signals.json` (id, claim, stat.value, q, n, verdict) | ruled academic table |

**Export changes (additive, `web/export_data.py` + analysis detail):** emit (a) the lead-lag
correlation-by-lag array for a small set of headline pairs, (b) the H2 drift-by-horizon points with
CI, (c) the H6 VRP time series. Small, schema-versioned additions to the existing JSON exports; no
change to verdicts.

## 5. Frontend architecture (Svelte)

- **New `Paper.svelte`** becomes the primary view (mounted by `App.svelte` or replacing its body).
  Long-form layout owns the grid + sidenote rail + reveal observer.
- **Figure components** (one file each, pure, props-in): `ValueChainFigure.svelte` (reuses/restyles
  the existing `ValueChainMap` logic as a restrained static+hover DAG), `VolcanoFigure.svelte`,
  `ForestFigure.svelte`, `CorrelogramFigure.svelte`, `EventStudyFigure.svelte`, `VrpFigure.svelte`,
  `EvidenceStrip.svelte`, `ResultsTable.svelte`, plus `Figure.svelte` (caption frame) and
  `Sidenote.svelte`.
- **Reuse:** existing loaders `lib/data.ts`, `lib/signals.ts`, `lib/leadlag.ts`, `lib/types.ts`,
  `lib/stages.ts`. Existing `SignalCard`/`Scroller`/`NodePanel` are superseded or absorbed; remove or
  repurpose rather than leave dead.
- **Styling:** a small design-token CSS module (`lib/paper.css` or `:root` vars) mirroring §2; load the
  two Google fonts (self-host for the static deploy to avoid an external request).
- **Routing:** single page (static site). The interactive value-chain map, if retained for
  exploration, becomes an in-figure interaction within Figure 1 — not a separate app.

## 6. Testing

- **vitest:** data transforms (effect-size accessor for the volcano, −log10(q) with NaN/None guard,
  forest CI extraction, DAG edge/stage layout, lag-curve parsing).
- **Playwright smoke:** paper renders; Figure 1/2 + Table 1 present; a confirmed hypothesis shows
  `confirmed`; reduced-motion path. Reuse the fixture-DB → export flow (extend fixtures for the new
  curve exports).
- Keep `svelte-check` + `ruff`/`pytest` green for the export changes.

## 7. Phasing

- **P1 — shell + headline figures (no backend change):** Paper layout + tokens + fonts; Figure 1
  (DAG), Figure 2 (volcano), Table 1, evidence strip — all from existing exports. Ships the register.
- **P2 — export extensions + remaining figures:** add lag-curve / CAR / VRP exports + Figures 4–6 and
  the forest plot; per-hypothesis §4 subsections.
- **P3 — narrative polish:** scroll-linked figure transitions, sidenote refinement, self-host fonts,
  responsive/print stylesheet, a11y pass.

## 8. Open decisions (for the plan)

- **Effect-size definition for the volcano** when `stat.value` isn't a slope (H0, H6) — standardize or
  annotate per hypothesis. (Recommend: a documented per-hypothesis accessor; show the native statistic
  in the tooltip/caption.)
- Whether to **retain the interactive map** as Figure 1's hover behavior or ship a static DAG first
  (recommend static in P1, interactive in P3).
- Self-host vs CDN fonts for the GitHub-Pages deploy (recommend self-host).
