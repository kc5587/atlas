# Atlas Front-End v2 — Scrollytelling Data-Story + Explorable Map (Design)

**Date:** 2026-06-02
**Status:** Design approved (pending written-spec review)
**Replaces:** the Streamlit app (`app/streamlit_app.py`) as Atlas's public interface
**Builds on:** `2026-06-02-atlas-value-chain-design.md` (data pipeline unchanged)

---

## 1. Purpose

Replace the klunky, laggy Streamlit BI app with a fast, distinctive interface: a
**scroll-driven data-story whose centerpiece is a live, animated value-chain map.** As the
reader scrolls the thesis, the map reacts (nodes highlight, edges pulse with measured
lead/lag, charts fade in); at the end it unlocks into a freely explorable mode. One artifact
that is both a narrative and an interactive map.

**Why this fixes the lag:** Streamlit round-trips every interaction to a Python server that
re-runs the script and reloads data. This is a **static site** that loads small precomputed
JSON once; all interaction (pan/zoom/hover/scroll) is client-side JS — instant, free to host.

## 2. Scope

- **In:** a new `web/` front-end package; a Python `export_data.py` step that turns the
  DuckDB marts into compact static JSON; a 7-scene scroll-story; a layered-DAG map with
  free-explore mode; nightly static rebuild + deploy to GitHub Pages; removal of the
  Streamlit app and its release-fetch wiring.
- **Out (non-goals):** ad-hoc/free-form SQL querying in-browser (no DuckDB-WASM — fixed views
  only); user accounts; mobile-first layout (desktop-first, gracefully degrades); changing the
  data pipeline (ingest/dbt/analysis are untouched); Layer 3 "forgotten plays" *data* (scene 6
  is a teaser placeholder until Layer 3 lands).

## 3. Map model — layered DAG with skip/back edges

Dependency is directional, so direction is the dominant visual axis (arrowheads + animation),
not clustering.

- **Layout:** a **stage-column layout** — `x` is fixed by the node's declared `stage`
  (equipment → foundry → chips → cloud, left→right); `y` orders nodes within a column. Order
  is chosen by a barycenter heuristic (mean `y` of connected nodes) to reduce edge crossings.
  No external graph-layout library and no topological layering needed.
- **Truthfulness:** the layout **draws skip-level edges** (e.g. NVDA→enterprise) and
  **back-edges** (hyperscaler in-house silicon, e.g. Google TPU / Amazon Trainium looping into
  "chips"). Because columns come from the declared `stage`, **cycles are a non-issue** — a
  back-edge simply renders right→left, visually distinguished (dashed/curved). A pure Sankey
  would lie by omission; this keeps every non-adjacent edge. `layout.ts` is pure + unit-tested.
- **Two flows:** goods/value flow downstream; demand/capital (capex) flows upstream. The map
  can express both — the upstream demand-pull is the lead/lag thesis.
- **Encodings:** node size = criticality/concentration; node color = stage; edge thickness =
  lead/lag significance (bold = FDR-significant + stable); edge animation = a pulse whose
  delay/speed encodes the measured lag (days for price edges, quarters for capex edges).

## 4. Interaction model — sticky map + scrolling steps → unlock

- Desktop: the map is **pinned full-bleed**; a narrow narrative column scrolls over it. Each
  scroll step is a "scene" that drives a camera transition (highlight/dim/zoom) on the map.
- After the final scene, the map **unlocks into free-explore**: pan, zoom, click a node for a
  side panel (its prices, fundamentals, and incident edges), stage filters, and a time
  scrubber that re-evaluates the displayed window.
- A persistent "skip to explore" affordance lets repeat visitors jump straight to the map.

## 5. Scroll-story scenes

1. **The whole chain** — full map fades in, stages labeled.
2. **Trace one path** — spotlight ASML→TSMC→NVDA→MSFT, dim the rest.
3. **Bottlenecks & geography** — size by criticality; flag EUV (ASML), advanced packaging,
   Taiwan/Netherlands concentration.
4. **Measured lead/lag** — edges pulse; bold = FDR-significant + stable; inline lead/lag chart
   for a flagship pair; "upstream moves show up downstream N days later."
5. **The upstream pull (capex)** — animate demand flowing upstream; tie to the Layer 2
   capex→revenue / capex→price lead/lag (renders only if Layer 2 data is present).
6. **Forgotten plays** — pan to power/cooling/fiber (Layer 3 teaser); "not-yet-priced-in"
   watchlist. Placeholder copy until Layer 3 data exists.
7. **Explore** — map unlocks; full controls.

## 6. Architecture

