# Atlas Front-End v2 — Data-Story + Explorable Map Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the laggy Streamlit app with a fast, static scrollytelling data-story whose centerpiece is an animated, stage-column value-chain map that unlocks into a free-explore mode.

**Architecture:** A Python `export_data.py` step turns the DuckDB marts into compact static JSON. A Vite + Svelte 5 + TypeScript site loads that JSON once and renders everything client-side (no server, no lag): a stage-column map (D3), a scroll-driven narrative (scrollama) with 7 scenes, and a free-explore mode. The nightly workflow exports JSON, builds the site, and deploys to GitHub Pages. The data pipeline (ingest/dbt/analysis) is untouched.

**Tech Stack:** Python (duckdb — already a dep) for export; Node 20 + Vite + Svelte 5 (runes) + TypeScript; `d3` (selection/zoom/scale/shape), `scrollama`, `zod`; Vitest (unit) + Playwright (smoke). No d3-dag.

**Spec:** `docs/superpowers/specs/2026-06-02-atlas-datastory-map-design.md`

---

## File Structure (new)

```
atlas/
  web/
    export_data.py            # duckdb marts -> static/data/*.json
    package.json · vite.config.ts · tsconfig.json · svelte.config.js · index.html
    playwright.config.ts
    src/
      main.ts · App.svelte · stores.ts
      lib/ types.ts · data.ts · layout.ts · leadlag.ts · scenes.ts
      components/ ValueChainMap.svelte · Scroller.svelte · NodePanel.svelte · LeadLagChart.svelte · Controls.svelte
    static/data/              # generated; gitignored
    tests/ layout.test.ts · leadlag.test.ts · data.test.ts · smoke.spec.ts · test_export_data.py
  Makefile                    # MODIFY: web-data / web-dev / web-build targets
  .github/workflows/          # MODIFY update-data.yml; ADD pages deploy
  app/streamlit_app.py        # DELETE (Task 11)
```

**Type contract (`src/lib/types.ts`, mirrored by `export_data.py` output):**
- `Node = { id; name; stage: "equipment"|"foundry"|"chips"|"cloud"; region; tickers: string[]; cik?: string; criticality: number }`
- `Edge = { from_id; to_id; relationship; note; evidence; as_of }`
- `LeadLag = { pair_type; left; right; lag: number; corr: number; p_value: number; q_value: number; n_eff: number; stable: boolean }`
- `SeriesPoint = { date: string; value: number }`; `Series = { prices: Record<string, SeriesPoint[]>; fundamentals?: Record<string, {capex:SeriesPoint[];revenue:SeriesPoint[];gross_margin:SeriesPoint[]}> }`
- `Meta = { generated_at; schema_version; tickers: string[]; stages: string[] }`

---

## Task 1: Data export — `web/export_data.py`

**Files:**
- Create: `atlas/web/export_data.py`
- Test: `atlas/web/tests/test_export_data.py`

- [ ] **Step 1: Write the failing test**

```python
# atlas/web/tests/test_export_data.py
import json
from pathlib import Path

import duckdb
import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from export_data import downsample, export_all  # noqa: E402


def _fixture_db(path: Path) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE graph_nodes(id VARCHAR, name VARCHAR, tickers VARCHAR, stage VARCHAR, region VARCHAR, cik VARCHAR)")
    con.execute("INSERT INTO graph_nodes VALUES ('nvidia','NVIDIA','[\"NVDA\"]','chips','US','0001045810')")
    con.execute("CREATE TABLE graph_edges(from_id VARCHAR,to_id VARCHAR,relationship VARCHAR,note VARCHAR,evidence VARCHAR,as_of VARCHAR)")
    con.execute("INSERT INTO graph_edges VALUES ('nvidia','nvidia','supplies','','','2024-01-01')")
    con.execute("CREATE TABLE leadlag(pair_type VARCHAR,\"left\" VARCHAR,\"right\" VARCHAR,lag INT,corr DOUBLE,p_value DOUBLE,q_value DOUBLE,n_eff INT,stable BOOLEAN)")
    con.execute("INSERT INTO leadlag VALUES ('edge','nvidia','nvidia',2,0.5,0.01,0.05,300,true)")
    con.execute("CREATE TABLE returns(ticker VARCHAR, date DATE, log_return DOUBLE)")
    con.execute("INSERT INTO returns SELECT 'NVDA', DATE '2020-01-01' + INTERVAL (i) DAY, 0.001 FROM range(0,400) t(i)")
    return con


def test_downsample_reduces_points():
    pts = [{"date": f"2020-01-{i:02d}", "value": float(i)} for i in range(1, 29)]
    out = downsample(pts, max_points=10)
    assert len(out) <= 10
    assert out[0] == pts[0] and out[-1] == pts[-1]  # endpoints preserved


def test_export_all_writes_expected_files(tmp_path):
    db = tmp_path / "atlas.duckdb"
    con = _fixture_db(db)
    out = tmp_path / "data"
    export_all(con, out)
    con.close()
    for name in ("graph.json", "leadlag.json", "series.json", "meta.json"):
        assert (out / name).exists(), name
    graph = json.loads((out / "graph.json").read_text())
    assert graph["nodes"][0]["tickers"] == ["NVDA"]   # JSON-parsed, not a string
    assert "criticality" in graph["nodes"][0]
    assert graph["edges"][0]["from_id"] == "nvidia"
    meta = json.loads((out / "meta.json").read_text())
    assert meta["schema_version"] == "2"


def test_export_all_missing_required_table_raises(tmp_path):
    db = tmp_path / "x.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE graph_nodes(id VARCHAR)")  # missing edges/leadlag
    with pytest.raises(RuntimeError, match="missing required table"):
        export_all(con, tmp_path / "out")
    con.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlas && uv run --extra dev python -m pytest web/tests/test_export_data.py -v`
Expected: FAIL — cannot import `export_data`.

- [ ] **Step 3: Write minimal implementation**

