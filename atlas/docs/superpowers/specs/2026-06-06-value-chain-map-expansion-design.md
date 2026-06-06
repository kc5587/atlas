# Value-Chain Map Expansion — Design Spec

**Date:** 2026-06-06
**Status:** Approved (design), pending implementation plan
**Scope:** Structural map expansion only. **No verdicts touched. No new statistical signals.** A new tested hypothesis (networking lead/lag → H11) is deferred to a separate follow-up spec.

---

## 1. Goal & rationale

The Atlas value-chain map currently covers 21 nodes across 5 stages (equipment → foundry → chips → cloud → power). Several economically important industries in the AI hardware chain are absent, and 3 nodes (`oracle`, `nrg`, `eaton`) are orphaned (no edges). This spec adds 4 new industries with **fully-sourced edges** (every edge cited to a 10-K/20-F, matching existing rigor), fixes the orphans, corrects a direction-modeling bug in the power edges, and reorders the chain so **cloud is the rightmost demand terminus**.

### Two kinds of claim (the rigor model)

- **Structural claim (the map):** "Company A supplies Company B." Verified *documentarily* — cited to an SEC filing. Not a statistical test.
- **Statistical claim (the Signal Lab):** "A's metric *predicts* B's metric, slope X, q=Y, verdict ∈ {confirmed, suggestive, null, contradicts}." Tested — de-betaed, FDR-corrected, walk-forward.

The map is the **skeleton** (who supplies whom, cited); the Signal Lab is the **evidence the skeleton transmits force** (tested, sometimes null). New nodes added here are structural; they get cited edges but no verdict card. This division is honest and explicit.

### Why no frontier AI labs (OpenAI/Anthropic/etc.)

They are **private**: no ticker (the `Node` validator requires ≥1 ticker), no SEC filing to cite, no price/fundamental series to test. Including them would be the single unsourced, untestable element on an otherwise fully-cited board. Their *demand* is already captured publicly through the hyperscalers (MSFT↔OpenAI, AMZN↔Anthropic, GOOGL=Gemini, META=Llama) — whose capex H1/H5 already test. The chain therefore terminates at **cloud** (demand sink). A non-node "demand: frontier labs (private)" annotation is **deferred** (out of scope).

---

## 2. Stage taxonomy & ordering

### New stages (explore-only)

| stage | nodes (ticker) | region |
|---|---|---|
| `eda` | Synopsys (SNPS), Cadence (CDNS) | US |
| `packaging` | Amkor (AMKR) | US |
| `networking` | Arista (ANET), Marvell (MRVL), Astera Labs (ALAB) | US |
| `grid` | GE Vernova (GEV), Quanta Services (PWR) | US |

Existing stages (equipment, foundry, chips, cloud, power) keep their current rosters. **Dell/Supermicro stay `cloud`** (no "systems/integrator" split — that would remove them from story mode). CIKs filled from EDGAR where available.

### Column ordering — cloud is the terminus (both modes)

**Story mode (5 columns):**
```
equipment → foundry → chips → power → cloud
```
(power moves from far-right to just-left-of-cloud; cloud becomes terminus)

**Explore mode (9 columns):**
```
eda → equipment → foundry → packaging → chips → networking → grid → power → cloud
```

Rationale: cloud (hyperscaler demand) is the sink that pulls the entire chain — which *is* the project thesis. With cloud rightmost, the power/grid arm (`grid → power → cloud`) and the compute spine (`chips → networking → cloud`) are all **forward** edges, and the power-supply direction is semantically correct (utilities supply electricity *to* datacenters).

### Colors (extend the 5-color palette)

| stage | existing/new | hex |
|---|---|---|
| equipment | existing | `#6c8ebf` |
| foundry | existing | `#9673a6` |
| chips | existing | `#82b366` |
| cloud | existing | `#d79b00` |
| power | existing | `#b5563a` |
| eda | **new** | `#4cc2c4` (cyan) |
| packaging | **new** | `#d98cc4` (pink) |
| networking | **new** | `#5b6ee1` (indigo) |
| grid | **new** | `#c9b037` (gold/olive) |

Legend gains 4 entries. Colorblind-distinct check to be confirmed in review; adjust hues if any pair is too close.

---

## 3. New edges (all `relationship: supplies`, `as_of: 2024-01-01`)

| from → to | evidence (citation) |
|---|---|
| synopsys → nvidia, amd, broadcom | SNPS FY24 10-K — EDA tools/IP to leading chip designers |
| cadence → nvidia, amd, broadcom | CDNS FY24 10-K — EDA tools/IP to leading chip designers |
| amkor → nvidia, amd | AMKR FY24 10-K — OSAT assembly/test, customer concentration |
| broadcom → arista | AVGO merchant switch silicon (Tomahawk/Jericho) in ANET platforms |
| arista → microsoft, meta | ANET FY24 10-K — Microsoft & Meta customer concentration |
| marvell → amazon, microsoft | MRVL FY24 10-K — custom AI silicon / cloud concentration |
| astera_labs → nvidia, microsoft | ALAB FY24 10-K — AI-server connectivity, hyperscaler concentration |
| ge_vernova → constellation, vistra, dominion | GEV FY24 10-K — gas turbines & grid equipment to utilities/IPPs |
| quanta → dominion, constellation | PWR FY24 10-K — grid/datacenter construction services |

All edges point upstream→downstream → render as forward (solid) edges. Notes summarize the supply relationship; evidence cites the filing.

---

## 4. Orphan fixes & power-edge direction correction

### Orphan fixes (existing nodes; appear in both modes)