```
atlas/
  web/                          # NEW front-end (decoupled from Python)
    package.json                # vite + svelte 5 + typescript (d3, scrollama, zod)
    vite.config.ts
    index.html
    src/
      main.ts
      App.svelte                # layout: sticky map + scroller + explore toggle
      lib/
        data.ts                 # fetch + typed/zod-validated load of static JSON
        layout.ts               # graph -> stage-column positions (barycenter); PURE, unit-tested
        leadlag.ts              # edge styling/format from lead/lag rows; PURE, unit-tested
        scenes.ts               # scene definitions (camera target + highlight set)
      components/
        ValueChainMap.svelte    # D3 svg/canvas map: nodes, edges, pulses, zoom
        Scroller.svelte         # scrollama steps -> active scene store
        NodePanel.svelte        # drill-down side panel (prices/fundamentals/edges)
        LeadLagChart.svelte     # inline chart
        Controls.svelte         # stage filters + time scrubber (explore mode)
      stores.ts                 # svelte stores: activeScene, mode, selection, window
    static/
      data/                     # generated; gitignored; produced by export_data.py
    tests/                      # vitest unit tests; playwright smoke
  web/export_data.py            # NEW: duckdb marts -> static/data/*.json (PURE-ish, pytest)
```

**Removed:** `app/streamlit_app.py`, `app/data.py`'s release-fetch wiring usage in the app
(the publish/release pipeline itself stays — the site consumes its data via the export step).
`app/data.py` resolution helpers may be deleted if unused after removal.

## 7. Data flow & export contract

`web/export_data.py` connects read-only to `atlas.duckdb` and writes compact JSON to
`web/static/data/`:

- `graph.json` — `{ nodes: [{id,name,stage,region,tickers,cik?,criticality}], edges:
  [{from_id,to_id,relationship,note,evidence,as_of}] }`
- `leadlag.json` — the `leadlag` table rows (`pair_type,left,right,lag,corr,p_value,q_value,
  n_eff,stable`).
- `series.json` — **downsampled** per-ticker price series (e.g. weekly close + cumulative
  return) and, when present, quarterly fundamentals (revenue/capex/gross_margin). Downsampling
  keeps payloads to a few hundred KB.
- `meta.json` — `{ generated_at, schema_version, tickers, stages }`.

`criticality` is derived in the export (e.g. graph in-degree/out-degree + a curated weight)
so the front-end stays presentation-only. Missing optional tables (fundamentals) → omitted
keys, and the front-end degrades gracefully (scene 5 shows a "fundamentals not yet available"
state).

## 8. Refresh & hosting

- The site is **static**. The nightly `update-data.yml` workflow, after publishing the DuckDB
  release, runs `export_data.py`, builds `web/` (`npm run build`), and deploys to **GitHub
  Pages** (`actions/deploy-pages`). The site is rebuilt daily with fresh data; no runtime
  fetch, no server.
- Local: `make web-data` (export) + `make web-dev` (Vite dev server) + `make web-build`.
- Public URL moves from the Streamlit link to the GitHub Pages URL (README updated).

## 9. Error handling

- `export_data.py` validates required tables exist; fails loudly (non-zero) if `graph_nodes`/
  `graph_edges`/`leadlag` are missing, so a broken pipeline can't silently ship an empty site.
- Front-end `data.ts` validates fetched JSON against TypeScript types at runtime (zod-lite
  guards); on malformed/absent data it renders an explicit error/empty state, never a blank
  canvas.
- Scenes that depend on optional data (capex/fundamentals) check presence and show a labeled
  fallback rather than erroring.

## 10. Testing

- **Vitest (unit):** `layout.ts` (graph → deterministic layered positions; skip/back edges
  retained), `leadlag.ts` (edge thickness/significance/format), `data.ts` guards.
- **Playwright (smoke):** site loads; scrolling advances the active scene; the map renders
  nodes/edges; the explore mode unlocks and a node click opens the panel.
- **pytest:** `export_data.py` against a tiny fixture DuckDB → asserts JSON shape + downsample
  bounds + graceful handling of a missing fundamentals table.
- Coverage target 80% on the pure TS lib + the export script (UI components are smoke-tested).

## 11. Build order (becomes the plan)

1. `web/export_data.py` + pytest (JSON contract).
2. `web/` scaffold (Vite/Svelte/TS) + `data.ts` typed loaders + tests.
3. `layout.ts` (stage-column layout + barycenter ordering) + tests; `ValueChainMap.svelte` static render.
4. Edge styling/lead-lag (`leadlag.ts`) + pulse animation.
5. `Scroller.svelte` + scenes 1–7 (camera/highlight transitions).
6. Explore mode: `NodePanel`, `Controls` (filters + time scrubber).
7. Playwright smoke; polish; empty/error states.
8. CI (build + vitest + playwright + pytest); Makefile targets.
9. Nightly export+build+deploy to GitHub Pages; remove Streamlit; README/URL update.
```