```python
# atlas/web/export_data.py
from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb

SCHEMA_VERSION = "2"
REQUIRED = ["graph_nodes", "graph_edges", "leadlag"]
DEFAULT_DB = Path(__file__).resolve().parents[1] / "data" / "atlas.duckdb"
DEFAULT_OUT = Path(__file__).resolve().parent / "static" / "data"


def _has_table(con: duckdb.DuckDBPyConnection, name: str) -> bool:
    return con.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = ?", [name]
    ).fetchone()[0] > 0


def downsample(points: list[dict], *, max_points: int) -> list[dict]:
    """Evenly thin a time series to <= max_points, always keeping first and last."""
    n = len(points)
    if max_points < 2 or n <= max_points:
        return points
    step = (n - 1) / (max_points - 1)
    idx = sorted({round(i * step) for i in range(max_points)} | {0, n - 1})
    return [points[i] for i in idx]


def _criticality(node_id: str, edges: list[dict]) -> float:
    deg = sum(1 for e in edges if e["from_id"] == node_id or e["to_id"] == node_id)
    return float(deg)


def export_all(con: duckdb.DuckDBPyConnection, out_dir: Path) -> None:
    for t in REQUIRED:
        if not _has_table(con, t):
            raise RuntimeError(f"missing required table: {t}")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    edges = con.execute(
        "SELECT from_id, to_id, relationship, note, evidence, as_of FROM graph_edges"
    ).df().to_dict("records")
    # cik only exists after Layer 2; select it conditionally so this works pre- and post-L2.
    has_cik = con.execute(
        "SELECT count(*) FROM information_schema.columns "
        "WHERE table_name='graph_nodes' AND column_name='cik'"
    ).fetchone()[0] > 0
    cik_sel = "COALESCE(cik, '') AS cik" if has_cik else "'' AS cik"
    raw_nodes = con.execute(
        f"SELECT id, name, tickers, stage, region, {cik_sel} FROM graph_nodes"
    ).df().to_dict("records")
    nodes = []
    for n in raw_nodes:
        nodes.append({
            "id": n["id"], "name": n["name"],
            "tickers": json.loads(n["tickers"]) if n["tickers"] else [],
            "stage": n["stage"], "region": n["region"],
            "cik": n["cik"] or None,
            "criticality": _criticality(n["id"], edges),
        })
    (out_dir / "graph.json").write_text(json.dumps({"nodes": nodes, "edges": edges}))

    leadlag = con.execute("SELECT * FROM leadlag").df().to_dict("records")
    (out_dir / "leadlag.json").write_text(json.dumps(leadlag, default=str))

    prices: dict[str, list[dict]] = {}
    if _has_table(con, "returns"):
        df = con.execute(
            "SELECT ticker, date, sum(log_return) OVER (PARTITION BY ticker ORDER BY date) AS cum "
            "FROM returns ORDER BY ticker, date"
        ).df()
        for ticker, grp in df.groupby("ticker"):
            pts = [{"date": str(d.date()), "value": float(v)}
                   for d, v in zip(grp["date"], grp["cum"])]
            prices[ticker] = downsample(pts, max_points=400)
    series: dict = {"prices": prices}

    if _has_table(con, "fundamentals_quarterly"):
        fdf = con.execute(
            "SELECT ticker, period_end, revenue, capex, gross_margin "
            "FROM fundamentals_quarterly ORDER BY ticker, period_end"
        ).df()
        fund: dict = {}
        for ticker, grp in fdf.groupby("ticker"):
            def col(c):
                return [{"date": str(d.date()), "value": (None if v != v else float(v))}
                        for d, v in zip(grp["period_end"], grp[c])]
            fund[ticker] = {"revenue": col("revenue"), "capex": col("capex"),
                            "gross_margin": col("gross_margin")}
        series["fundamentals"] = fund
    (out_dir / "series.json").write_text(json.dumps(series))

    tickers = sorted({t for n in nodes for t in n["tickers"]})
    stages = ["equipment", "foundry", "chips", "cloud"]
    meta = {
        "generated_at": con.execute("SELECT now()").fetchone()[0].isoformat(),
        "schema_version": SCHEMA_VERSION, "tickers": tickers, "stages": stages,
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, default=str))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()
    con = duckdb.connect(args.db, read_only=True)
    export_all(con, Path(args.out))
    con.close()
    print(f"export_data: wrote JSON to {args.out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd atlas && uv run --extra dev python -m pytest web/tests/test_export_data.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add atlas/web/export_data.py atlas/web/tests/test_export_data.py
git commit -m "feat(web): duckdb -> static JSON export with tests"
```

---

## Task 2: Front-end scaffold + config

**Files:**
- Create: `atlas/web/package.json`, `vite.config.ts`, `tsconfig.json`, `svelte.config.js`, `index.html`, `src/main.ts`

- [ ] **Step 1: Create `package.json`**

```json
{
  "name": "atlas-web",
  "private": true,
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "e2e": "playwright test"
  },
  "devDependencies": {
    "@sveltejs/vite-plugin-svelte": "^4",
    "@playwright/test": "^1.45",
    "svelte": "^5",
    "svelte-check": "^4",
    "typescript": "^5.5",
    "vite": "^5.4",
    "vitest": "^2"
  },
  "dependencies": {
    "d3": "^7.9",
    "scrollama": "^3.2",
    "zod": "^3.23"
  }
}
```

- [ ] **Step 2: Create `vite.config.ts`** (relative base so it works on GitHub Pages subpaths)

```ts
import { svelte } from "@sveltejs/vite-plugin-svelte";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [svelte()],
  base: "./",
  publicDir: "static",          // copies static/data/*.json into dist/data/ — REQUIRED
  build: { outDir: "dist" },
});
```

- [ ] **Step 3: Create `tsconfig.json`, `svelte.config.js`, `index.html`, `src/main.ts`**

```json
// tsconfig.json
{
  "compilerOptions": {
    "target": "ES2022", "module": "ESNext", "moduleResolution": "bundler",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "strict": true, "skipLibCheck": true, "verbatimModuleSyntax": true,
    "isolatedModules": true, "types": ["svelte", "vite/client"]
  },
  "include": ["src", "tests"]
}
```

```js
// svelte.config.js
import { vitePreprocess } from "@sveltejs/vite-plugin-svelte";
export default { preprocess: vitePreprocess() };
```

```html
<!-- index.html -->
<!doctype html>
<html lang="en">
  <head><meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Atlas — the AI value chain</title></head>
  <body><div id="app"></div><script type="module" src="/src/main.ts"></script></body>
</html>
```

```ts
// src/main.ts
import { mount } from "svelte";
import App from "./App.svelte";
export default mount(App, { target: document.getElementById("app")! });
```

- [ ] **Step 4: Install and verify build tooling**