| new edge | evidence |
|---|---|
| nvidia → oracle | NVDA/ORCL FY24 — GPUs to Oracle Cloud Infrastructure (OCI) |
| nrg → amazon | NRG FY24 — power offtake / PPA to hyperscaler datacenter load |
| eaton → microsoft | ETN FY24 — datacenter electrical distribution gear to hyperscalers |

Directions are correct (supplier → customer): NRG/Eaton supply *to* cloud; NVIDIA supplies *to* Oracle.

### Power-edge direction fix (correctness bug)

The 4 existing power edges are modeled backwards (`cloud → utility "supplies"`, which reads "cloud supplies the utility"). Flip to the correct **utility → cloud** direction and add missing notes:

| before | after | note |
|---|---|---|
| microsoft → dominion | dominion → microsoft | Dominion supplies grid power to MSFT datacenters (VA) |
| amazon → vistra | vistra → amazon | Vistra power offtake to AWS datacenter load |
| microsoft → constellation | constellation → microsoft | Constellation nuclear PPA to MSFT |
| amazon → vertiv | vertiv → amazon | Vertiv datacenter power/cooling gear to AWS buildout |

With cloud as terminus (§2), all flipped edges render forward/solid. **H10 reads the `power_*` tables, not graph edge direction — flipping is statistically safe; confirm by re-running the H10 export and diffing the numbers (must be unchanged).**

### Lead/lag lookup interaction

`leadLagFor(leadlag, from_id, to_id)` is keyed on edge direction. Flipping `from`/`to` on the 4 power edges (and adding new edges) must not break lead/lag styling. Power edges are not in the daily lead/lag pair set (H0), so no row should be affected — **verify**: regenerate `leadlag` after the seed change and confirm no power/new-edge rows are silently dropped. If any lookup is order-sensitive for an affected edge, make `leadLagFor` order-insensitive (try both orderings).

---

## 5. Mode-aware layout

`web/src/lib/layout.ts` today has a single `STAGE_ORDER`. Change to:

```ts
const STAGE_ORDER_STORY: Stage[]   = ["equipment","foundry","chips","power","cloud"];
const STAGE_ORDER_EXPLORE: Stage[] = ["eda","equipment","foundry","packaging","chips","networking","grid","power","cloud"];
```

- `computeLayout(graph, opts)` takes `mode: "story" | "explore"`.
- **Story mode filters out nodes whose stage ∉ STAGE_ORDER_STORY** → story renders the current 21 nodes (now in the reordered 5-column layout). The 4 new stages never appear in story.
- Explore mode shows all nodes across 9 columns; existing pan/zoom + no left-inset handle the width.
- `web/src/components/ValueChainMap.svelte`: the hardcoded `STAGES` array (column headers), `stageColor()` map, and legend must become **mode-aware** (5 entries story / 9 explore). The component already receives a `mode` prop.
- `Controls` stage-filter chips read `meta.stages` and auto-pick up the 4 new stages.

The existing in-house back-edges (`google → tsmc`, `amazon → tsmc`) remain back-edges (cloud col > foundry col) and keep their dashed-gold styling — semantics preserved.

---

## 6. Taxonomy wiring sites (update in lockstep)

The `stage` enum is hardcoded in **6 places**; all must accept the 4 new values:

1. `ingest/graph.py:12` — `Stage = Literal[...]` (pydantic node validation)
2. `dbt_project/models/marts/schema.yml:18` — `accepted_values` test
3. `web/export_data.py:132` — `meta.stages` list (use full explore order)
4. `web/src/lib/types.ts:4` — `StageZ` Zod enum
5. `web/src/lib/layout.ts` — `STAGE_ORDER_STORY` / `STAGE_ORDER_EXPLORE`
6. `web/src/components/ValueChainMap.svelte` — `STAGES` array + `stageColor()` + legend

Seed source of truth: `seeds/value_chain.yml` (nodes + edges). Pipeline: edit YAML → `ingest/graph.py` → DuckDB `graph_nodes`/`graph_edges` → dbt → `web/export_data.py` → `web/static/data/graph.json`. `criticality` (= degree) recomputes automatically in export.

---

## 7. Testing

- **`ingest` / `load_graph`:** new tests — the 4 new stages validate; all new edges resolve to known node ids; flipped power edges + orphan edges parse. Duplicate-id / unknown-endpoint guards still pass.
- **dbt:** `accepted_values` passes with new stages present.
- **`web/tests/layout.test.ts`:** story mode = 5 columns / 21 nodes (new stages excluded); explore mode = 9 columns / all 29 nodes; cloud is the rightmost column in both; flipped power edges + grid→power render forward (not `isBack`).
- **`web/tests/data.test.ts`:** `graph.json` validates against `GraphZ` with new stages; no orphan nodes remain (every node has ≥1 edge).
- **H10 regression:** re-run ingest→dbt→export; diff `power_margins` / `power_demand` / `signals.json` — **must be byte-identical** (edge-direction flip is structural only).
- **Smoke (`smoke.spec.ts`):** map renders in both modes; stage filter chips include the 4 new stages.

---

## 8. Non-goals (explicit)

- No new statistical signal / hypothesis (networking H11 is a separate spec).
- No "systems/integrator" stage (Dell/Supermicro stay `cloud`).
- No frontier-lab nodes or demand annotation.
- No changes to any existing verdict, stat, or Signal Lab card.
- No refactor beyond what the taxonomy change requires.

---

## 9. Open items for the implementation plan

- Confirm CIKs for SNPS, CDNS, AMKR, ANET, MRVL, ALAB, GEV, PWR from EDGAR.
- Confirm colorblind-distinct palette (adjust the 4 new hues if needed).
- Decide whether `leadLagFor` needs order-insensitive lookup (only if a flipped/new edge has a lead/lag row).
