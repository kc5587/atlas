# Signal Lab H0 + H1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Signal Lab board (H0: present the daily-null result + shared `signals.json` surface) and the first research card (H1: quarterly capex→downstream-revenue, sample-appropriate).

**Architecture:** A pure adapter `analysis/signals.py` turns analysis tables into `signals.json` records (evidence chain + verdict). `analysis/fundamentals_leadlag.py` computes the hardened capex→revenue statistics (YoY growth, cycle control, one-sided lead, bootstrap CI). A new Svelte `SignalLab` board renders one card per record. Each hypothesis adds one record + (if new) one chart renderer.

**Tech Stack:** Python 3.13, NumPy, pandas, DuckDB; Svelte 5 + TypeScript + Zod; pytest, vitest, Playwright.

**Specs:** `2026-06-04-atlas-signal-lab-roadmap.md`, `…-h0-daily-null-and-board.md`, `…-h1-capex-revenue.md`.

**Conventions:**
- Python tests from `atlas/`: `uv run --extra dev python -m pytest <path> -v`
- Web tests from `atlas/web/`: `npm run test`, `npm run build`
- `left`/`right` are SQL keywords — quote them as `"left"`/`"right"` in DuckDB.
- Never commit `data/`, `dist/`, `node_modules/`, caches.

---

## File Structure

| File | Responsibility |
|---|---|
| `atlas/analysis/signals.py` (create) | Pure record builders (`h0_record`, `h1_record`) + `build_signal_records(con)` DB wrapper |
| `atlas/analysis/fundamentals_leadlag.py` (create) | `yoy_growth`, `cycle_control`, `bootstrap_slope_ci`, `capex_revenue_edges` |
| `atlas/analysis/leadlag.py` (modify) | In `run()`, write a `fundamentals_leadlag` table from `capex_revenue_edges` |
| `atlas/web/export_data.py` (modify) | Emit `signals.json` |
| `atlas/web/src/lib/signals.ts` (create) | `SignalZ` schema + `loadSignals` |
| `atlas/web/src/stores.ts` (modify) | Add `"lab"` to the `mode` union |
| `atlas/web/src/components/SignalLab.svelte` (create) | Board view (cards + back button) |
| `atlas/web/src/components/SignalCard.svelte` (create) | One card: claim→mechanism→evidence→verdict→chart |
| `atlas/web/src/App.svelte` (modify) | Render `SignalLab` in `lab` mode; add a "Signal Lab" entry button |
| `atlas/tests/test_signals.py` (create) | Unit tests for record builders |
| `atlas/tests/test_fundamentals_leadlag.py` (create) | Unit tests for H1 statistics |
| `atlas/web/tests/signals.test.ts` (create) | `SignalZ` parsing tests |

**Shared `signals.json` record shape** (roadmap §3): `{id, title, claim, mechanism, horizon, verdict, evidence_chain[], stat{}, caveats[], chart{}, detail_rows[]}`. `verdict ∈ {confirmed, suggestive, null, contradicts}`.

---

## Task 1: H0 record builder (`analysis/signals.py`)

**Files:**
- Create: `atlas/analysis/signals.py`
- Test: `atlas/tests/test_signals.py`

- [ ] **Step 1: Write the failing test**

```python
# atlas/tests/test_signals.py
import pandas as pd
from analysis.signals import h0_record


def _edges_frame():
    # Two specs x two edges; M2 contemporaneous small, OOS sign 0.5, no FDR pass.
    rows = []
    for fm, contemp in [("M1_market", 0.14), ("M2_market_sector", 0.04)]:
        for left, right in [("a", "b"), ("c", "d")]:
            rows.append({
                "left": left, "right": right, "factor_model": fm,
                "corr_raw": 0.05, "corr_resid": 0.035, "corr_contemporaneous": contemp,
                "lag": 3, "q_value": 0.30, "oos_sign_rate": 0.5, "contradicts_thesis": False,
            })
    return pd.DataFrame(rows)


def test_h0_record_is_null_verdict_with_evidence_chain():
    rec = h0_record(_edges_frame())
    assert rec["id"] == "H0"
    assert rec["verdict"] == "null"
    # evidence chain ordered raw -> de-beta'd -> OOS
    stages = [e["stage"] for e in rec["evidence_chain"]]
    assert stages == ["raw contemporaneous", "sector de-beta'd", "OOS sign-retention"]
    assert rec["evidence_chain"][0]["value"] > rec["evidence_chain"][1]["value"]
    assert rec["stat"]["value"] == 0           # edges confirmed
    assert rec["stat"]["n"] == 2               # M2 edge count
    assert len(rec["detail_rows"]) == 2


def test_h0_confirmed_when_some_edge_passes():
    df = _edges_frame()
    df.loc[(df.factor_model == "M2_market_sector") & (df.left == "a"), "q_value"] = 0.01
    df.loc[(df.factor_model == "M2_market_sector") & (df.left == "a"), "oos_sign_rate"] = 0.8
    rec = h0_record(df)
    assert rec["stat"]["value"] == 1
    assert rec["verdict"] != "null"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --extra dev python -m pytest tests/test_signals.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'analysis.signals'`

