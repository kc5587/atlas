# Atlas Working Paper — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Atlas front-end's primary view with a long-form academic "working paper" shell plus its three headline figures (value-chain DAG, volcano plot, results table) and the evidence strip, driven entirely by the data already exported today.

**Architecture:** A new `Paper.svelte` becomes the page body, composing small, pure figure components from a tested `lib/paper.ts` transform module. No backend/export changes in P1 (cross-correlogram, event-study, VRP series are P2). Existing Svelte 5 + Vite + TS + Zod loaders are reused; the interactive map is left in place but no longer mounted as the primary view.

**Tech Stack:** Svelte 5 (runes), TypeScript, Vite, Zod, vitest, Playwright. Fonts: EB Garamond + IBM Plex Mono (Google Fonts in P1; self-host in P3).

---

## File Structure

- Create `atlas/web/src/lib/paper.ts` — pure transforms: effect-size accessor, volcano points, table rows, DAG layout, confirmed-pair extraction. **Tested.**
- Create `atlas/web/src/lib/paper.css` — design tokens + base paper typography (imported once by `Paper.svelte`).
- Create `atlas/web/src/components/paper/Figure.svelte` — numbered figure + caption frame.
- Create `atlas/web/src/components/paper/Sidenote.svelte` — Tufte margin note.
- Create `atlas/web/src/components/paper/VolcanoFigure.svelte` — Figure 2.
- Create `atlas/web/src/components/paper/ValueChainFigure.svelte` — Figure 1 (static DAG).
- Create `atlas/web/src/components/paper/ResultsTable.svelte` — Table 1.
- Create `atlas/web/src/components/paper/EvidenceStrip.svelte` — evidence chain row.
- Create `atlas/web/src/components/Paper.svelte` — the document (masthead → §1 → §2 → Table 1).
- Modify `atlas/web/src/App.svelte` — mount `Paper` as the primary view.
- Modify `atlas/web/index.html` — add the two font links.
- Create `atlas/web/tests/paper.test.ts` — vitest for `lib/paper.ts`.
- Create `atlas/web/tests/paper.spec.ts` — Playwright smoke for the rendered paper.

Run tests from `atlas/web`: `npm run test` (vitest) and `npx playwright test paper.spec.ts`.

---

### Task 1: `lib/paper.ts` — effect size + volcano points

**Files:**
- Create: `atlas/web/src/lib/paper.ts`
- Test: `atlas/web/tests/paper.test.ts`

Decision baked in: the volcano x-axis is **slope** and y is **−log10(q)**. Only hypotheses whose
statistic is a slope *and* carry a selection-aware q appear on the volcano (their `stat.name` ends in
`"slope"` and `stat.q_value != null`). H0 (an edge count) and H6 (variance premium, criterion-based,
`q_value == null`) are intentionally excluded from the volcano and reported in Table 1.

- [ ] **Step 1: Write the failing test**

```ts
// atlas/web/tests/paper.test.ts
import { describe, it, expect } from "vitest";
import { effectSize, negLog10Q, volcanoPoints } from "../src/lib/paper";
import type { Signal } from "../src/lib/signals";

const sig = (over: Partial<Signal> & { id: string }): Signal => ({
  id: over.id, title: over.id, claim: "", mechanism: "", horizon: "",
  verdict: over.verdict ?? "null",
  evidence_chain: [], caveats: [], chart: { type: "", ref: "" }, detail_rows: [],
  stat: over.stat ?? { name: "slope", value: 0, q_value: 1, n: 0 },
});

describe("paper transforms", () => {
  it("effectSize returns the headline statistic value", () => {
    expect(effectSize(sig({ id: "H1", stat: { name: "slope", value: 0.41, q_value: 0.055, n: 11 } }))).toBe(0.41);
  });

  it("negLog10Q maps q to significance height; null q -> null", () => {
    expect(negLog10Q(0.1)).toBeCloseTo(1, 6);
    expect(negLog10Q(0.001)).toBeCloseTo(3, 6);
    expect(negLog10Q(null)).toBeNull();
  });

  it("volcanoPoints includes only slope hypotheses with a finite q", () => {
    const signals = [
      sig({ id: "H1", verdict: "confirmed", stat: { name: "slope", value: 0.41, q_value: 0.055, n: 11 } }),
      sig({ id: "H0", stat: { name: "edges_confirmed", value: 1, q_value: 0.04, n: 1 } }),       // excluded: not a slope
      sig({ id: "H6", verdict: "confirmed", stat: { name: "mean_vrp", value: 0.009, q_value: null, n: 4120 } }), // excluded: null q
    ];
    const pts = volcanoPoints(signals);
    expect(pts.map((p) => p.id)).toEqual(["H1"]);
    expect(pts[0]).toMatchObject({ id: "H1", slope: 0.41, y: expect.any(Number), verdict: "confirmed" });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlas/web && npx vitest run tests/paper.test.ts`
