# Atlas Working Paper — Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the working paper's body — add §3 Method, §4 Findings (a per-hypothesis subsection for all 13 hypotheses, each with a within-hypothesis coefficient plot built from its `detail_rows`), and §5 Thesis — using only data already exported. No backend changes.

**Architecture:** One new tested transform (`detailCoefficients`) plus two new components: a reusable `DetailFigure.svelte` (a within-hypothesis coefficient/forest plot of effect ± CI, q-shaded) and `Hypothesis.svelte` (one §4 subsection composing heading, verdict, evidence strip, detail figure, caveats). `Paper.svelte` gains §3/§5 prose and a §4 loop. Builds on P1 (`feat/working-paper`, through `81087ee`).

**Tech Stack:** Svelte 5 (runes), TypeScript, Vite, Zod, vitest, Playwright. No Python/export changes.

**Scope note:** P2 is deliberately backend-free. The *true* cross-correlogram (full lag sweep) and the VRP *time series* need new `export_data.py` curves; those move to **P3**.

---

## File Structure

- Modify `atlas/web/src/lib/paper.ts` — add `labelForDetailRow`, `detailCoefficients`, `DetailCoefficient`, `DetailEffect`. **Tested.**
- Create `atlas/web/src/components/paper/DetailFigure.svelte` — within-hypothesis coefficient plot.
- Create `atlas/web/src/components/paper/Hypothesis.svelte` — one §4 subsection.
- Modify `atlas/web/src/components/Paper.svelte` — add §3 Method, §4 Findings loop, §5 Thesis.
- Modify `atlas/web/tests/paper.test.ts` — vitest for the new transforms.
- Modify `atlas/web/tests/paper.spec.ts` — extend the smoke test.

Run from `atlas/web`: `npm run test` (vitest), `npx playwright test paper.spec.ts`.

---

### Task 1: `lib/paper.ts` — detail-row label + coefficient extraction

**Files:**
- Modify: `atlas/web/src/lib/paper.ts`
- Modify: `atlas/web/tests/paper.test.ts`

`detail_rows` are heterogeneous: H1/H11 have `{left,right,slope,slope_lo,slope_hi,q_value}`; H7 has
`{target,horizon,...}`; H8 `{indicator,...}`; H6 `{pair,mean_vrp,vrp_lo,vrp_hi}`. We extract a common
`{label, effect, lo, hi, passes}` so one figure renders any hypothesis's edges/cells.

- [ ] **Step 1: Write the failing test (append to `tests/paper.test.ts`)**

```ts
// append to atlas/web/tests/paper.test.ts
import { detailCoefficients, labelForDetailRow } from "../src/lib/paper";

describe("detail coefficients", () => {
  it("labels rows from their identity fields", () => {
    expect(labelForDetailRow({ left: "asml", right: "tsmc" })).toBe("asml → tsmc");
    expect(labelForDetailRow({ target: "SPY", horizon: 21 })).toBe("SPY · 21d");
    expect(labelForDetailRow({ indicator: "CAPUTLG3344S" })).toBe("CAPUTLG3344S");
    expect(labelForDetailRow({ pair: "^VIX~SPY" })).toBe("^VIX~SPY");
    expect(labelForDetailRow({ foo: 1 })).toBe("row 1");
  });

  it("extracts effect/CI/passes from slope rows", () => {
    const s = sig({ id: "H1", detail_rows: [
      { left: "asml", right: "tsmc", slope: 0.41, slope_lo: 0.12, slope_hi: 0.58, q_value: 0.04 },
      { left: "x", right: "y", slope: -0.02, slope_lo: -0.1, slope_hi: 0.06, q_value: 0.7 },
    ] });
    const cs = detailCoefficients(s);
    expect(cs[0]).toEqual({ label: "asml → tsmc", effect: 0.41, lo: 0.12, hi: 0.58, passes: true });
    expect(cs[1].passes).toBe(false);
  });

  it("falls back to mean_vrp / vrp CI for H6-style rows", () => {
    const s = sig({ id: "H6", detail_rows: [{ pair: "^VIX~SPY", mean_vrp: 0.009, vrp_lo: 0.003, vrp_hi: 0.014 }] });
    expect(detailCoefficients(s)[0]).toMatchObject({ label: "^VIX~SPY", effect: 0.009, lo: 0.003, hi: 0.014 });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlas/web && npx vitest run tests/paper.test.ts`
Expected: FAIL — `detailCoefficients`/`labelForDetailRow` are not exported.

- [ ] **Step 3: Write minimal implementation (append to `lib/paper.ts`)**