- [ ] **Step 3: Implement**

```python
# atlas/analysis/signals.py
"""Adapter: turn analysis tables into Signal Lab records (evidence chain + verdict).

Record builders are PURE (DataFrame in, dict out). build_signal_records wraps the
DuckDB reads. Verdict vocabulary: confirmed | suggestive | null | contradicts.
"""
from __future__ import annotations

import pandas as pd

FDR_ALPHA = 0.10
OOS_SIGN_FLOOR = 0.6


def h0_record(leadlag_edges: pd.DataFrame) -> dict:
    m1 = leadlag_edges[leadlag_edges["factor_model"] == "M1_market"]
    m2 = leadlag_edges[leadlag_edges["factor_model"] == "M2_market_sector"]
    raw_contemp = float(m1["corr_contemporaneous"].abs().median())
    resid_contemp = float(m2["corr_contemporaneous"].abs().median())
    oos = float(m2["oos_sign_rate"].median())
    confirmed = int(((m2["q_value"] <= FDR_ALPHA) & (m2["oos_sign_rate"] >= OOS_SIGN_FLOOR)
                     & (~m2["contradicts_thesis"])).sum())
    min_q = float(m2["q_value"].min()) if len(m2) else float("nan")
    verdict = "null" if confirmed == 0 else "suggestive"
    detail = m2[["left", "right", "corr_raw", "corr_resid", "lag", "q_value",
                 "oos_sign_rate"]].to_dict("records")
    return {
        "id": "H0", "title": "Daily lead/lag is sector beta", "horizon": "daily",
        "claim": "Upstream daily returns lead downstream daily returns",
        "mechanism": "If real, fast diffusion — but daily liquid names arbitrage it away",
        "verdict": verdict,
        "evidence_chain": [
            {"stage": "raw contemporaneous", "metric": "|corr|", "value": round(raw_contemp, 3)},
            {"stage": "sector de-beta'd", "metric": "|corr|", "value": round(resid_contemp, 3)},
            {"stage": "OOS sign-retention", "metric": "rate", "value": round(oos, 3)},
        ],
        "stat": {"name": "edges_confirmed", "value": confirmed,
                 "q_value": round(min_q, 3), "n": int(len(m2))},
        "caveats": ["Daily price→price only; co-moves but does not lead beyond sector beta"],
        "chart": {"type": "edge_corr_bars", "ref": "h0"},
        "detail_rows": detail,
    }


def build_signal_records(con) -> list[dict]:  # pragma: no cover (thin DB wrapper)
    edges = con.execute(
        'SELECT "left","right",factor_model,corr_raw,corr_resid,corr_contemporaneous,'
        'lag,q_value,oos_sign_rate,contradicts_thesis FROM leadlag WHERE pair_type=\'edge\''
    ).df()
    records = [h0_record(edges)]
    return records
```

- [ ] **Step 4: Run to verify passes**

Run: `uv run --extra dev python -m pytest tests/test_signals.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add atlas/analysis/signals.py atlas/tests/test_signals.py
git commit -m "feat: H0 signal record builder (daily-null evidence chain + verdict)"
```

---

## Task 2: Export `signals.json`

**Files:**
- Modify: `atlas/web/export_data.py:100-108`
- Test: manual (covered by Task 9 smoke + Task 3 web parse test against a fixture)

- [ ] **Step 1: Add the export**

In `atlas/web/export_data.py`, after the `series.json` write (line ~100), add:

```python
    from analysis.signals import build_signal_records
    signals = build_signal_records(con)
    (out_dir / "signals.json").write_text(json.dumps(signals, default=str))
```

- [ ] **Step 2: Verify it runs against the live DB**

Run from `atlas/`:
```bash
uv run python web/export_data.py --db data/atlas.duckdb --out /tmp/atlas_sig
uv run python -c "import json; r=json.load(open('/tmp/atlas_sig/signals.json')); print(r[0]['id'], r[0]['verdict'], r[0]['stat'])"
```
Expected: `H0 null {...'value': 0...}` (0 confirmed edges, matching the Priority 1 result).

- [ ] **Step 3: Commit**

```bash
git add atlas/web/export_data.py
git commit -m "feat: export signals.json from analysis.signals"
```

---

## Task 3: Web `SignalZ` schema + loader

**Files:**
- Create: `atlas/web/src/lib/signals.ts`
- Test: `atlas/web/tests/signals.test.ts`

- [ ] **Step 1: Write the failing test**