Expected: FAIL — `Cannot find module '../src/lib/paper'`.

- [ ] **Step 3: Write minimal implementation**

```ts
// atlas/web/src/lib/paper.ts
import type { Signal } from "./signals";

export const FDR_ALPHA = 0.1;

/** Headline effect size for a hypothesis (slope for slope-based records). */
export function effectSize(sig: Signal): number {
  return sig.stat.value;
}

/** −log10(q); null when q is missing/non-finite/non-positive. */
export function negLog10Q(q: number | null | undefined): number | null {
  if (q == null || !Number.isFinite(q) || q <= 0) return null;
  return -Math.log10(q);
}

export interface VolcanoPoint {
  id: string;
  slope: number;
  y: number; // −log10(q)
  q: number;
  verdict: Signal["verdict"];
}

/** Slope hypotheses with a finite selection-aware q. Excludes H0 (count) and H6 (null q). */
export function volcanoPoints(signals: Signal[]): VolcanoPoint[] {
  const out: VolcanoPoint[] = [];
  for (const s of signals) {
    if (!s.stat.name.endsWith("slope")) continue;
    const y = negLog10Q(s.stat.q_value);
    if (y == null) continue;
    out.push({ id: s.id, slope: s.stat.value, y, q: s.stat.q_value as number, verdict: s.verdict });
  }
  return out;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd atlas/web && npx vitest run tests/paper.test.ts`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add atlas/web/src/lib/paper.ts atlas/web/tests/paper.test.ts
git commit -m "feat(paper): effect-size + volcano-point transforms"
```

---

### Task 2: `lib/paper.ts` — table rows + DAG layout + confirmed pairs

**Files:**
- Modify: `atlas/web/src/lib/paper.ts`
- Modify: `atlas/web/tests/paper.test.ts`

- [ ] **Step 1: Write the failing test (append)**

```ts
// append to atlas/web/tests/paper.test.ts
import { tableRows, confirmedPairs, dagLayout } from "../src/lib/paper";