```ts
// append to atlas/web/src/lib/paper.ts
export interface DetailCoefficient {
  label: string;
  effect: number;
  lo: number | null;
  hi: number | null;
  passes: boolean; // q <= FDR_ALPHA
}

const numOr = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

export function labelForDetailRow(row: Record<string, unknown>): string {
  if (typeof row.left === "string" && typeof row.right === "string") return `${row.left} → ${row.right}`;
  if (typeof row.target === "string" && row.horizon != null) return `${row.target} · ${row.horizon}d`;
  if (typeof row.indicator === "string") return row.indicator;
  if (typeof row.name === "string") return row.name;
  if (typeof row.pair === "string") return row.pair;
  return "row 1";
}

/** Common {label, effect, lo, hi, passes} per detail row, across heterogeneous schemas. */
export function detailCoefficients(sig: Signal): DetailCoefficient[] {
  return sig.detail_rows.map((raw, i) => {
    const row = raw as Record<string, unknown>;
    const effect = numOr(row.slope) ?? numOr(row.mean_vrp) ?? numOr(row.corr) ?? 0;
    const lo = numOr(row.slope_lo) ?? numOr(row.vrp_lo);
    const hi = numOr(row.slope_hi) ?? numOr(row.vrp_hi);
    const q = numOr(row.q_value);
    const label = labelForDetailRow(row) === "row 1" ? `row ${i + 1}` : labelForDetailRow(row);
    return { label, effect, lo, hi, passes: q != null && q <= FDR_ALPHA };
  });
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd atlas/web && npx vitest run tests/paper.test.ts`
Expected: PASS (all paper transform tests green).

- [ ] **Step 5: Commit**

```bash
git add atlas/web/src/lib/paper.ts atlas/web/tests/paper.test.ts
git commit -m "feat(paper): detail-row coefficient extraction for per-hypothesis figures"
```

---

### Task 2: `DetailFigure.svelte` — within-hypothesis coefficient plot

**Files:**
- Create: `atlas/web/src/components/paper/DetailFigure.svelte`

A horizontal coefficient/forest plot: one row per detail coefficient, point = effect, whiskers = CI,
vertical line at 0; rows that clear FDR are filled blue, others hollow grey. Domain auto-scales to the
CIs. Renders nothing if there are no rows.

- [ ] **Step 1: Create the component**

```svelte
<!-- atlas/web/src/components/paper/DetailFigure.svelte -->
<script lang="ts">
  import type { Signal } from "../../lib/signals";
  import { detailCoefficients } from "../../lib/paper";
  let { signal }: { signal: Signal } = $props();

  const rows = $derived(detailCoefficients(signal));
  const W = 760;
  const rowH = 26;
  const m = { t: 14, r: 30, b: 34, l: 150 };
  const H = $derived(m.t + m.b + rows.length * rowH);
  const PW = W - m.l - m.r;
  const domain = $derived.by((): [number, number] => {
    const vals = rows.flatMap((r) => [r.effect, r.lo ?? r.effect, r.hi ?? r.effect]);
    const lo = Math.min(0, ...vals), hi = Math.max(0, ...vals);
    const pad = (hi - lo) * 0.08 || 0.1;
    return [lo - pad, hi + pad];
  });
  const xs = (v: number) => m.l + ((v - domain[0]) / (domain[1] - domain[0])) * PW;
</script>

{#if rows.length}
  <svg viewBox="0 0 {W} {H}" role="img" aria-label={`Coefficient plot for ${signal.id}`}>
    <line x1={xs(0)} y1={m.t} x2={xs(0)} y2={m.t + rows.length * rowH} stroke="var(--rule-2)" stroke-dasharray="2 4" />
    {#each rows as r, i}
      {@const y = m.t + i * rowH + rowH / 2}
      <text x={m.l - 12} {y} dy="4" text-anchor="end" font-family="var(--mono)" font-size="11" fill="var(--ink-soft)">{r.label}</text>
      {#if r.lo != null && r.hi != null}
        <line x1={xs(r.lo)} y1={y} x2={xs(r.hi)} y2={y} stroke={r.passes ? "var(--blue)" : "var(--null)"} stroke-width="1.4" />
      {/if}
      <circle cx={xs(r.effect)} cy={y} r="4" fill={r.passes ? "var(--blue)" : "#fcfbf8"} stroke={r.passes ? "var(--blue)" : "var(--null)"} stroke-width="1.4" />
    {/each}
    <line x1={m.l} y1={m.t + rows.length * rowH} x2={m.l + PW} y2={m.t + rows.length * rowH} stroke="var(--ink)" />
    <text x={m.l + PW / 2} y={H - 8} text-anchor="middle" font-family="var(--serif)" font-style="italic" font-size="13" fill="var(--ink-soft)">effect ± 95% CI (filled = clears FDR)</text>
  </svg>
{/if}
```