Run: `cd atlas/web && npm install && npx vitest --version && npx playwright install --with-deps chromium`
Expected: install completes; vitest prints a version.

- [ ] **Step 5: Commit**

```bash
git add atlas/web/package.json atlas/web/package-lock.json atlas/web/vite.config.ts atlas/web/tsconfig.json atlas/web/svelte.config.js atlas/web/index.html atlas/web/src/main.ts
git commit -m "feat(web): vite + svelte 5 + ts scaffold"
```

---

## Task 3: Types + data loader (`types.ts`, `data.ts`)

**Files:**
- Create: `atlas/web/src/lib/types.ts`, `atlas/web/src/lib/data.ts`
- Test: `atlas/web/tests/data.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// atlas/web/tests/data.test.ts
import { describe, expect, it } from "vitest";
import { parseGraph, parseLeadLag } from "../src/lib/data";

describe("data parsing", () => {
  it("parses a valid graph", () => {
    const g = parseGraph({
      nodes: [{ id: "nvidia", name: "NVIDIA", tickers: ["NVDA"], stage: "chips", region: "US", criticality: 3 }],
      edges: [{ from_id: "tsmc", to_id: "nvidia", relationship: "supplies", note: "", evidence: "", as_of: "2024-01-01" }],
    });
    expect(g.nodes[0].stage).toBe("chips");
    expect(g.edges[0].from_id).toBe("tsmc");
  });

  it("rejects an invalid stage", () => {
    expect(() => parseGraph({
      nodes: [{ id: "x", name: "X", tickers: [], stage: "banana", region: "US", criticality: 0 }],
      edges: [],
    })).toThrow();
  });

  it("parses lead/lag rows", () => {
    const ll = parseLeadLag([
      { pair_type: "edge", left: "a", right: "b", lag: 2, corr: 0.4, p_value: 0.01, q_value: 0.05, n_eff: 300, stable: true },
    ]);
    expect(ll[0].stable).toBe(true);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlas/web && npx vitest run tests/data.test.ts`
Expected: FAIL — cannot resolve `../src/lib/data`.

- [ ] **Step 3: Write `types.ts` and `data.ts`**

```ts
// src/lib/types.ts
import { z } from "zod";

export const StageZ = z.enum(["equipment", "foundry", "chips", "cloud"]);
export const NodeZ = z.object({
  id: z.string(), name: z.string(), tickers: z.array(z.string()),
  stage: StageZ, region: z.string(), cik: z.string().nullable().optional(),
  criticality: z.number(),
});
export const EdgeZ = z.object({
  from_id: z.string(), to_id: z.string(), relationship: z.string(),
  note: z.string(), evidence: z.string(), as_of: z.string(),
});
export const GraphZ = z.object({ nodes: z.array(NodeZ), edges: z.array(EdgeZ) });
export const LeadLagZ = z.object({
  pair_type: z.string(), left: z.string(), right: z.string(), lag: z.number(),
  corr: z.number(), p_value: z.number(), q_value: z.number(),
  n_eff: z.number(), stable: z.boolean(),
});
export const SeriesPointZ = z.object({ date: z.string(), value: z.number().nullable() });
export const SeriesZ = z.object({
  prices: z.record(z.array(SeriesPointZ)),
  fundamentals: z.record(z.object({
    capex: z.array(SeriesPointZ), revenue: z.array(SeriesPointZ),
    gross_margin: z.array(SeriesPointZ),
  })).optional(),
});
export const MetaZ = z.object({
  generated_at: z.string(), schema_version: z.string(),
  tickers: z.array(z.string()), stages: z.array(z.string()),
});

export type Stage = z.infer<typeof StageZ>;
export type Node = z.infer<typeof NodeZ>;
export type Edge = z.infer<typeof EdgeZ>;
export type Graph = z.infer<typeof GraphZ>;
export type LeadLag = z.infer<typeof LeadLagZ>;
export type Series = z.infer<typeof SeriesZ>;
export type Meta = z.infer<typeof MetaZ>;
```

```ts
// src/lib/data.ts
import { GraphZ, LeadLagZ, MetaZ, SeriesZ } from "./types";
import type { Graph, LeadLag, Meta, Series } from "./types";

export function parseGraph(raw: unknown): Graph { return GraphZ.parse(raw); }
export function parseLeadLag(raw: unknown): LeadLag[] { return LeadLagZ.array().parse(raw); }
export function parseSeries(raw: unknown): Series { return SeriesZ.parse(raw); }
export function parseMeta(raw: unknown): Meta { return MetaZ.parse(raw); }

async function getJSON(path: string): Promise<unknown> {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`failed to load ${path}: ${r.status}`);
  return r.json();
}

export async function loadAll(base = "data") {
  const [graph, leadlag, series, meta] = await Promise.all([
    getJSON(`${base}/graph.json`).then(parseGraph),
    getJSON(`${base}/leadlag.json`).then(parseLeadLag),
    getJSON(`${base}/series.json`).then(parseSeries),
    getJSON(`${base}/meta.json`).then(parseMeta),
  ]);
  return { graph, leadlag, series, meta };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd atlas/web && npx vitest run tests/data.test.ts`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add atlas/web/src/lib/types.ts atlas/web/src/lib/data.ts atlas/web/tests/data.test.ts
git commit -m "feat(web): typed + zod-validated data loaders"
```

---

## Task 4: Stage-column layout (`layout.ts`)

**Files:**
- Create: `atlas/web/src/lib/layout.ts`
- Test: `atlas/web/tests/layout.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// atlas/web/tests/layout.test.ts
import { describe, expect, it } from "vitest";
import { computeLayout } from "../src/lib/layout";
import type { Graph } from "../src/lib/types";

const g: Graph = {
  nodes: [
    { id: "asml", name: "ASML", tickers: ["ASML"], stage: "equipment", region: "NL", criticality: 1 },
    { id: "tsmc", name: "TSMC", tickers: ["TSM"], stage: "foundry", region: "TW", criticality: 2 },
    { id: "nvidia", name: "NVIDIA", tickers: ["NVDA"], stage: "chips", region: "US", criticality: 3 },
    { id: "msft", name: "Microsoft", tickers: ["MSFT"], stage: "cloud", region: "US", criticality: 2 },
  ],
  edges: [
    { from_id: "asml", to_id: "tsmc", relationship: "supplies", note: "", evidence: "", as_of: "" },
    { from_id: "tsmc", to_id: "nvidia", relationship: "supplies", note: "", evidence: "", as_of: "" },
    { from_id: "nvidia", to_id: "msft", relationship: "supplies", note: "", evidence: "", as_of: "" },
    // back-edge: cloud builds its own silicon -> chips
    { from_id: "msft", to_id: "nvidia", relationship: "supplies", note: "in-house", evidence: "", as_of: "" },
  ],
};