```typescript
// atlas/web/tests/signals.test.ts
import { describe, expect, it } from "vitest";
import { parseSignals } from "../src/lib/signals";

const valid = [{
  id: "H0", title: "Daily lead/lag is sector beta", claim: "x", mechanism: "y",
  horizon: "daily", verdict: "null",
  evidence_chain: [{ stage: "raw", metric: "|corr|", value: 0.14 }],
  stat: { name: "edges_confirmed", value: 0, q_value: 0.17, n: 19 },
  caveats: ["c"], chart: { type: "edge_corr_bars", ref: "h0" }, detail_rows: [],
}];

describe("signals parsing", () => {
  it("parses a valid signal record", () => {
    const s = parseSignals(valid);
    expect(s[0].verdict).toBe("null");
    expect(s[0].evidence_chain[0].value).toBe(0.14);
  });
  it("rejects an invalid verdict", () => {
    const bad = [{ ...valid[0], verdict: "amazing" }];
    expect(() => parseSignals(bad)).toThrow();
  });
});
```

- [ ] **Step 2: Run to verify failure**

Run (from `atlas/web/`): `npm run test -- tests/signals.test.ts`
Expected: FAIL — cannot resolve `../src/lib/signals`.

- [ ] **Step 3: Implement**

```typescript
// atlas/web/src/lib/signals.ts
import { z } from "zod";

export const VerdictZ = z.enum(["confirmed", "suggestive", "null", "contradicts"]);
export const EvidenceStepZ = z.object({
  stage: z.string(), metric: z.string(), value: z.number(),
});
export const SignalZ = z.object({
  id: z.string(), title: z.string(), claim: z.string(), mechanism: z.string(),
  horizon: z.string(), verdict: VerdictZ,
  evidence_chain: z.array(EvidenceStepZ),
  stat: z.object({
    name: z.string(), value: z.number(),
    q_value: z.number().nullable().optional(),
    ci: z.tuple([z.number(), z.number()]).nullable().optional(),
    n: z.number(),
  }),
  caveats: z.array(z.string()),
  chart: z.object({ type: z.string(), ref: z.string() }),
  detail_rows: z.array(z.record(z.any())),
});
export type Signal = z.infer<typeof SignalZ>;

export function parseSignals(raw: unknown): Signal[] {
  return SignalZ.array().parse(raw);
}

export async function loadSignals(base = "data"): Promise<Signal[]> {
  const r = await fetch(`${base}/signals.json`);
  if (!r.ok) throw new Error(`failed to load signals: ${r.status}`);
  return parseSignals(await r.json());
}
```

- [ ] **Step 4: Run to verify passes**

Run (from `atlas/web/`): `npm run test -- tests/signals.test.ts`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add atlas/web/src/lib/signals.ts atlas/web/tests/signals.test.ts
git commit -m "feat: SignalZ schema and signals loader"
```

---

## Task 4: Signal Lab board UI

**Files:**
- Modify: `atlas/web/src/stores.ts:6`
- Create: `atlas/web/src/components/SignalCard.svelte`
- Create: `atlas/web/src/components/SignalLab.svelte`
- Modify: `atlas/web/src/App.svelte`

- [ ] **Step 1: Add `lab` to the mode union**

`atlas/web/src/stores.ts` line 6:

```typescript
export const mode = writable<"story" | "explore" | "lab">("story");
```

- [ ] **Step 2: Create `SignalCard.svelte`**

```svelte
<!-- atlas/web/src/components/SignalCard.svelte -->
<script lang="ts">
  import type { Signal } from "../lib/signals";
  let { signal }: { signal: Signal } = $props();
  const badge = $derived({
    confirmed: "#82b366", suggestive: "#d79b00", null: "#7d90a8", contradicts: "#b5563a",
  }[signal.verdict] ?? "#7d90a8");
</script>