describe("paper table + dag", () => {
  it("tableRows projects id/claim/slope/q/n/verdict", () => {
    const rows = tableRows([sig({ id: "H1", claim: "Capex -> revenue", verdict: "confirmed",
      stat: { name: "slope", value: 0.41, q_value: 0.055, n: 11 } })]);
    expect(rows[0]).toEqual({ id: "H1", claim: "Capex -> revenue", slope: 0.41, q: 0.055, n: 11, verdict: "confirmed" });
  });

  it("confirmedPairs extracts H1/H11 edges that clear FDR", () => {
    const s = sig({ id: "H1", verdict: "confirmed",
      detail_rows: [{ left: "asml", right: "tsmc", q_value: 0.04 }, { left: "x", right: "y", q_value: 0.5 }] });
    expect(confirmedPairs([s])).toEqual(new Set(["asml|tsmc"]));
  });

  it("dagLayout places nodes by stage column and finite edge coordinates", () => {
    const graph = {
      nodes: [{ id: "asml", name: "ASML", stage: "equipment" }, { id: "tsmc", name: "TSMC", stage: "foundry" }],
      edges: [{ from_id: "asml", to_id: "tsmc" }],
    } as any;
    const lay = dagLayout(graph, ["equipment", "foundry"], new Set(["asml|tsmc"]), 800, 300);
    expect(lay.nodes.find((n) => n.id === "asml")!.x).toBeLessThan(lay.nodes.find((n) => n.id === "tsmc")!.x);
    expect(lay.edges[0].confirmed).toBe(true);
    for (const v of [lay.edges[0].x1, lay.edges[0].y1, lay.edges[0].x2, lay.edges[0].y2]) expect(Number.isFinite(v)).toBe(true);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlas/web && npx vitest run tests/paper.test.ts`
Expected: FAIL — `confirmedPairs`/`tableRows`/`dagLayout` are not exported.

- [ ] **Step 3: Write minimal implementation (append to `lib/paper.ts`)**

```ts
// append to atlas/web/src/lib/paper.ts

export interface TableRow {
  id: string; claim: string; slope: number; q: number | null; n: number; verdict: Signal["verdict"];
}
export function tableRows(signals: Signal[]): TableRow[] {
  return signals.map((s) => ({
    id: s.id, claim: s.claim, slope: s.stat.value,
    q: s.stat.q_value ?? null, n: s.stat.n, verdict: s.verdict,
  }));
}

/** "from|to" keys for H1/H11 detail edges with q <= FDR_ALPHA. */
export function confirmedPairs(signals: Signal[]): Set<string> {
  const keys = new Set<string>();
  for (const s of signals) {
    if (s.id !== "H1" && s.id !== "H11") continue;
    for (const r of s.detail_rows) {
      const q = (r as any).q_value;
      if (typeof q === "number" && q <= FDR_ALPHA && (r as any).left && (r as any).right) {
        keys.add(`${(r as any).left}|${(r as any).right}`);
      }
    }
  }
  return keys;
}

export interface DagNode { id: string; name: string; x: number; y: number; stage: string; }
export interface DagEdge { x1: number; y1: number; x2: number; y2: number; confirmed: boolean; }
export interface DagLayout { nodes: DagNode[]; edges: DagEdge[]; }

export function dagLayout(
  graph: { nodes: { id: string; name: string; stage: string }[]; edges: { from_id: string; to_id: string }[] },
  stageOrder: string[], confirmed: Set<string>, w: number, h: number,
): DagLayout {
  const mTop = 34, mBot = 26, mX = 24;
  const colW = (w - mX * 2) / Math.max(stageOrder.length, 1);
  const colX = (stage: string) => mX + colW * (stageOrder.indexOf(stage) + 0.5);
  const byStage: Record<string, { id: string; name: string }[]> = {};
  for (const n of graph.nodes) (byStage[n.stage] ??= []).push(n);
  const pos: Record<string, DagNode> = {};
  const nodes: DagNode[] = [];
  for (const stage of stageOrder) {
    const list = byStage[stage] ?? [];
    const gap = (h - mTop - mBot) / (list.length + 1);
    list.forEach((n, i) => {
      const node = { id: n.id, name: n.name, x: colX(stage), y: mTop + gap * (i + 1), stage };
      pos[n.id] = node; nodes.push(node);
    });
  }
  const edges: DagEdge[] = [];
  for (const e of graph.edges) {
    const a = pos[e.from_id], b = pos[e.to_id];
    if (!a || !b) continue;
    edges.push({ x1: a.x, y1: a.y, x2: b.x, y2: b.y, confirmed: confirmed.has(`${e.from_id}|${e.to_id}`) });
  }
  return { nodes, edges };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd atlas/web && npx vitest run tests/paper.test.ts`
Expected: PASS (6 passed total).

- [ ] **Step 5: Commit**

```bash
git add atlas/web/src/lib/paper.ts atlas/web/tests/paper.test.ts
git commit -m "feat(paper): table rows, confirmed-pair extraction, DAG layout"
```

---

### Task 3: Design tokens + fonts

**Files:**
- Create: `atlas/web/src/lib/paper.css`
- Modify: `atlas/web/index.html`

- [ ] **Step 1: Create the tokens stylesheet**

```css
/* atlas/web/src/lib/paper.css */
:root {
  --paper:#fbfaf6; --ink:#1b1a17; --ink-soft:#403c34; --muted:#8a8377;
  --rule:#d9d3c6; --rule-2:#c7c0b0; --blue:#2a4b8d; --red:#9b2d2d;
  --null:#b3ab9c; --suggest:#9a6a1e;
  --serif:'EB Garamond',Georgia,serif; --mono:'IBM Plex Mono',ui-monospace,monospace;
}
.paper { background:var(--paper); color:var(--ink); font-family:var(--serif);
  font-size:20px; line-height:1.62; text-rendering:optimizeLegibility; }
.paper .num { font-family:var(--mono); font-variant-numeric:tabular-nums; }
.paper figure svg { display:block; width:100%; height:auto; background:#fcfbf8;
  border-top:1px solid var(--ink); border-bottom:1px solid var(--rule); }
@media (prefers-reduced-motion: reduce) { .paper .reveal { opacity:1 !important; transform:none !important; } }
```

- [ ] **Step 2: Add the font links to `index.html`** (inside `<head>`, before the module script)

```html
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=EB+Garamond:ital,wght@0,400;0,500;0,600;1,400;1,500&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet" />
```

- [ ] **Step 3: Verify the dev server compiles**

Run: `cd atlas/web && npx svelte-check --tsconfig ./tsconfig.json`
Expected: 0 errors (warnings about existing files acceptable).

- [ ] **Step 4: Commit**

```bash
git add atlas/web/src/lib/paper.css atlas/web/index.html
git commit -m "feat(paper): design tokens + academic fonts"
```

---

### Task 4: `Figure.svelte` + `Sidenote.svelte` wrappers

**Files:**
- Create: `atlas/web/src/components/paper/Figure.svelte`
- Create: `atlas/web/src/components/paper/Sidenote.svelte`

- [ ] **Step 1: Create `Figure.svelte`**

```svelte
<!-- atlas/web/src/components/paper/Figure.svelte -->
<script lang="ts">
  let { n, caption }: { n: number; caption: string } = $props();
  let el: HTMLElement;
  let shown = $state(false);
  $effect(() => {
    if (!el) return;
    const io = new IntersectionObserver((es) => es.forEach((e) => e.isIntersecting && (shown = true)), { threshold: 0.15 });
    io.observe(el);
    return () => io.disconnect();
  });
</script>

<figure bind:this={el} class="reveal" class:in={shown}>
  <slot />
  <figcaption><span class="fl">Figure {n}.</span> {@html caption}</figcaption>
</figure>

<style>
  figure { margin: 34px 0; }
  .reveal { opacity: 0; transform: translateY(14px); transition: opacity .7s ease, transform .7s cubic-bezier(.2,.6,.3,1); }
  .reveal.in { opacity: 1; transform: none; }
  figcaption { font-size: 15.5px; line-height: 1.45; color: var(--ink-soft); margin-top: 11px; max-width: 780px; }
  .fl { font-family: var(--mono); font-size: 12px; font-weight: 500; color: var(--ink); }
</style>
```

- [ ] **Step 2: Create `Sidenote.svelte`**

```svelte
<!-- atlas/web/src/components/paper/Sidenote.svelte -->
<script lang="ts">
  let { n }: { n: number } = $props();
</script>

<aside class="sidenote"><span class="sn">{n}.</span><slot /></aside>

<style>
  .sidenote { font-family: var(--serif); font-size: 15px; line-height: 1.5; color: var(--ink-soft);
    border-left: 2px solid var(--rule-2); padding-left: 14px; }
  .sn { font-family: var(--mono); font-size: 11px; color: var(--blue); margin-right: 5px; }
</style>
```

- [ ] **Step 3: Verify compile**

Run: `cd atlas/web && npx svelte-check --tsconfig ./tsconfig.json`
Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
git add atlas/web/src/components/paper/Figure.svelte atlas/web/src/components/paper/Sidenote.svelte
git commit -m "feat(paper): Figure + Sidenote wrapper components"
```

---

### Task 5: `VolcanoFigure.svelte` (Figure 2)

**Files:**
- Create: `atlas/web/src/components/paper/VolcanoFigure.svelte`

- [ ] **Step 1: Create the component**

```svelte
<!-- atlas/web/src/components/paper/VolcanoFigure.svelte -->
<script lang="ts">
  import type { Signal } from "../../lib/signals";
  import { volcanoPoints, negLog10Q, FDR_ALPHA } from "../../lib/paper";
  let { signals }: { signals: Signal[] } = $props();

  const W = 760, H = 440, m = { t: 26, r: 30, b: 54, l: 60 };
  const PW = W - m.l - m.r, PH = H - m.t - m.b;
  const xs = (slope: number) => m.l + ((slope + 0.1) / 0.6) * PW; // domain [-0.1, 0.5]
  const ys = (y: number) => m.t + PH - (y / 2.6) * PH;            // −log10 q in [0, 2.6]
  const pts = $derived(volcanoPoints(signals));
  const fdrY = ys(negLog10Q(FDR_ALPHA)!);
  const xticks = [-0.1, 0, 0.1, 0.2, 0.3, 0.4, 0.5];
  const yticks: [number, string][] = [[1, "1.0"], [0.1, "0.1"], [0.01, ".01"]];
  const fill = (v: Signal["verdict"]) => (v === "confirmed" ? "var(--blue)" : v === "suggestive" ? "var(--suggest)" : "#fcfbf8");
  const stroke = (v: Signal["verdict"]) => (v === "null" ? "var(--null)" : v === "suggestive" ? "var(--suggest)" : "var(--blue)");
</script>

<svg viewBox="0 0 {W} {H}" role="img" aria-label="Volcano plot of all slope hypotheses">
  <line x1={m.l} y1={m.t} x2={m.l} y2={m.t + PH} stroke="var(--ink)" />
  <line x1={m.l} y1={m.t + PH} x2={m.l + PW} y2={m.t + PH} stroke="var(--ink)" />
  {#each xticks as v}
    <line x1={xs(v)} y1={m.t + PH} x2={xs(v)} y2={m.t + PH + 5} stroke="var(--ink)" />
    <text x={xs(v)} y={m.t + PH + 18} text-anchor="middle" font-family="var(--mono)" font-size="11" fill="var(--muted)">{v.toFixed(1)}</text>
  {/each}
  {#each yticks as [q, lab]}
    <text x={m.l - 9} y={ys(negLog10Q(q)!) + 4} text-anchor="end" font-family="var(--mono)" font-size="11" fill="var(--muted)">q={lab}</text>
  {/each}
  <line x1={xs(0)} y1={m.t} x2={xs(0)} y2={m.t + PH} stroke="var(--rule-2)" stroke-dasharray="2 4" />
  <line x1={m.l} y1={fdrY} x2={m.l + PW} y2={fdrY} stroke="var(--red)" stroke-width="1.2" stroke-dasharray="5 4" />
  <text x={m.l + PW} y={fdrY - 7} text-anchor="end" font-family="var(--mono)" font-size="11" fill="var(--red)">FDR q = 0.10</text>
  <text x={m.l + PW / 2} y={H - 12} text-anchor="middle" font-family="var(--serif)" font-style="italic" font-size="14" fill="var(--ink-soft)">effect size (slope)</text>
  {#each pts as p}
    <circle cx={xs(p.slope)} cy={ys(p.y)} r={p.verdict === "confirmed" ? 6 : 5} fill={fill(p.verdict)} stroke={stroke(p.verdict)} stroke-width="1.4" />
    <text x={p.slope > 0.33 ? xs(p.slope) - 10 : xs(p.slope) + 10} y={ys(p.y) + 4}
      text-anchor={p.slope > 0.33 ? "end" : "start"} font-family="var(--mono)"
      font-size={p.verdict === "null" ? 10 : 11} fill={p.verdict === "null" ? "var(--muted)" : "var(--ink)"}>{p.id}</text>
  {/each}
</svg>
```

- [ ] **Step 2: Verify compile**

Run: `cd atlas/web && npx svelte-check --tsconfig ./tsconfig.json`
Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add atlas/web/src/components/paper/VolcanoFigure.svelte
git commit -m "feat(paper): volcano plot figure (Figure 2)"
```

---

### Task 6: `ValueChainFigure.svelte` (Figure 1) + `ResultsTable.svelte` + `EvidenceStrip.svelte`

**Files:**
- Create: `atlas/web/src/components/paper/ValueChainFigure.svelte`
- Create: `atlas/web/src/components/paper/ResultsTable.svelte`
- Create: `atlas/web/src/components/paper/EvidenceStrip.svelte`

- [ ] **Step 1: Create `ValueChainFigure.svelte`**

```svelte
<!-- atlas/web/src/components/paper/ValueChainFigure.svelte -->
<script lang="ts">
  import type { Graph } from "../../lib/types";
  import type { Signal } from "../../lib/signals";
  import { dagLayout, confirmedPairs } from "../../lib/paper";
  import { stageOrder } from "../../lib/stages";
  let { graph, signals }: { graph: Graph; signals: Signal[] } = $props();
  const W = 920, H = 380;
  const lay = $derived(dagLayout(graph as any, stageOrder, confirmedPairs(signals), W, H));
</script>

<svg viewBox="0 0 {W} {H}" role="img" aria-label="The AI value chain">
  {#each lay.edges as e}
    {@const mx = (e.x1 + e.x2) / 2}
    <path d={`M${e.x1 + 6},${e.y1} C${mx},${e.y1} ${mx},${e.y2} ${e.x2 - 7},${e.y2}`}
      fill="none" stroke={e.confirmed ? "var(--blue)" : "var(--rule)"} stroke-width={e.confirmed ? 1.6 : 0.9} opacity={e.confirmed ? 0.85 : 0.7} />
  {/each}
  {#each lay.nodes as n}
    <circle cx={n.x} cy={n.y} r="3.2" fill="var(--ink)" />
    <text x={n.x} y={n.y - 8} text-anchor="middle" font-family="var(--serif)" font-size="13" fill="var(--ink-soft)">{n.name}</text>
  {/each}
</svg>
```

- [ ] **Step 2: Create `ResultsTable.svelte`**

```svelte
<!-- atlas/web/src/components/paper/ResultsTable.svelte -->
<script lang="ts">
  import type { Signal } from "../../lib/signals";
  import { tableRows } from "../../lib/paper";
  let { signals }: { signals: Signal[] } = $props();
  const rows = $derived(tableRows(signals));
  const cls = (v: string) => (v === "confirmed" ? "c" : v === "suggestive" ? "s" : "n");
</script>

<table class="t1">
  <caption>Table 1 — Hypotheses, effect sizes, and verdicts</caption>
  <thead><tr><th>ID</th><th>Claim</th><th>slope</th><th>q</th><th>n</th><th>verdict</th></tr></thead>
  <tbody>
    {#each rows as r}
      <tr>
        <td class="num">{r.id}</td><td>{r.claim}</td>
        <td class="num">{r.slope.toFixed(2)}</td>
        <td class="num">{r.q == null ? "—" : r.q.toFixed(3)}</td>
        <td class="num">{r.n}</td>
        <td><span class="vd {cls(r.verdict)}">{r.verdict}</span></td>
      </tr>
    {/each}
  </tbody>
</table>

<style>
  .t1 { border-collapse: collapse; width: 100%; margin: 18px 0; font-size: 16px; }
  caption { font-family: var(--mono); font-size: 12px; color: var(--ink); text-align: left; padding-bottom: 8px; border-bottom: 2px solid var(--ink); }
  th { font-family: var(--mono); font-size: 11px; letter-spacing: .06em; text-transform: uppercase; color: var(--muted); text-align: left; padding: 9px 10px; border-bottom: 1px solid var(--rule-2); font-weight: 500; }
  td { padding: 8px 10px; border-bottom: 1px solid var(--rule); }
  td.num { font-variant-numeric: tabular-nums; font-size: 14px; color: var(--ink-soft); }
  .vd { font-family: var(--mono); font-size: 11px; text-transform: uppercase; }
  .vd.c { color: var(--blue); } .vd.s { color: var(--suggest); } .vd.n { color: var(--muted); }
</style>
```

- [ ] **Step 3: Create `EvidenceStrip.svelte`**

```svelte
<!-- atlas/web/src/components/paper/EvidenceStrip.svelte -->
<script lang="ts">
  import type { Signal } from "../../lib/signals";
  let { signal }: { signal: Signal } = $props();
</script>

<div class="strip">
  {#each signal.evidence_chain as step, i}
    <div class="cell">
      <div class="stage">{step.stage}</div>
      <div class="val num">{step.value}</div>
      <div class="metric">{step.metric}</div>
    </div>
    {#if i < signal.evidence_chain.length - 1}<div class="arrow">→</div>{/if}
  {/each}
</div>

<style>
  .strip { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin: 14px 0; }
  .cell { border: 1px solid var(--rule-2); padding: 8px 12px; min-width: 120px; }
  .stage { font-family: var(--mono); font-size: 10px; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); }
  .val { font-size: 20px; color: var(--ink); }
  .metric { font-size: 12px; color: var(--ink-soft); font-style: italic; }
  .arrow { color: var(--rule-2); font-family: var(--mono); }
</style>
```

- [ ] **Step 4: Verify compile**

Run: `cd atlas/web && npx svelte-check --tsconfig ./tsconfig.json`
Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add atlas/web/src/components/paper/ValueChainFigure.svelte atlas/web/src/components/paper/ResultsTable.svelte atlas/web/src/components/paper/EvidenceStrip.svelte
git commit -m "feat(paper): value-chain figure, results table, evidence strip"
```

---

### Task 7: `Paper.svelte` document + mount in `App.svelte`

**Files:**
- Create: `atlas/web/src/components/Paper.svelte`
- Modify: `atlas/web/src/App.svelte`

- [ ] **Step 1: Create `Paper.svelte`**

```svelte
<!-- atlas/web/src/components/Paper.svelte -->
<script lang="ts">
  import "../lib/paper.css";
  import type { Graph } from "../lib/types";
  import type { Signal } from "../lib/signals";
  import Figure from "./paper/Figure.svelte";
  import Sidenote from "./paper/Sidenote.svelte";
  import ValueChainFigure from "./paper/ValueChainFigure.svelte";
  import VolcanoFigure from "./paper/VolcanoFigure.svelte";
  import ResultsTable from "./paper/ResultsTable.svelte";
  let { graph, signals }: { graph: Graph; signals: Signal[] } = $props();
  const n = $derived({
    c: signals.filter((s) => s.verdict === "confirmed").length,
    s: signals.filter((s) => s.verdict === "suggestive").length,
    n: signals.filter((s) => s.verdict === "null").length,
  });
</script>

<main class="paper page">
  <header class="body">
    <div class="kicker">Atlas · Working Paper · Draft, June 2026</div>
    <h1 class="title">Honest Signal Detection Across the AI Value Chain</h1>
    <p class="subtitle">Lead–lag structure, variance risk premia, and the discipline of the null result</p>
  </header>
  <hr class="rule heavy body" />

  <section class="abstract body">
    <span class="lbl">Abstract</span>
    <p>We test whether economically-motivated signals propagate across the AI supply chain, or are
    arbitraged away. Each hypothesis is evaluated with a selection-aware bootstrap null, Benjamini–Hochberg
    control across declared families, and out-of-sample validation. Of {signals.length} hypotheses,
    <span class="num">{n.c}</span> are confirmed, <span class="num">{n.s}</span> suggestive, and
    <span class="num">{n.n}</span> null. The nulls are not failures; they are the result.</p>
  </section>

  <section class="body">
    <h2 class="sec"><span class="hn num">1</span>The value chain</h2>
    <p class="drop">The object of study is a directed graph of supplier relationships among the firms that
    build and operate AI infrastructure.<sup class="ref">1</sup> The question throughout is whether a shock
    at one node is informative about a later move downstream.</p>
  </section>
  <Sidenote n={1}>Nodes carry a CIK where a US filer exists; stage membership is fixed ex-ante and never tuned to a result.</Sidenote>

  <Figure n={1} caption={`The AI value chain. Hairline edges denote supplier relations; <span style="color:var(--blue)">blue edges</span> mark confirmed capex→revenue propagation (H1, H11).`}>
    <ValueChainFigure {graph} {signals} />
  </Figure>

  <section class="body">
    <h2 class="sec"><span class="hn num">2</span>The testing campaign at a glance</h2>
    <p>Figure 2 plots each slope hypothesis by effect size against selection-aware significance, with the
    false-discovery threshold drawn explicitly.<sup class="ref">2</sup></p>
  </section>
  <Sidenote n={2}>q-values are Benjamini–Hochberg adjusted within each family over finite, eligible edges. The dashed line is q = 0.10. H0 (an edge count) and H6 (variance premium, criterion-based) are reported in Table 1.</Sidenote>

  <Figure n={2} caption={`<em>Volcano plot.</em> Effect size versus −log<sub>10</sub> q for all slope hypotheses. Points above the dashed line clear FDR control at q = 0.10.`}>
    <VolcanoFigure {signals} />
  </Figure>

  <div class="body"><ResultsTable {signals} /></div>
</main>

<style>
  .page { max-width: 1120px; margin: 0 auto; padding: 84px 40px 120px;
    display: grid; grid-template-columns: minmax(0,680px) 36px 230px; justify-content: center; }
  .body { grid-column: 1; }
  :global(.paper figure), :global(.paper .sidenote) { grid-column: 1 / -1; }
  :global(.paper aside.sidenote) { grid-column: 3; }
  .kicker { font-family: var(--mono); font-size: 12px; letter-spacing: .22em; text-transform: uppercase; color: var(--muted); }
  .title { font-weight: 600; font-size: 40px; line-height: 1.12; margin: .5rem 0 0; }
  .subtitle { font-style: italic; color: var(--ink-soft); font-size: 22px; margin-top: 10px; }
  .rule.heavy { border: 0; border-top: 2px solid var(--ink); margin: 26px 0; }
  .abstract { font-size: 18px; color: var(--ink-soft); }
  .lbl { font-family: var(--mono); font-size: 11px; letter-spacing: .18em; text-transform: uppercase; color: var(--muted); display: block; margin-bottom: 6px; }
  .sec { font-weight: 600; font-size: 24px; margin: 0 0 .4rem; }
  .hn { font-size: 16px; color: var(--blue); margin-right: .6em; font-weight: 500; }
  p { margin: 0 0 1.05rem; text-align: justify; hyphens: auto; }
  .drop::first-letter { font-size: 3.1em; line-height: .86; float: left; padding: .06em .08em 0 0; font-weight: 600; }
  .ref { font-family: var(--mono); font-size: .62em; color: var(--blue); }
  @media (max-width: 980px) {
    .page { grid-template-columns: 1fr; padding: 54px 22px 90px; }
    :global(.paper aside.sidenote) { grid-column: 1; margin: 6px 0 20px; }
  }
</style>
```

- [ ] **Step 2: Mount `Paper` in `App.svelte`** — replace the existing primary content. At the top of the `<script>` add the loaders and signals; render `Paper` when data is present.

Replace the component imports block (lines ~7-11, `ValueChainMap`…`SignalLab`) and the markup with a Paper-first render. Concretely, set the script to:

```svelte
<script lang="ts">
  import { onMount } from "svelte";
  import { loadAll } from "./lib/data";
  import { loadSignals } from "./lib/signals";
  import type { Signal } from "./lib/signals";
  import Paper from "./components/Paper.svelte";

  let error = $state<string | null>(null);
  let data = $state<Awaited<ReturnType<typeof loadAll>> | null>(null);
  let signals = $state<Signal[]>([]);

  onMount(async () => {
    try {
      [data, signals] = await Promise.all([loadAll(), loadSignals()]);
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
  });
</script>
```

And set the markup to:

```svelte
{#if error}
  <p style="font-family:monospace;padding:40px;color:#9b2d2d">Failed to load: {error}</p>
{:else if data}
  <Paper graph={data.graph} {signals} />
{:else}
  <p style="font-family:monospace;padding:40px;color:#8a8377">Loading…</p>
{/if}
```

- [ ] **Step 3: Verify compile + dev render**

Run: `cd atlas/web && npx svelte-check --tsconfig ./tsconfig.json`
Expected: 0 errors. (Unused old components are fine; they are removed in Task 8.)

- [ ] **Step 4: Commit**

```bash
git add atlas/web/src/components/Paper.svelte atlas/web/src/App.svelte
git commit -m "feat(paper): assemble Paper document and mount as primary view"
```

---

### Task 8: Playwright smoke + dead-code cleanup

**Files:**
- Create: `atlas/web/tests/paper.spec.ts`
- Delete (now-unmounted): `atlas/web/src/components/SignalLab.svelte`, `Scroller.svelte`, `Controls.svelte`, `src/stores.ts`, `src/lib/scenes.ts` — **only if** `npx svelte-check` and grep confirm no remaining imports. Otherwise leave and note in the PR.

- [ ] **Step 1: Write the smoke test**

```ts
// atlas/web/tests/paper.spec.ts
import { test, expect } from "@playwright/test";

test("working paper renders masthead, both figures, and the results table", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /Honest Signal Detection/ })).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("Abstract")).toBeVisible();
  await expect(page.locator('svg[aria-label="The AI value chain"]')).toBeVisible();
  await expect(page.locator('svg[aria-label="Volcano plot of all slope hypotheses"]')).toBeVisible();
  await expect(page.getByText("Table 1 —", { exact: false })).toBeVisible();
  await expect(page.locator(".vd.c").first()).toContainText("confirmed");
});
```

- [ ] **Step 2: Run it (build fixture data first, mirroring CI)**

Run:
```bash
cd atlas && uv run python web/tests/make_fixture_db.py /tmp/fix.duckdb && uv run python web/export_data.py --db /tmp/fix.duckdb --out web/static/data
cd web && npx playwright test paper.spec.ts
```
Expected: PASS (the fixture exports a real `signals.json`; the masthead, Figure 1, Figure 2, and Table 1 render).

- [ ] **Step 3: Remove now-dead components if unreferenced**

Run: `cd atlas/web && grep -rl "SignalLab\|Scroller\|Controls\|stores\|scenes" src/ | grep -v node_modules`
For each file with **no** remaining importer, `git rm` it. Re-run `npx svelte-check` (expect 0 errors). If any still import, leave the file and record it.

- [ ] **Step 4: Full check + commit**

```bash
cd atlas/web && npx svelte-check --tsconfig ./tsconfig.json && npm run test
git add -A
git commit -m "test(paper): playwright smoke + remove superseded map components"
```

---

## Self-Review

**Spec coverage (P1 scope):** masthead/abstract ✅ (Task 7); §1 value chain + Figure 1 ✅ (Tasks 2,6,7); §2 campaign + volcano + Table 1 ✅ (Tasks 1,5,6,7); evidence strip ✅ (Task 6, available for §4 — mounted in P2 subsections); aesthetic system ✅ (Task 3 tokens + component styles); motion (reveal-on-scroll, reduced-motion) ✅ (Task 4 + paper.css); reuse of existing loaders ✅ (Task 7); testing (vitest transforms + Playwright smoke) ✅ (Tasks 1,2,8). Deferred to P2/P3 per spec: cross-correlogram/CAR/VRP figures + export changes, forest plot, per-hypothesis §4 subsections, self-hosted fonts, scroll-linked transitions, print/a11y pass.

**Placeholder scan:** no TBD/TODO; every code step shows complete code; commands have expected output. The Task 8 deletions are explicitly conditional on a grep/`svelte-check` check rather than assumed.

**Type consistency:** `Signal` from `lib/signals` (with `stat.value`, `stat.q_value?`, `stat.n`, `verdict`) is used identically across `paper.ts`, the figures, and `Paper.svelte`. `dagLayout`/`confirmedPairs`/`volcanoPoints`/`tableRows`/`negLog10Q`/`effectSize`/`FDR_ALPHA` signatures match between Tasks 1–2 and their consumers (Tasks 5–7). `stageOrder` imported from existing `lib/stages`.

**Open decision resolved in-plan:** volcano includes only slope hypotheses with finite q; H0/H6 go to Table 1 (documented in the Figure 2 sidenote). Static DAG (not the interactive map) per the spec's P1 recommendation.