describe("computeLayout", () => {
  it("assigns x by stage order (left to right)", () => {
    const { nodes } = computeLayout(g, { width: 800, height: 400 });
    const by = Object.fromEntries(nodes.map((n) => [n.id, n.x]));
    expect(by["asml"]).toBeLessThan(by["tsmc"]);
    expect(by["tsmc"]).toBeLessThan(by["nvidia"]);
    expect(by["nvidia"]).toBeLessThan(by["msft"]);
  });

  it("gives every node a finite position", () => {
    const { nodes } = computeLayout(g, { width: 800, height: 400 });
    for (const n of nodes) {
      expect(Number.isFinite(n.x)).toBe(true);
      expect(Number.isFinite(n.y)).toBe(true);
    }
  });

  it("flags back-edges (downstream stage -> upstream stage)", () => {
    const { edges } = computeLayout(g, { width: 800, height: 400 });
    const back = edges.find((e) => e.from_id === "msft" && e.to_id === "nvidia");
    expect(back?.isBack).toBe(true);
    const fwd = edges.find((e) => e.from_id === "asml" && e.to_id === "tsmc");
    expect(fwd?.isBack).toBe(false);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlas/web && npx vitest run tests/layout.test.ts`
Expected: FAIL — cannot resolve `layout`.

- [ ] **Step 3: Write `layout.ts`**

```ts
// src/lib/layout.ts
import type { Edge, Graph, Node, Stage } from "./types";

const STAGE_ORDER: Stage[] = ["equipment", "foundry", "chips", "cloud"];

export interface PositionedNode extends Node { x: number; y: number; col: number; }
export interface RoutedEdge extends Edge { isBack: boolean; }
export interface LayoutOpts { width: number; height: number; padding?: number; }

export function computeLayout(graph: Graph, opts: LayoutOpts) {
  const pad = opts.padding ?? 60;
  const cols = STAGE_ORDER;
  const colX = (i: number) =>
    cols.length === 1 ? opts.width / 2 : pad + (i * (opts.width - 2 * pad)) / (cols.length - 1);

  const byStage = new Map<Stage, Node[]>();
  for (const s of cols) byStage.set(s, []);
  for (const n of graph.nodes) (byStage.get(n.stage) ?? byStage.get("chips"))!.push(n);

  // initial y: evenly spaced within each column
  const pos = new Map<string, PositionedNode>();
  cols.forEach((s, ci) => {
    const list = byStage.get(s)!;
    list.forEach((n, i) => {
      const y = list.length === 1
        ? opts.height / 2
        : pad + (i * (opts.height - 2 * pad)) / (list.length - 1);
      pos.set(n.id, { ...n, x: colX(ci), y, col: ci });
    });
  });

  // one barycenter pass: order each column by mean neighbour y to reduce crossings
  const neighbours = new Map<string, string[]>();
  const addNb = (a: string, b: string) => {
    let arr = neighbours.get(a);
    if (!arr) neighbours.set(a, (arr = []));
    arr.push(b);
  };
  for (const e of graph.edges) { addNb(e.from_id, e.to_id); addNb(e.to_id, e.from_id); }
  cols.forEach((s, ci) => {
    const list = byStage.get(s)!.map((n) => pos.get(n.id)!);
    list.sort((a, b) => bary(a, neighbours, pos) - bary(b, neighbours, pos));
    list.forEach((n, i) => {
      n.y = list.length === 1
        ? opts.height / 2
        : pad + (i * (opts.height - 2 * pad)) / (list.length - 1);
    });
  });

  const colOf = (id: string) => pos.get(id)?.col ?? 0;
  const edges: RoutedEdge[] = graph.edges.map((e) => ({
    ...e,
    isBack: colOf(e.from_id) > colOf(e.to_id),
  }));

  return { nodes: [...pos.values()], edges };
}

function bary(n: PositionedNode, nb: Map<string, string[]>, pos: Map<string, PositionedNode>): number {
  const ns = (nb.get(n.id) ?? []).map((id) => pos.get(id)?.y).filter((y): y is number => y != null);
  return ns.length ? ns.reduce((a, b) => a + b, 0) / ns.length : n.y;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd atlas/web && npx vitest run tests/layout.test.ts`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add atlas/web/src/lib/layout.ts atlas/web/tests/layout.test.ts
git commit -m "feat(web): stage-column layout with barycenter ordering + back-edge flag"
```

---

## Task 5: Lead/lag edge styling (`leadlag.ts`)

**Files:**
- Create: `atlas/web/src/lib/leadlag.ts`
- Test: `atlas/web/tests/leadlag.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// atlas/web/tests/leadlag.test.ts
import { describe, expect, it } from "vitest";
import { edgeStyle, leadLagFor } from "../src/lib/leadlag";
import type { LeadLag } from "../src/lib/types";

const rows: LeadLag[] = [
  { pair_type: "edge", left: "asml", right: "tsmc", lag: 5, corr: 0.6, p_value: 0.001, q_value: 0.02, n_eff: 300, stable: true },
  { pair_type: "edge", left: "tsmc", right: "nvidia", lag: 3, corr: 0.2, p_value: 0.3, q_value: 0.4, n_eff: 300, stable: false },
];

describe("leadlag styling", () => {
  it("finds the row for an edge", () => {
    expect(leadLagFor(rows, "asml", "tsmc")?.lag).toBe(5);
    expect(leadLagFor(rows, "x", "y")).toBeUndefined();
  });
  it("bolds FDR-significant + stable edges", () => {
    const sig = edgeStyle(rows[0], 0.1);
    const ns = edgeStyle(rows[1], 0.1);
    expect(sig.width).toBeGreaterThan(ns.width);
    expect(sig.significant).toBe(true);
    expect(ns.significant).toBe(false);
  });
  it("derives pulse delay from |lag|", () => {
    expect(edgeStyle(rows[0], 0.1).pulseDelayMs).toBeGreaterThan(0);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlas/web && npx vitest run tests/leadlag.test.ts`
Expected: FAIL.

- [ ] **Step 3: Write `leadlag.ts`**

```ts
// src/lib/leadlag.ts
import type { LeadLag } from "./types";

export function leadLagFor(rows: LeadLag[], from: string, to: string): LeadLag | undefined {
  return rows.find(
    (r) => (r.left === from && r.right === to) || (r.left === to && r.right === from),
  );
}

export interface EdgeStyle { width: number; significant: boolean; pulseDelayMs: number; opacity: number; }

export function edgeStyle(row: LeadLag | undefined, alpha: number): EdgeStyle {
  if (!row) return { width: 1, significant: false, pulseDelayMs: 0, opacity: 0.35 };
  const significant = row.q_value <= alpha && row.stable;
  return {
    width: significant ? 3.5 : 1.25,
    significant,
    pulseDelayMs: Math.max(0, Math.abs(row.lag)) * 120,
    opacity: significant ? 0.95 : 0.4,
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd atlas/web && npx vitest run tests/leadlag.test.ts`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add atlas/web/src/lib/leadlag.ts atlas/web/tests/leadlag.test.ts
git commit -m "feat(web): lead/lag edge styling (significance + pulse delay)"
```

---

## Task 6: Stores + scenes (`stores.ts`, `scenes.ts`)

**Files:**
- Create: `atlas/web/src/stores.ts`, `atlas/web/src/lib/scenes.ts`

- [ ] **Step 1: Create `scenes.ts`** (pure scene definitions; the camera/highlight contract)

```ts
// src/lib/scenes.ts
export interface Scene {
  id: string;
  title: string;
  body: string;
  highlightNodeIds?: string[];   // empty/undefined = whole graph
  highlightPath?: [string, string][];
  focusStage?: string;
  showLeadLag?: boolean;
  showCapex?: boolean;
}

export const SCENES: Scene[] = [
  { id: "whole", title: "The AI value chain", body: "Every layer, from lithography to the cloud." },
  { id: "path", title: "One path", body: "ASML enables TSMC, which fabricates NVIDIA, which powers Microsoft.",
    highlightPath: [["asml", "tsmc"], ["tsmc", "nvidia"], ["nvidia", "msft"]] },
  { id: "bottlenecks", title: "Bottlenecks & geography", body: "A few chokepoints carry the chain: EUV, advanced packaging, Taiwan.",
    focusStage: "foundry" },
  { id: "leadlag", title: "Measured lead/lag", body: "Upstream moves show up downstream days later.", showLeadLag: true },
  { id: "capex", title: "The upstream pull", body: "Hyperscaler capex pulls orders back up the chain.", showCapex: true },
  { id: "forgotten", title: "Forgotten plays", body: "Power, cooling, fiber — the unpriced edges (coming in Layer 3)." },
  { id: "explore", title: "Explore", body: "Roam the chain yourself." },
];
```

- [ ] **Step 2: Create `stores.ts`**

```ts
// src/stores.ts
import { writable } from "svelte/store";
import type { Graph, LeadLag, Series, Meta } from "./lib/types";

export const activeScene = writable<number>(0);
export const mode = writable<"story" | "explore">("story");
export const selectedNode = writable<string | null>(null);
export const dataset = writable<{ graph: Graph; leadlag: LeadLag[]; series: Series; meta: Meta } | null>(null);
```

- [ ] **Step 3: Verify type-check**

Run: `cd atlas/web && npx svelte-check --tsconfig ./tsconfig.json`
Expected: 0 errors (warnings about unused are acceptable at this stage).

- [ ] **Step 4: Commit**

```bash
git add atlas/web/src/stores.ts atlas/web/src/lib/scenes.ts
git commit -m "feat(web): scene definitions and svelte stores"
```

---

## Task 7: Map component (`ValueChainMap.svelte`)

**Files:**
- Create: `atlas/web/src/components/ValueChainMap.svelte`

> Rendering component; no unit test (covered by the Playwright smoke). Keep math in `layout.ts`/`leadlag.ts` (already tested).

- [ ] **Step 1: Create `ValueChainMap.svelte`**

```svelte
<script lang="ts">
  import { onMount } from "svelte";
  import * as d3 from "d3";
  import { computeLayout } from "../lib/layout";
  import { edgeStyle, leadLagFor } from "../lib/leadlag";
  import type { Graph, LeadLag } from "../lib/types";

  let { graph, leadlag, highlight = null, showLeadLag = false, mode = "story", onSelect = (_: string) => {} }:
    { graph: Graph; leadlag: LeadLag[]; highlight?: Set<string> | null; showLeadLag?: boolean;
      mode?: "story" | "explore"; onSelect?: (id: string) => void } = $props();

  let svgEl: SVGSVGElement;
  let width = $state(960);
  let height = $state(560);

  $effect(() => {
    if (!svgEl) return;
    const { nodes, edges } = computeLayout(graph, { width, height });
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const svg = d3.select(svgEl);
    svg.selectAll("*").remove();
    const g = svg.append("g");

    if (mode === "explore") {
      svg.call(
        d3.zoom<SVGSVGElement, unknown>().scaleExtent([0.5, 4])
          .on("zoom", (e) => g.attr("transform", e.transform.toString())),
      );
    }

    g.selectAll("path.edge").data(edges).join("path")
      .attr("class", "edge")
      .attr("d", (e) => {
        const a = byId.get(e.from_id)!, b = byId.get(e.to_id)!;
        const mx = (a.x + b.x) / 2;
        return `M${a.x},${a.y} C${mx},${a.y} ${mx},${b.y} ${b.x},${b.y}`;
      })
      .attr("fill", "none")
      .attr("stroke", (e) => (e.isBack ? "#c0883a" : "#7aa2c8"))
      .attr("stroke-dasharray", (e) => (e.isBack ? "4 3" : null))
      .attr("stroke-width", (e) => (showLeadLag ? edgeStyle(leadLagFor(leadlag, e.from_id, e.to_id), 0.1).width : 1.25))
      .attr("opacity", (e) => dim(e.from_id, e.to_id) ? 0.08 : (showLeadLag ? edgeStyle(leadLagFor(leadlag, e.from_id, e.to_id), 0.1).opacity : 0.5));

    const node = g.selectAll("g.node").data(nodes).join("g")
      .attr("class", "node")
      .attr("transform", (n) => `translate(${n.x},${n.y})`)
      .style("cursor", "pointer")
      .on("click", (_, n) => onSelect(n.id));
    node.append("circle")
      .attr("r", (n) => 8 + 3 * Math.sqrt(n.criticality))
      .attr("fill", (n) => stageColor(n.stage))
      .attr("opacity", (n) => (dimNode(n.id) ? 0.12 : 1));
    node.append("text").text((n) => n.name).attr("y", -16)
      .attr("text-anchor", "middle").attr("font-size", 11)
      .attr("fill", "#e8eef6").attr("opacity", (n) => (dimNode(n.id) ? 0.15 : 1));

    function dimNode(id: string) { return highlight != null && !highlight.has(id); }
    function dim(a: string, b: string) { return highlight != null && !(highlight.has(a) && highlight.has(b)); }
  });

  function stageColor(s: string) {
    return { equipment: "#6c8ebf", foundry: "#9673a6", chips: "#82b366", cloud: "#d79b00" }[s] ?? "#888";
  }
</script>

<svg bind:this={svgEl} viewBox={`0 0 ${width} ${height}`} style="width:100%;height:100%;background:#0d1422" role="img" aria-label="AI value chain map"></svg>
```

- [ ] **Step 2: Type-check**

Run: `cd atlas/web && npx svelte-check --tsconfig ./tsconfig.json`
Expected: 0 errors.

- [ ] **Step 3: Commit**

```bash
git add atlas/web/src/components/ValueChainMap.svelte
git commit -m "feat(web): D3 stage-column value-chain map component"
```

---

## Task 8: Scroller + scene wiring (`Scroller.svelte`)

**Files:**
- Create: `atlas/web/src/components/Scroller.svelte`

- [ ] **Step 1: Create `Scroller.svelte`**

```svelte
<script lang="ts">
  import { onMount } from "svelte";
  import scrollama from "scrollama";
  import { SCENES } from "../lib/scenes";
  import { activeScene, mode } from "../stores";

  let container: HTMLDivElement;
  onMount(() => {
    const scroller = scrollama();
    scroller.setup({ step: ".scene-step", offset: 0.6 }).onStepEnter(({ index }) => {
      activeScene.set(index);
      mode.set(SCENES[index].id === "explore" ? "explore" : "story");
    });
    const onResize = () => scroller.resize();
    window.addEventListener("resize", onResize);
    return () => { window.removeEventListener("resize", onResize); scroller.destroy(); };
  });
</script>

<div bind:this={container} class="scroller">
  {#each SCENES as s (s.id)}
    <section class="scene-step">
      <h2>{s.title}</h2>
      <p>{s.body}</p>
    </section>
  {/each}
</div>

<style>
  .scroller { position: relative; z-index: 2; width: min(420px, 90vw); margin-left: 2rem; }
  .scene-step { min-height: 90vh; display: flex; flex-direction: column; justify-content: center;
    color: #e8eef6; padding: 1.5rem; background: rgba(13,20,34,0.72); border-radius: 12px; margin: 18vh 0; }
  h2 { font-size: 1.6rem; margin: 0 0 .5rem; }
  p { font-size: 1.05rem; line-height: 1.5; opacity: .9; }
</style>
```

- [ ] **Step 2: Type-check + commit**

Run: `cd atlas/web && npx svelte-check --tsconfig ./tsconfig.json`
Expected: 0 errors.

```bash
git add atlas/web/src/components/Scroller.svelte
git commit -m "feat(web): scrollama scene scroller"
```

---

## Task 9: Drill-down panel, controls, inline chart, App shell

**Files:**
- Create: `atlas/web/src/components/NodePanel.svelte`, `Controls.svelte`, `LeadLagChart.svelte`
- Create/Replace: `atlas/web/src/App.svelte`

- [ ] **Step 1: Create `LeadLagChart.svelte`**

```svelte
<script lang="ts">
  import * as d3 from "d3";
  import type { SeriesPoint } from "../lib/types";
  let { points = [] as { date: string; value: number | null }[] } = $props();
  let el: SVGSVGElement;
  $effect(() => {
    if (!el) return;
    const w = 320, h = 120, m = 24;
    const data = points.filter((p) => p.value != null) as { date: string; value: number }[];
    const svg = d3.select(el); svg.selectAll("*").remove();
    if (!data.length) return;
    const x = d3.scaleLinear([0, data.length - 1], [m, w - m]);
    const y = d3.scaleLinear(d3.extent(data, (d) => d.value) as [number, number], [h - m, m]);
    const line = d3.line<{ value: number }>().x((_, i) => x(i)).y((d) => y(d.value));
    svg.append("path").datum(data).attr("fill", "none").attr("stroke", "#82b366").attr("stroke-width", 2).attr("d", line as any);
  });
</script>
<svg bind:this={el} viewBox="0 0 320 120" style="width:100%"></svg>
```

- [ ] **Step 2: Create `NodePanel.svelte`**

```svelte
<script lang="ts">
  import type { Graph, Series } from "../lib/types";
  import LeadLagChart from "./LeadLagChart.svelte";
  let { graph, series, nodeId, onClose = () => {} }:
    { graph: Graph; series: Series; nodeId: string; onClose?: () => void } = $props();
  const node = $derived(graph.nodes.find((n) => n.id === nodeId));
  const ticker = $derived(node?.tickers[0] ?? "");
  const price = $derived(series.prices[ticker] ?? []);
</script>

{#if node}
  <aside class="panel">
    <button class="close" onclick={onClose}>×</button>
    <h3>{node.name}</h3>
    <p class="meta">{node.stage} · {node.region} · {node.tickers.join(", ")}</p>
    <h4>Cumulative return</h4>
    <LeadLagChart points={price} />
    {#if series.fundamentals?.[ticker]}
      <h4>Capex</h4><LeadLagChart points={series.fundamentals[ticker].capex} />
    {/if}
  </aside>
{/if}

<style>
  .panel { position: absolute; top: 1rem; right: 1rem; z-index: 5; width: 360px;
    background: #111a2b; color: #e8eef6; padding: 1rem 1.2rem; border-radius: 12px; box-shadow: 0 8px 30px rgba(0,0,0,.5); }
  .close { position: absolute; top: .5rem; right: .6rem; background: none; border: 0; color: #9fb3c8; font-size: 1.3rem; cursor: pointer; }
  .meta { opacity: .7; font-size: .85rem; }
</style>
```

- [ ] **Step 3: Create `Controls.svelte`** (explore-mode stage filter)

```svelte
<script lang="ts">
  let { stages = [] as string[], active = new Set<string>(), onToggle = (_: string) => {} }:
    { stages?: string[]; active?: Set<string>; onToggle?: (s: string) => void } = $props();
</script>
<div class="controls">
  {#each stages as s (s)}
    <button class:on={active.has(s)} onclick={() => onToggle(s)}>{s}</button>
  {/each}
</div>
<style>
  .controls { position: absolute; bottom: 1rem; left: 1rem; z-index: 5; display: flex; gap: .4rem; }
  button { background: #1b2740; color: #cdd9e8; border: 1px solid #2c3e60; border-radius: 999px; padding: .3rem .8rem; cursor: pointer; }
  button.on { background: #2c4a78; color: #fff; }
</style>
```

- [ ] **Step 4: Create `App.svelte`** (wires it all together)

```svelte
<script lang="ts">
  import { onMount } from "svelte";
  import { loadAll } from "./lib/data";
  import { SCENES } from "./lib/scenes";
  import { activeScene, mode, selectedNode, dataset } from "./stores";
  import ValueChainMap from "./components/ValueChainMap.svelte";
  import Scroller from "./components/Scroller.svelte";
  import NodePanel from "./components/NodePanel.svelte";
  import Controls from "./components/Controls.svelte";

  let error = $state<string | null>(null);
  let data = $state<Awaited<ReturnType<typeof loadAll>> | null>(null);
  onMount(async () => {
    try { data = await loadAll(); dataset.set(data); }
    catch (e) { error = e instanceof Error ? e.message : String(e); }
  });

  const scene = $derived(SCENES[$activeScene]);
  const highlight = $derived.by(() => {
    if (!scene) return null;
    if (scene.highlightPath) return new Set(scene.highlightPath.flat());
    if (scene.focusStage && data) return new Set(data.graph.nodes.filter((n) => n.stage === scene.focusStage).map((n) => n.id));
    return null;
  });
</script>

<main>
  {#if error}
    <div class="state">Couldn’t load data: {error}</div>
  {:else if !data}
    <div class="state">Loading the value chain…</div>
  {:else}
    <div class="map-layer">
      <ValueChainMap graph={data.graph} leadlag={data.leadlag}
        highlight={$mode === "explore" ? null : highlight}
        showLeadLag={scene?.showLeadLag ?? false}
        mode={$mode}
        onSelect={(id) => selectedNode.set(id)} />
    </div>
    {#if $mode === "story"}<Scroller />{/if}
    {#if $selectedNode}
      <NodePanel graph={data.graph} series={data.series} nodeId={$selectedNode} onClose={() => selectedNode.set(null)} />
    {/if}
    {#if $mode === "explore"}<Controls stages={data.meta.stages} />{/if}
  {/if}
</main>

<style>
  :global(body) { margin: 0; background: #0d1422; font-family: system-ui, sans-serif; }
  .map-layer { position: fixed; inset: 0; z-index: 1; }
  .state { position: fixed; inset: 0; display: grid; place-items: center; color: #9fb3c8; }
  main { position: relative; }
</style>
```

- [ ] **Step 5: Type-check, build, commit**

Run: `cd atlas/web && npx svelte-check --tsconfig ./tsconfig.json && npm run build`
Expected: 0 type errors; `dist/` produced.

```bash
git add atlas/web/src/components/NodePanel.svelte atlas/web/src/components/Controls.svelte atlas/web/src/components/LeadLagChart.svelte atlas/web/src/App.svelte
git commit -m "feat(web): node panel, controls, inline chart, app shell"
```

---

## Task 10: Playwright smoke + Makefile + gitignore

**Files:**
- Create: `atlas/web/playwright.config.ts`, `atlas/web/tests/smoke.spec.ts`
- Modify: `atlas/Makefile`, repo-root `.gitignore`

- [ ] **Step 1: Generate fixture data for the smoke test**

Run: `cd atlas && uv run python -m ingest.graph && uv run python web/export_data.py --db data/atlas.duckdb --out web/static/data` (if no DB/data, build it first with `make all`, or run against the CI fixtures).

- [ ] **Step 2: Create `playwright.config.ts`**

```ts
import { defineConfig } from "@playwright/test";
export default defineConfig({
  testDir: "tests",
  testMatch: "**/*.spec.ts",
  webServer: { command: "npm run build && npm run preview -- --port 4173", port: 4173, reuseExistingServer: !process.env.CI },
  use: { baseURL: "http://localhost:4173" },
});
```

- [ ] **Step 3: Create `tests/smoke.spec.ts`**

```ts
import { expect, test } from "@playwright/test";

test("map renders and explore unlocks", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("svg[aria-label='AI value chain map']")).toBeVisible();
  // at least one node circle renders
  await expect(page.locator("g.node").first()).toBeVisible({ timeout: 10_000 });
  // scroll to the final (explore) scene
  await page.mouse.wheel(0, 20_000);
  await page.waitForTimeout(800);
  // clicking a node opens the panel
  await page.locator("g.node").first().click();
  await expect(page.locator("aside.panel")).toBeVisible();
});
```

- [ ] **Step 4: Add Makefile targets and gitignore rule**

Append to `atlas/Makefile`:

```makefile
web-data:
	python web/export_data.py --db data/atlas.duckdb --out web/static/data

web-dev:
	cd web && npm run dev

web-build:
	cd web && npm run build
```

Add to repo-root `.gitignore`:

```gitignore
# web build + generated data
atlas/web/node_modules/
atlas/web/dist/
atlas/web/static/data/
atlas/web/test-results/
atlas/web/playwright-report/
```

- [ ] **Step 5: Run the smoke test**

Run: `cd atlas/web && npx playwright test`
Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add atlas/web/playwright.config.ts atlas/web/tests/smoke.spec.ts atlas/Makefile .gitignore
git commit -m "test(web): playwright smoke + make targets + gitignore"
```

---

## Task 11: CI, Pages deploy, remove Streamlit, docs

**Files:**
- Create: `.github/workflows/web.yml`
- Modify: `.github/workflows/update-data.yml`, `atlas/README.md`
- Delete: `atlas/app/streamlit_app.py` (and `app/data.py` if unused after removal)

- [ ] **Step 1: Create `.github/workflows/web.yml`** (PR check: build + unit + smoke)

```yaml
name: web
on:
  push:
  pull_request:
jobs:
  build-test:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: atlas/web } }
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20" }
      - run: npm ci
      - run: npx svelte-check --tsconfig ./tsconfig.json
      - run: npx vitest run
      - name: build fixture data
        working-directory: atlas
        run: |
          uv run python -m ingest.graph || true
          uv run python web/export_data.py --db tests/fixtures/atlas.duckdb --out web/static/data || \
            echo '{"nodes":[],"edges":[]}' > web/static/data/graph.json
      - run: npx playwright install --with-deps chromium
      - run: npx playwright test
```

> If a fixtures DuckDB isn't available in CI, add a tiny `atlas/tests/fixtures/atlas.duckdb`
> builder step (reuse the Task 1 fixture helper) so the export produces real data.

- [ ] **Step 2: Extend `update-data.yml`** — after the data release publishes, export + build + deploy to Pages

Add a `deploy-web` job (depends on the refresh job) using the project's preferred Pages flow:

```yaml
  deploy-web:
    needs: refresh
    runs-on: ubuntu-latest
    permissions: { pages: write, id-token: write, contents: read }
    environment: { name: github-pages }
    defaults: { run: { working-directory: atlas } }
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - uses: actions/setup-node@v4
        with: { node-version: "20" }
      - run: uv venv && uv pip install -e ".[dev]"
      - run: uv run make all            # rebuild duckdb from the freshest data
      - run: uv run python web/export_data.py --db data/atlas.duckdb --out web/static/data
      - run: cd web && npm ci && npm run build
      - uses: actions/upload-pages-artifact@v3
        with: { path: atlas/web/dist }
      - uses: actions/deploy-pages@v4
```

- [ ] **Step 3: Remove Streamlit**

```bash
git rm atlas/app/streamlit_app.py
```
Check whether `atlas/app/data.py` is still imported anywhere (`grep -rn "app.data\|app/data" atlas`). If unused, `git rm atlas/app/data.py atlas/tests/test_app_data.py`; if its release pipeline is still referenced, keep it. Remove the `app` Streamlit run target from the Makefile.

- [ ] **Step 4: Update `README.md`** — replace the Streamlit demo link with the GitHub Pages URL; add a "How the front-end works" section (static, precomputed JSON, scroll-story + explorable map); update the architecture/run instructions (`make web-data && make web-dev`).

- [ ] **Step 5: Verify the full web suite + commit**

Run: `cd atlas/web && npm run build && npx vitest run && npx playwright test`
Expected: build ok; unit + smoke green.

```bash
git add .github/workflows/web.yml .github/workflows/update-data.yml atlas/README.md atlas/Makefile
git commit -m "ci(web): build/test workflow + Pages deploy; retire Streamlit"
```

---

## Council Review Adjustments (apply during the listed task)

From a multi-perspective review. Build-breakers (publicDir, tsconfig lib, cik guard,
downsample guard, layout neighbours) are already folded into the task code above. The rest:

- **Task 1 (CI/smoke fixture):** there is NO committed `.duckdb`, and `ingest.graph` alone
  only creates graph tables (no `returns`/`leadlag`), so export raises "missing required
  table". Add `web/tests/make_fixture_db.py` that builds a temp DuckDB with `graph_nodes`,
  `graph_edges`, `leadlag`, and `returns` (reuse the `_fixture_db` helper from
  `test_export_data.py`). Smoke (Task 10) and CI (Task 11) must build that fixture DB and
  export from it — never rely on a checked-in `.duckdb`.
- **Task 4 (layout):** add a vertical min-spacing pass so labels in dense columns
  (chips/cloud) don't overlap; nudge `y` apart if closer than ~28px.
- **Task 7 (map):**
  - Return a cleanup from the `$effect` that calls `svg.on(".zoom", null)` so zoom handlers
    don't accumulate across re-renders.
  - **Reduced motion + decodability:** edge pulses run ONLY under
    `@media (prefers-reduced-motion: no-preference)` and ONLY on `pair_type==="edge"`,
    FDR-significant + stable edges; pulse encodes *direction*, not magnitude. Render the
    measured lag as a **numeric label** ("≈N d") on significant edges (and on hover) — that
    is the readable encoding, not pulse speed.
  - Mute non-significant edges hard (opacity ≈0.15, thin) so the map doesn't imply causation.
  - **Don't rely on color alone:** add stage **column headers** (EQUIPMENT/FOUNDRY/CHIPS/
    CLOUD) and a small legend.
  - **SR a11y:** give each node `<title>` (name + stage + ticker).
- **Task 8 (scroller):** offset `0.5`, add `.onStepExit`; add visible **prev/next scene
  buttons** and make each scene a focusable landmark so the story is keyboard/SR-drivable.
- **Task 9 (app):** **never unmount `Scroller` on mode change** (that collapses page height
  and bounces scrollama) — keep it mounted and toggle visibility/`pointer-events`. Add a
  persistent "correlation, not causation" caption. **Descope the time scrubber** (spec §4) to
  a follow-up; explore mode ships with stage filters + node panel only.
- **Task 11 (deploy):** add `concurrency: { group: "pages", cancel-in-progress: true }` to the
  Pages deploy job so scheduled + dispatched runs don't race.
- **Scenes:** scene 6 ("forgotten plays") stays a brief teaser and leads into Explore; capex
  scene 5 only renders fundamentals if Layer 2 has populated `fundamentals_quarterly` (it
  degrades to a labeled "coming with Layer 2" state otherwise).

## Definition of Done

- [ ] `export_data.py` produces `graph/leadlag/series/meta.json`; pytest green; missing-table guard works.
- [ ] `npx vitest run` green (`data`, `layout`, `leadlag`); `svelte-check` clean.
- [ ] `npm run build` produces a static `dist/`; Playwright smoke passes (map renders, scroll advances, explore unlocks, node panel opens).
- [ ] Stage-column map renders left→right by stage; skip + back edges drawn (back-edges dashed/right→left); lead/lag scene bolds FDR-significant+stable edges.
- [ ] 7 scenes drive highlight/focus; explore mode unlocks pan/zoom + node panel + stage filters.
- [ ] Nightly workflow exports JSON, builds, and deploys to GitHub Pages; README points to the Pages URL.
- [ ] Streamlit app removed; no dangling imports; Makefile updated.
- [ ] No data files committed (`web/static/data/` gitignored); data is regenerated by the build.