<article class="card">
  <header>
    <h3>{signal.id} · {signal.title}</h3>
    <span class="badge" style="background:{badge}">{signal.verdict}</span>
  </header>
  <p class="claim"><b>Claim:</b> {signal.claim}</p>
  <p class="mech"><b>Mechanism:</b> {signal.mechanism}</p>
  <ol class="chain">
    {#each signal.evidence_chain as step}
      <li>{step.stage}: <b>{step.value}</b> <span>{step.metric}</span></li>
    {/each}
  </ol>
  <p class="stat">
    {signal.stat.name} = {signal.stat.value}
    {#if signal.stat.ci}[{signal.stat.ci[0]}, {signal.stat.ci[1]}]{/if}
    {#if signal.stat.q_value != null} · q={signal.stat.q_value}{/if}
    · n={signal.stat.n}
  </p>
  {#each signal.caveats as c}<p class="caveat">⚠ {c}</p>{/each}
</article>

<style>
  .card { background:#111a2b; color:#e8eef6; border-radius:12px; padding:1rem 1.2rem;
    margin:0 0 1rem; box-shadow:0 4px 18px rgba(0,0,0,.4); }
  header { display:flex; justify-content:space-between; align-items:center; gap:1rem; }
  h3 { margin:0; font-size:1rem; }
  .badge { font-size:.7rem; text-transform:uppercase; letter-spacing:.06em;
    padding:.15rem .5rem; border-radius:6px; color:#0d1422; font-weight:700; }
  .claim,.mech { margin:.4rem 0; font-size:.85rem; }
  .chain { margin:.5rem 0; padding-left:1.1rem; font-size:.82rem; }
  .chain span { opacity:.5; }
  .stat { font-variant-numeric:tabular-nums; font-size:.82rem; opacity:.9; }
  .caveat { font-size:.74rem; color:#b58a6a; margin:.3rem 0 0; }
</style>
```

- [ ] **Step 3: Create `SignalLab.svelte`**

```svelte
<!-- atlas/web/src/components/SignalLab.svelte -->
<script lang="ts">
  import { onMount } from "svelte";
  import { loadSignals, type Signal } from "../lib/signals";
  import { mode } from "../stores";
  import SignalCard from "./SignalCard.svelte";
  let signals = $state<Signal[]>([]);
  let error = $state<string | null>(null);
  onMount(async () => {
    try { signals = await loadSignals(); }
    catch (e) { error = e instanceof Error ? e.message : String(e); }
  });
</script>

<section class="lab">
  <header class="lab-head">
    <h2>Signal Lab</h2>
    <button onclick={() => mode.set("story")}>← Back to map</button>
  </header>
  {#if error}
    <p class="err">Couldn’t load signals: {error}</p>
  {:else}
    {#each signals as s (s.id)}<SignalCard signal={s} />{/each}
  {/if}
  <p class="disclaimer">The value chain is specified ex-post; these test propagation
    given the chain, not its ex-ante discoverability.</p>
</section>

<style>
  .lab { position:fixed; inset:0; z-index:7; overflow-y:auto; background:#0d1422;
    padding:1.2rem; max-width:760px; margin:0 auto; }
  .lab-head { display:flex; justify-content:space-between; align-items:center; }
  h2 { color:#e8eef6; margin:.2rem 0 1rem; }
  button { background:#1b2740; color:#9fb3c8; border:0; border-radius:8px;
    padding:.4rem .8rem; cursor:pointer; }
  .err { color:#b5563a; }
  .disclaimer { color:#7d90a8; font-size:.72rem; margin-top:1.5rem; }
</style>
```

- [ ] **Step 4: Wire into `App.svelte`**

Add the import, render the board in `lab` mode, and add an entry button. In the `<script>`:

```typescript
  import SignalLab from "./components/SignalLab.svelte";
```

In the markup, inside the `{:else}` data-loaded block, add (alongside the existing layers):

```svelte
    {#if $mode === "lab"}
      <SignalLab />
    {:else}
      <button class="lab-entry" onclick={() => mode.set("lab")}>Signal Lab</button>
    {/if}
```

Add to `App.svelte` `<style>`:

```css
  .lab-entry { position: fixed; top: 1rem; left: 1rem; z-index: 6;
    background: #1b2740; color: #cfe0f5; border: 0; border-radius: 8px;
    padding: .4rem .8rem; cursor: pointer; }
```

- [ ] **Step 5: Type-check + build**

Run (from `atlas/web/`): `npx svelte-check --tsconfig ./tsconfig.json && npm run build`
Expected: 0 errors (pre-existing a11y warnings OK).

- [ ] **Step 6: Commit**

```bash
git add atlas/web/src/stores.ts atlas/web/src/components/SignalCard.svelte atlas/web/src/components/SignalLab.svelte atlas/web/src/App.svelte
git commit -m "feat: Signal Lab board view with hypothesis cards"
```

---

## Task 5: E2E smoke for the board

**Files:**
- Modify: `atlas/web/tests/smoke.spec.ts`

- [ ] **Step 1: Write the failing e2e test**

Append to `atlas/web/tests/smoke.spec.ts`:

```typescript
test("Signal Lab opens and shows the H0 card", async ({ page }) => {
  await page.goto("/");
  await page.locator("button.lab-entry").click();
  await expect(page.getByRole("heading", { name: "Signal Lab" })).toBeVisible();
  await expect(page.getByText(/Daily lead\/lag is sector beta/)).toBeVisible();
});
```

- [ ] **Step 2: Generate signals.json into the dev fixture, then run**

Run from `atlas/`:
```bash
uv run python web/export_data.py --db data/atlas.duckdb --out web/static/data
```
Then from `atlas/web/`: `npm run e2e -- tests/smoke.spec.ts`
Expected: all smoke tests pass including the new one.

> Note: this regenerates `web/static/data/` from the live DB. That directory is the committed dev fixture; commit it only if intended (Task 9 covers the final regen). For this step it provides `signals.json` so the e2e can load it.

- [ ] **Step 3: Commit**

```bash
git add atlas/web/tests/smoke.spec.ts
git commit -m "test: e2e smoke for Signal Lab board"
```

---

## Task 6: H1 — YoY growth + cycle control

**Files:**
- Create: `atlas/analysis/fundamentals_leadlag.py`
- Test: `atlas/tests/test_fundamentals_leadlag.py`

- [ ] **Step 1: Write the failing tests**

```python
# atlas/tests/test_fundamentals_leadlag.py
import numpy as np
import pandas as pd
from analysis.fundamentals_leadlag import yoy_growth, cycle_control


def _q(vals, start="2015-03-31"):
    idx = pd.date_range(start, periods=len(vals), freq="QE")
    return pd.Series(vals, index=idx)


def test_yoy_growth_is_four_quarter_log_diff():
    s = _q([100, 110, 120, 130, 200, 220, 240, 260])  # year 2 = 2x year 1
    g = yoy_growth(s)
    assert len(g) == 4                      # first 4 dropped
    np.testing.assert_allclose(g.iloc[0], np.log(200 / 100), rtol=1e-9)


def test_cycle_control_residual_orthogonal_to_factor():
    rng = np.random.default_rng(0)
    cycle = _q(rng.standard_normal(30))
    target = 1.5 * cycle + _q(rng.standard_normal(30))
    resid = cycle_control(target, cycle)
    aligned = pd.concat([resid.rename("r"), cycle.rename("c")], axis=1, join="inner").dropna()
    assert abs(np.corrcoef(aligned["r"], aligned["c"])[0, 1]) < 1e-6
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --extra dev python -m pytest tests/test_fundamentals_leadlag.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```python
# atlas/analysis/fundamentals_leadlag.py
"""H1: hardened quarterly capex -> downstream revenue lead/lag.

YoY-growth transform (stationarity) + cycle control (de-beta analog) + one-sided
lead search over [1,4] quarters + bootstrap slope CI. Sample is small (~20-40
quarters) so we report effect sizes + CIs, NOT walk-forward.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def yoy_growth(level: pd.Series) -> pd.Series:
    """Year-over-year log growth (4-quarter difference); removes seasonality."""
    s = level.sort_index().astype(float)
    g = np.log(s) - np.log(s.shift(4))
    return g.dropna()


def cycle_control(target_growth: pd.Series, cycle_growth: pd.Series) -> pd.Series:
    """Residual of target on [const, cycle] — the fundamental de-beta analog."""
    df = pd.concat([target_growth.rename("y"), cycle_growth.rename("c")],
                   axis=1, join="inner").dropna()
    if len(df) < 3:
        return pd.Series(dtype=float)
    A = np.column_stack([np.ones(len(df)), df["c"].to_numpy()])
    beta, *_ = np.linalg.lstsq(A, df["y"].to_numpy(), rcond=None)
    return pd.Series(df["y"].to_numpy() - A @ beta, index=df.index)
```

- [ ] **Step 4: Run to verify passes**

Run: `uv run --extra dev python -m pytest tests/test_fundamentals_leadlag.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add atlas/analysis/fundamentals_leadlag.py atlas/tests/test_fundamentals_leadlag.py
git commit -m "feat: H1 yoy_growth + cycle_control (fundamental de-beta analog)"
```

---

## Task 7: H1 — slope CI + per-edge capex→revenue

**Files:**
- Modify: `atlas/analysis/fundamentals_leadlag.py`
- Test: `atlas/tests/test_fundamentals_leadlag.py`

- [ ] **Step 1: Write the failing tests**

Append to `atlas/tests/test_fundamentals_leadlag.py`:

```python
from analysis.fundamentals_leadlag import bootstrap_slope_ci, capex_revenue_edge


def test_bootstrap_slope_ci_brackets_true_slope():
    rng = np.random.default_rng(1)
    x = rng.standard_normal(120)
    y = 0.8 * x + 0.2 * rng.standard_normal(120)
    lo, hi, slope = bootstrap_slope_ci(x, y, block=2, iters=400, seed=3)
    assert lo < 0.8 < hi
    assert lo > 0                       # CI excludes 0 for a real relationship

def test_capex_revenue_edge_detects_lead_and_direction():
    rng = np.random.default_rng(2)
    n = 40
    capex_g = _q(rng.standard_normal(n))
    # downstream revenue growth = upstream capex growth lagged 2 quarters
    rev_g = capex_g.shift(2) + 0.3 * _q(rng.standard_normal(n))
    cycle = _q(rng.standard_normal(n))
    out = capex_revenue_edge(capex_g, rev_g, cycle, lag_min=1, lag_max=4,
                             iters=300, seed=5)
    assert out["lag"] == 2
    assert out["slope"] > 0
    assert out["contradicts_thesis"] is False
    assert out["n_quarters"] > 0
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --extra dev python -m pytest tests/test_fundamentals_leadlag.py -v`
Expected: FAIL — `ImportError` on `bootstrap_slope_ci`.

- [ ] **Step 3: Implement**

Append to `atlas/analysis/fundamentals_leadlag.py`:

```python
from analysis.significance import _corr_at_lag, _signed_peak, selection_aware


def bootstrap_slope_ci(x: np.ndarray, y: np.ndarray, *, block: int, iters: int,
                       seed: int, ci: float = 0.90) -> tuple[float, float, float]:
    """Block-bootstrap CI for the OLS slope of y on x (moving blocks of pairs)."""
    x = np.asarray(x, float); y = np.asarray(y, float)
    n = len(x)
    def slope(xs, ys):
        A = np.column_stack([np.ones(len(xs)), xs])
        b, *_ = np.linalg.lstsq(A, ys, rcond=None)
        return b[1]
    point = slope(x, y)
    rng = np.random.default_rng(seed)
    nblocks = int(np.ceil(n / block))
    draws = []
    for _ in range(iters):
        starts = rng.integers(0, max(1, n - block + 1), size=nblocks)
        idx = np.concatenate([np.arange(s, s + block) for s in starts])[:n]
        draws.append(slope(x[idx], y[idx]))
    lo = float(np.percentile(draws, (1 - ci) / 2 * 100))
    hi = float(np.percentile(draws, (1 + ci) / 2 * 100))
    return lo, hi, float(point)


def capex_revenue_edge(capex_growth: pd.Series, rev_growth: pd.Series,
                       cycle_growth: pd.Series, *, lag_min: int, lag_max: int,
                       iters: int, seed: int) -> dict:
    """One edge: capex growth (lead) vs cycle-controlled revenue growth."""
    rev_resid = cycle_control(rev_growth, cycle_growth)
    paired = pd.concat([capex_growth.rename("x"), rev_resid.rename("y")],
                       axis=1, join="inner").dropna()
    if len(paired) < lag_max + 5:
        return {"lag": 0, "corr": float("nan"), "slope": float("nan"),
                "slope_ci": [float("nan"), float("nan")], "p_selection": 1.0,
                "contradicts_thesis": False, "n_quarters": int(len(paired))}
    x, y = paired["x"].to_numpy(), paired["y"].to_numpy()
    lag, corr = _signed_peak(x, y, lag_min, lag_max)
    sig = selection_aware(x, y, lag_min=lag_min, lag_max=lag_max, iters=iters,
                          seed=seed, block=2)
    # align at the chosen lag for slope
    xs, ys = x[: len(x) - lag], y[lag:]
    lo, hi, slope = bootstrap_slope_ci(xs, ys, block=2, iters=iters, seed=seed)
    return {
        "lag": int(lag), "corr": float(corr), "slope": slope, "slope_ci": [lo, hi],
        "p_selection": sig["p_selection"], "contradicts_thesis": sig["contradicts_thesis"],
        "n_quarters": int(len(paired)),
    }
```

- [ ] **Step 4: Run to verify passes**

Run: `uv run --extra dev python -m pytest tests/test_fundamentals_leadlag.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add atlas/analysis/fundamentals_leadlag.py atlas/tests/test_fundamentals_leadlag.py
git commit -m "feat: H1 bootstrap slope CI + per-edge capex->revenue estimator"
```

---

## Task 8: H1 table + record + chart

**Files:**
- Modify: `atlas/analysis/leadlag.py` (`run()`)
- Modify: `atlas/analysis/signals.py`
- Modify: `atlas/analysis/fundamentals_leadlag.py` (add `capex_revenue_edges` driver)
- Modify: `atlas/tests/test_signals.py`

- [ ] **Step 1: Write the failing test for the H1 record + verdict**

Append to `atlas/tests/test_signals.py`:

```python
from analysis.signals import h1_record


def _h1_rows():
    # one strong edge (suggestive), one contradicting
    return pd.DataFrame([
        {"left": "applied_materials", "right": "tsmc", "lag": 2, "corr": 0.4,
         "slope": 0.6, "slope_lo": 0.2, "slope_hi": 1.0, "p_selection": 0.03,
         "q_value": 0.06, "contradicts_thesis": False, "n_quarters": 34},
        {"left": "nvidia", "right": "microsoft", "lag": 1, "corr": -0.1,
         "slope": -0.2, "slope_lo": -0.5, "slope_hi": 0.1, "p_selection": 0.6,
         "q_value": 0.6, "contradicts_thesis": True, "n_quarters": 30},
    ])


def test_h1_record_verdict_and_chain():
    rec = h1_record(_h1_rows())
    assert rec["id"] == "H1"
    assert rec["verdict"] in {"confirmed", "suggestive", "null", "contradicts"}
    assert rec["stat"]["n"] == 2
    assert rec["chart"]["type"] == "capex_revenue_overlay"
    assert len(rec["detail_rows"]) == 2
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --extra dev python -m pytest tests/test_signals.py::test_h1_record_verdict_and_chain -v`
Expected: FAIL — `ImportError` on `h1_record`.

- [ ] **Step 3: Implement the H1 driver, record, and table write**

Append to `atlas/analysis/fundamentals_leadlag.py`:

```python
import json as _json


def capex_revenue_edges(fundamentals: pd.DataFrame, nodes: pd.DataFrame,
                        edges: pd.DataFrame, *, iters: int, seed: int) -> pd.DataFrame:
    """Driver: per eligible edge, hardened capex->revenue stats. Quarterly lags 1-4.

    Cycle factor = leave-one-out cross-sectional mean of downstream revenue growth.
    """
    def series(ticker, col):
        sub = fundamentals.loc[fundamentals["ticker"] == ticker, ["period_end", col]].dropna()
        if sub.empty:
            return pd.Series(dtype=float)
        return pd.Series(sub[col].to_numpy(float),
                         index=pd.to_datetime(sub["period_end"])).sort_index()

    def ticker_of(node_id):
        row = nodes.loc[nodes["id"] == node_id]
        return _json.loads(row["tickers"].iloc[0])[0] if not row.empty else ""

    # revenue YoY growth per ticker (for the cycle factor)
    rev_growth = {}
    for t in fundamentals["ticker"].unique():
        g = yoy_growth(series(t, "revenue"))
        if not g.empty:
            rev_growth[t] = g

    rows = []
    for e in edges.itertuples():
        ut, dt = ticker_of(e.from_id), ticker_of(e.to_id)
        cg = yoy_growth(series(ut, "capex"))
        rg = rev_growth.get(dt)
        if cg.empty or rg is None:
            continue
        peers = [g for t, g in rev_growth.items() if t != dt]
        if not peers:
            continue
        cycle = pd.concat(peers, axis=1, join="inner").dropna().mean(axis=1)
        out = capex_revenue_edge(cg, rg, cycle, lag_min=1, lag_max=4, iters=iters, seed=seed)
        out.update({"left": e.from_id, "right": e.to_id})
        rows.append(out)
    df = pd.DataFrame(rows)
    if not df.empty:
        from analysis.leadlag import bh_fdr
        df["q_value"] = bh_fdr(df["p_selection"].to_numpy())
        df["slope_lo"] = df["slope_ci"].apply(lambda c: c[0])
        df["slope_hi"] = df["slope_ci"].apply(lambda c: c[1])
        df = df.drop(columns=["slope_ci"])
    return df
```

Append to `atlas/analysis/signals.py`:

```python
def h1_record(rows: pd.DataFrame) -> dict:
    n = int(len(rows))
    # Eligible = enough quarters AND a finite slope (short/degenerate edges excluded).
    elig = rows[(rows["n_quarters"] > 0) & rows["slope"].notna()]
    confirmed = elig[(elig["q_value"] <= FDR_ALPHA) & (elig["slope"] > 0)
                     & (elig["slope_lo"] > 0) & (~elig["contradicts_thesis"])]
    suggestive = elig[(elig["slope"] > 0) & (elig["slope_lo"] > 0)]
    if len(confirmed):
        verdict, best = "confirmed", confirmed.sort_values("q_value").iloc[0]
    elif len(suggestive):
        verdict, best = "suggestive", suggestive.sort_values("p_selection").iloc[0]
    elif elig["contradicts_thesis"].any():
        verdict, best = "contradicts", elig.iloc[0]
    else:
        verdict = "null"
        best = elig.iloc[0] if len(elig) else rows.iloc[0]
    return {
        "id": "H1", "title": "Capex → downstream revenue", "horizon": "quarterly",
        "claim": "Upstream capex leads downstream revenue by 1–4 quarters",
        "mechanism": "Real lead times; markets update on quarterly guidance",
        "verdict": verdict,
        "evidence_chain": [
            {"stage": "raw |corr|", "metric": "|corr|", "value": round(float(elig["corr"].abs().median()), 3) if len(elig) else 0.0},
            {"stage": "best edge corr", "metric": "corr", "value": round(float(best["corr"]), 3)},
            {"stage": "best edge slope", "metric": "slope", "value": round(float(best["slope"]), 3)},
        ],
        "stat": {"name": "slope", "value": round(float(best["slope"]), 3),
                 "ci": [round(float(best["slope_lo"]), 3), round(float(best["slope_hi"]), 3)],
                 "q_value": round(float(best["q_value"]), 3), "n": n},
        "caveats": [f"~{int(elig['n_quarters'].median()) if len(elig) else 0} quarters/edge → CIs, no walk-forward",
                    "ASML/TSM excluded (no SEC fundamentals)"],
        "chart": {"type": "capex_revenue_overlay", "ref": "h1"},
        "detail_rows": elig[["left", "right", "lag", "corr", "slope", "slope_lo",
                             "slope_hi", "q_value", "n_quarters"]].to_dict("records"),
    }
```

Update `build_signal_records` in `signals.py` to append H1 when its table exists:

```python
def build_signal_records(con) -> list[dict]:  # pragma: no cover
    edges = con.execute(
        'SELECT "left","right",factor_model,corr_raw,corr_resid,corr_contemporaneous,'
        'lag,q_value,oos_sign_rate,contradicts_thesis FROM leadlag WHERE pair_type=\'edge\''
    ).df()
    records = [h0_record(edges)]
    has_h1 = con.execute("SELECT count(*) FROM information_schema.tables "
                         "WHERE table_name='fundamentals_leadlag'").fetchone()[0] > 0
    if has_h1:
        h1 = con.execute('SELECT * FROM fundamentals_leadlag').df()
        if len(h1):
            records.append(h1_record(h1))
    return records
```

In `atlas/analysis/leadlag.py` `run()`, after the `leadlag` table write, add:

```python
    from analysis.fundamentals_leadlag import capex_revenue_edges
    h1 = capex_revenue_edges(fundamentals, nodes, edges,
                             iters=BOOTSTRAP_ITERS, seed=RANDOM_SEED)
    con.register("h1t", h1)
    con.execute("CREATE OR REPLACE TABLE fundamentals_leadlag AS SELECT * FROM h1t")
    con.unregister("h1t")
    print(f"fundamentals_leadlag: wrote {len(h1)} capex->revenue edge rows")
```

- [ ] **Step 4: Run to verify passes**

Run: `uv run --extra dev python -m pytest tests/test_signals.py tests/test_fundamentals_leadlag.py -v`
Expected: PASS (all)

- [ ] **Step 5: Add the H1 chart renderer**

In `SignalCard.svelte`, after the stat paragraph, render a minimal overlay when
`chart.type === "capex_revenue_overlay"` using `detail_rows` (a compact per-edge
bar of slope with its CI). Append inside the card markup:

```svelte
  {#if signal.chart.type === "capex_revenue_overlay"}
    <ul class="edges">
      {#each signal.detail_rows as r}
        <li><span>{r.left} → {r.right}</span>
          <b>slope {Number(r.slope).toFixed(2)}</b>
          <span class="ci">[{Number(r.slope_lo).toFixed(2)}, {Number(r.slope_hi).toFixed(2)}]</span>
          <span class="lag">lag {r.lag}Q · n={r.n_quarters}</span></li>
      {/each}
    </ul>
  {/if}
```

Add to `SignalCard.svelte` `<style>`:

```css
  .edges { list-style:none; padding:0; margin:.5rem 0 0; font-size:.78rem; }
  .edges li { display:flex; gap:.5rem; justify-content:space-between; padding:.15rem 0;
    border-top:1px solid #1b2740; }
  .edges .ci,.edges .lag { opacity:.55; }
```

- [ ] **Step 6: Build the web app**

Run (from `atlas/web/`): `npx svelte-check --tsconfig ./tsconfig.json && npm run build`
Expected: 0 errors.

- [ ] **Step 7: Commit**

```bash
git add atlas/analysis/leadlag.py atlas/analysis/signals.py atlas/analysis/fundamentals_leadlag.py atlas/tests/test_signals.py atlas/web/src/components/SignalCard.svelte
git commit -m "feat: H1 capex->revenue table, signal record, and card chart"
```

---

## Task 9: End-to-end smoke + coverage

**Files:** none (verification only) — plus an optional fixture regen commit.

- [ ] **Step 1: Run the analysis end-to-end**

Run from `atlas/`:
```bash
uv run make analyze
uv run python web/export_data.py --db data/atlas.duckdb --out /tmp/atlas_sig2
uv run python -c "import json; r={x['id']:x for x in json.load(open('/tmp/atlas_sig2/signals.json'))}; print('H0', r['H0']['verdict']); print('H1', r['H1']['verdict'], r['H1']['stat'])"
```
Expected: prints `H0 null` and an `H1 <verdict>` with a slope/CI. The H1 verdict is whatever the data says (likely `suggestive` or `null`) — record it; do not tune to force a result.

- [ ] **Step 2: Coverage gate**

Run from `atlas/`:
```bash
uv run --extra dev python -m pytest --cov=analysis --cov-report=term-missing \
  tests/test_signals.py tests/test_fundamentals_leadlag.py
```
Expected: pass; new modules ≥ 80%.

- [ ] **Step 3: Full web test suite**

Run (from `atlas/web/`): `npm run test && npm run build`
Expected: all pass.

- [ ] **Step 4: Report the H1 finding**

Record the realized H1 verdict + slope/CI in the commit body (this is the actual
research result). Do not commit `data/` or regenerated `web/static/data` unless
intentionally refreshing the fixture.

- [ ] **Step 5: Commit (verification note only, if anything changed)**

```bash
git add -A -- ':!atlas/data' ':!atlas/web/static/data'
git commit -m "chore: Signal Lab H0+H1 end-to-end verified (H1 verdict: <fill in>)" || echo "nothing to commit"
```

---

## Self-Review Notes

- **H0 builds the shared surface** (signals.py, signals.json, SignalZ, board); H1 adds exactly one record + one chart branch — matches roadmap §6.
- **H1 is sample-appropriate:** effect size + bootstrap CI + selection-aware p + FDR; **no walk-forward** (spec §4). Verdict mapping (confirmed/suggestive/null/contradicts) implemented in `h1_record`.
- **Reuses Priority 1 internals:** `selection_aware`, `_signed_peak`, `_corr_at_lag`, `bh_fdr` — imported, not duplicated.
- **Eligibility:** ASML/TSM drop out (no fundamentals); FDR family = eligible edges; `n` shown on the card.
- **Honesty:** the H1 verdict is reported as-is; Step 1/4 explicitly forbid tuning to force a result. Ex-post universe caveat shown on the board.
- **Not in this plan:** H3/H2/H4 (their outlines get detailed when reached), map recolor for H0 (optional polish, deferred — the H0 card already tells the story).