- [ ] **Step 2: Verify compile**

Run: `cd atlas/web && npx svelte-check --tsconfig ./tsconfig.json`
Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add atlas/web/src/components/paper/DetailFigure.svelte
git commit -m "feat(paper): within-hypothesis coefficient plot (DetailFigure)"
```

---

### Task 3: `Hypothesis.svelte` — one §4 subsection

**Files:**
- Create: `atlas/web/src/components/paper/Hypothesis.svelte`

Composes a single hypothesis: a `§4.k` heading, the claim, a verdict pill, the evidence strip, the
detail coefficient figure (wrapped as a numbered `Figure`), and caveats as a footnote-style list.

- [ ] **Step 1: Create the component**

```svelte
<!-- atlas/web/src/components/paper/Hypothesis.svelte -->
<script lang="ts">
  import type { Signal } from "../../lib/signals";
  import Figure from "./Figure.svelte";
  import EvidenceStrip from "./EvidenceStrip.svelte";
  import DetailFigure from "./DetailFigure.svelte";
  let { signal, section, figureNo }: { signal: Signal; section: string; figureNo: number } = $props();
  const cls = (v: string) => (v === "confirmed" ? "c" : v === "suggestive" ? "s" : "n");
</script>

<section class="hyp body">
  <h3 class="sub"><span class="hn num">{section}</span>{signal.title}
    <span class="vd {cls(signal.verdict)}">{signal.verdict}</span></h3>
  <p class="claim">{signal.claim}</p>
  <EvidenceStrip {signal} />
</section>

{#if signal.detail_rows.length}
  <Figure n={figureNo}>
    {#snippet caption()}
      <em>{signal.id} detail.</em> Per-edge effect with 95% confidence intervals; filled markers clear FDR control at q = 0.10.
    {/snippet}
    <DetailFigure {signal} />
  </Figure>
{/if}

<section class="hyp body">
  <ul class="caveats">
    {#each signal.caveats as c}<li>{c}</li>{/each}
  </ul>
</section>

<style>
  .sub { font-weight: 600; font-size: 19px; margin: 28px 0 .3rem; }
  .hn { font-family: var(--mono); font-size: 14px; color: var(--blue); margin-right: .5em; font-weight: 500; }
  .vd { font-family: var(--mono); font-size: 11px; text-transform: uppercase; margin-left: .5em; }
  .vd.c { color: var(--blue); } .vd.s { color: var(--suggest); } .vd.n { color: var(--muted); }
  .claim { font-style: italic; color: var(--ink-soft); margin: 0 0 .6rem; }
  .caveats { font-size: 14px; color: var(--muted); padding-left: 1.1rem; margin: 6px 0 0; }
  .caveats li { margin-bottom: 3px; }
</style>
```

- [ ] **Step 2: Verify compile**

Run: `cd atlas/web && npx svelte-check --tsconfig ./tsconfig.json`
Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add atlas/web/src/components/paper/Hypothesis.svelte
git commit -m "feat(paper): per-hypothesis §4 subsection component"
```

---

### Task 4: Wire §3 Method, §4 Findings loop, §5 Thesis into `Paper.svelte`

**Files:**
- Modify: `atlas/web/src/components/Paper.svelte`

- [ ] **Step 1: Import `Hypothesis` and add a figure counter**

In the `<script>` of `Paper.svelte`, add the import alongside the others:

```svelte
  import Hypothesis from "./paper/Hypothesis.svelte";
```

and after the existing `const n = $derived(...)` block add:

```svelte
  // §4 figures are numbered after Figures 1 (DAG) and 2 (volcano).
  const findings = $derived(signals.filter((s) => s.detail_rows.length > 0));
```

- [ ] **Step 2: Insert §3, §4, §5 after the Table 1 block** (i.e. after `<div class="body"><ResultsTable {signals} /></div>`)

```svelte
  <section class="body">
    <h2 class="sec"><span class="hn num">3</span>Method</h2>
    <p>Every verdict is the end of a fixed evidence chain: a raw contemporaneous correlation, the same
    relationship after de-beta'ing market and sector factors (M2), an out-of-sample sign-retention check,
    and a selection-aware q-value that already accounts for the lag/horizon search. A hypothesis is
    <em>confirmed</em> only when the selection-aware q clears Benjamini–Hochberg control within its family
    and the effect carries the expected sign; <em>suggestive</em> rests on the slope CI alone; everything
    else is <em>null</em>. "Contradicts" is reserved for a statistically significant reversal.<sup class="ref">3</sup></p>
  </section>
  <Sidenote n={3}>Nulls surface the closest-to-significant edge, so each card shows that even the strongest
  link does not pass — "priced in", not "not looked at".</Sidenote>

  <section class="body">
    <h2 class="sec"><span class="hn num">4</span>Findings</h2>
    <p>Each hypothesis is reported with its within-family detail: the individual edges, cells, or
    indicators that compose it, shown as effect sizes with confidence intervals.</p>
  </section>

  {#each findings as s, i}
    <Hypothesis signal={s} section={`4.${i + 1}`} figureNo={i + 3} />
  {/each}

  <section class="body">
    <h2 class="sec"><span class="hn num">5</span>Thesis</h2>
    <p>The pattern across {signals.length} hypotheses is consistent with efficient pricing of slow,
    public fundamental signals: capex, the chip cycle, and power demand are largely <em>priced in</em>
    by the time they are observable. Two exceptions survive — genuine capex→revenue propagation along
    the supply chain (H1, with H11 suggestive), and a compensated volatility risk premium (H6, H7) that
    pays for bearing stress rather than offering free alpha. The eight nulls are not gaps in the search;
    they are the finding. An honest board reports what the market has already arbitraged away.</p>
  </section>
```

- [ ] **Step 3: Verify compile + dev render**

Run: `cd atlas/web && npx svelte-check --tsconfig ./tsconfig.json`
Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
git add atlas/web/src/components/Paper.svelte
git commit -m "feat(paper): add Method, Findings (per-hypothesis), and Thesis sections"
```

---

### Task 5: Extend the Playwright smoke + full verification

**Files:**
- Modify: `atlas/web/tests/paper.spec.ts`

- [ ] **Step 1: Add assertions for §4 to the smoke test** (append inside the existing test, after the Table 1 assertion)

```ts
  // §4 Findings: at least one per-hypothesis section + its coefficient figure render
  await expect(page.getByRole("heading", { name: /Findings/ })).toBeVisible();
  await expect(page.locator('svg[aria-label^="Coefficient plot for"]').first()).toBeVisible();
  await expect(page.getByRole("heading", { name: /Thesis/ })).toBeVisible();
```

- [ ] **Step 2: Build fixture data and run the smoke test**

Run:
```bash
cd atlas && uv run python web/tests/make_fixture_db.py /tmp/fix.duckdb && uv run python web/export_data.py --db /tmp/fix.duckdb --out web/static/data
cd web && npx playwright test paper.spec.ts
```
Expected: PASS. (The fixture's single hypothesis still produces a §4 subsection + coefficient figure.)

- [ ] **Step 3: Full check + commit**

```bash
cd atlas/web && npx svelte-check --tsconfig ./tsconfig.json && npm run test
git add atlas/web/tests/paper.spec.ts
git commit -m "test(paper): smoke-cover Findings sections and coefficient figures"
```

---

## Self-Review

**Spec coverage (P2 scope):** §3 Method ✅ (Task 4) with evidence-chain explanation + sidenote; §4 Findings per-hypothesis ✅ (Tasks 1–4) — every hypothesis with `detail_rows` gets a subsection + within-hypothesis coefficient figure built from existing data; §5 Thesis ✅ (Task 4); reusable transform tested ✅ (Task 1); smoke coverage ✅ (Task 5). **Reframed from the spec:** the standalone forest-of-all-hypotheses is dropped (redundant with P1's volcano); the *true* cross-correlogram (lag sweep) and VRP *time series* are deferred to P3 because they require `export_data.py` curve additions — P2 is intentionally backend-free.

**Placeholder scan:** no TBD/TODO; every code step has complete code; commands carry expected output.

**Type consistency:** `detailCoefficients`/`labelForDetailRow`/`DetailCoefficient` defined in Task 1 are consumed unchanged in `DetailFigure` (Task 2); `Signal` (with `detail_rows`, `caveats`, `evidence_chain`, `title`, `claim`, `verdict`) is used identically across Tasks 1–4; `Figure`/`EvidenceStrip` props match the P1 components (`n`, `caption` snippet; `signal`). `FDR_ALPHA` reused from P1.

**Open item for P3:** true cross-correlogram + VRP time series (need `export_data.py` lag/horizon/series exports + fixtures); self-hosted fonts; print + a11y pass; scroll-linked figure transitions.
