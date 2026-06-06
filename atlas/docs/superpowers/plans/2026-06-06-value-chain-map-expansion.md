# Value-Chain Map Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 4 new explore-only stages (eda, packaging, networking, grid) to the AI value-chain map with fully-sourced edges, fix 3 orphan nodes, correct the reversed power-edge direction, and reorder both modes so cloud is the rightmost demand terminus — without touching any Signal Lab verdict or number.

**Architecture:** The seed YAML (`seeds/value_chain.yml`) is the single source of truth; it flows ingest → DuckDB → dbt → `web/export_data.py` → `web/static/data/graph.json`. The `stage` enum is hardcoded in 6 sites that must move in lockstep. A new `web/src/lib/stages.ts` module becomes the single source of stage order/color/label for the frontend (DRY — today the order is duplicated between `layout.ts` and `ValueChainMap.svelte`). The map layout becomes mode-aware: story mode renders only the 5 original stages (21 nodes); explore mode renders all 9 stages (29 nodes).

**Tech Stack:** Python 3.13 (pydantic, duckdb, pandas, pytest), dbt, Svelte 5 + TypeScript + D3 + Zod, Vitest.

**Reference spec:** `docs/superpowers/specs/2026-06-06-value-chain-map-expansion-design.md`

---

## File structure

| File | Responsibility | Action |
|---|---|---|
| `ingest/graph.py` | pydantic `Stage` Literal | Modify (add 4 stages) |
| `dbt_project/models/marts/schema.yml` | `accepted_values` test | Modify (add 4 stages) |
| `seeds/value_chain.yml` | node/edge source of truth | Modify (8 nodes, new edges, flips, orphans) |
| `tests/test_graph.py` | ingest validation tests | Modify (new-stage test, flip assertion) |
| `web/src/lib/types.ts` | `StageZ` Zod enum | Modify (add 4 stages) |
| `web/src/lib/stages.ts` | **NEW** stage order/color/label | Create |
| `web/src/lib/layout.ts` | mode-aware column layout | Modify |
| `web/src/components/ValueChainMap.svelte` | mode-aware headers/colors/legend | Modify |
| `web/export_data.py` | `meta.stages` list | Modify |
| `web/tests/layout.test.ts` | layout unit tests | Modify |
| `web/tests/stages.test.ts` | **NEW** stages module test | Create |
| `web/tests/data.test.ts` | graph parse test | Modify (new-stage parse) |

---

## Task 1: Extend the `Stage` Literal (ingest) + dbt accepted_values

**Files:**
- Modify: `ingest/graph.py:12`
- Modify: `dbt_project/models/marts/schema.yml:18`
- Test: `tests/test_graph.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_graph.py` (after the `VALID_WITH_CIK` constant block, before the test functions or at the end):

```python
NEW_STAGE = """
nodes:
  - id: arista
    name: Arista Networks
    tickers: [ANET]
    stage: networking
    region: US
edges: []
"""


def test_new_stages_validate(tmp_path):
    p = tmp_path / "g.yml"
    p.write_text(NEW_STAGE)
    nodes, _ = load_graph(p)
    assert nodes.loc[nodes["id"] == "arista", "stage"].iloc[0] == "networking"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/kaushalchitturu/Data_Quant_project/atlas && python -m pytest tests/test_graph.py::test_new_stages_validate -v`
Expected: FAIL — pydantic `ValidationError` (`networking` not a permitted Literal value).

- [ ] **Step 3: Implement — widen the Literal**

In `ingest/graph.py:12` replace:

```python
Stage = Literal["equipment", "foundry", "chips", "cloud", "power"]
```

with:

```python
Stage = Literal[
    "eda", "equipment", "foundry", "packaging",
    "chips", "networking", "grid", "power", "cloud",
]
```

- [ ] **Step 4: Update the dbt accepted_values test**

In `dbt_project/models/marts/schema.yml:18` replace:

```yaml
              values: [equipment, foundry, chips, cloud, power]
```

with:

```yaml
              values: [eda, equipment, foundry, packaging, chips, networking, grid, power, cloud]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd /Users/kaushalchitturu/Data_Quant_project/atlas && python -m pytest tests/test_graph.py::test_new_stages_validate -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
cd /Users/kaushalchitturu/Data_Quant_project
git add atlas/ingest/graph.py atlas/dbt_project/models/marts/schema.yml atlas/tests/test_graph.py
git commit -m "feat: allow eda/packaging/networking/grid stages in graph schema"
```

---

## Task 2: Add the 8 new nodes to the seed

**Files:**
- Modify: `seeds/value_chain.yml`
- Test: `tests/test_graph.py`

New nodes carry no `cik` (CIK is only needed when a node gets fundamentals; these nodes are map-only for now — the deferred signal spec will add CIKs via EDGAR lookup).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_graph.py`:

```python
def test_seed_has_new_stage_nodes():
    from config import SEED_PATH

    nodes, _ = load_graph(SEED_PATH)
    by_stage = nodes.groupby("stage")["id"].apply(set).to_dict()
    assert by_stage.get("eda") == {"synopsys", "cadence"}
    assert by_stage.get("packaging") == {"amkor"}
    assert by_stage.get("networking") == {"arista", "marvell", "astera_labs"}
    assert by_stage.get("grid") == {"ge_vernova", "quanta"}
    assert len(nodes) == 29
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/kaushalchitturu/Data_Quant_project/atlas && python -m pytest tests/test_graph.py::test_seed_has_new_stage_nodes -v`
Expected: FAIL — new stages absent; `len(nodes) == 21`.

- [ ] **Step 3: Implement — insert node blocks**

In `seeds/value_chain.yml`, immediately **before** the `edges:` line (after the last power node `dominion`), insert:

```yaml
  # --- eda (Layer 3 / explore-only) ---
  - id: synopsys
    name: Synopsys
    tickers: [SNPS]
    stage: eda
    region: US
  - id: cadence
    name: Cadence Design Systems
    tickers: [CDNS]
    stage: eda
    region: US
  # --- packaging / OSAT (explore-only) ---
  - id: amkor
    name: Amkor Technology
    tickers: [AMKR]
    stage: packaging
    region: US
  # --- networking / interconnect (explore-only) ---
  - id: arista
    name: Arista Networks
    tickers: [ANET]
    stage: networking
    region: US
  - id: marvell
    name: Marvell Technology
    tickers: [MRVL]
    stage: networking
    region: US
  - id: astera_labs
    name: Astera Labs
    tickers: [ALAB]
    stage: networking
    region: US
  # --- grid / power buildout (explore-only) ---
  - id: ge_vernova
    name: GE Vernova
    tickers: [GEV]
    stage: grid
    region: US
  - id: quanta
    name: Quanta Services
    tickers: [PWR]
    stage: grid
    region: US
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/kaushalchitturu/Data_Quant_project/atlas && python -m pytest tests/test_graph.py::test_seed_has_new_stage_nodes -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/kaushalchitturu/Data_Quant_project
git add atlas/seeds/value_chain.yml atlas/tests/test_graph.py
git commit -m "feat: add eda/packaging/networking/grid nodes to value-chain seed"
```

---

## Task 3: Add the new sourced supply edges

**Files:**
- Modify: `seeds/value_chain.yml`
- Test: `tests/test_graph.py`

All edges point upstream→downstream (forward). `astera_labs` routes to cloud (microsoft/amazon) to keep it forward rather than back into chips.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_graph.py`:

```python
def test_seed_has_new_supply_edges():
    from config import SEED_PATH

    _, edges = load_graph(SEED_PATH)
    pairs = set(zip(edges["from_id"], edges["to_id"]))
    assert ("synopsys", "nvidia") in pairs
    assert ("cadence", "broadcom") in pairs
    assert ("amkor", "nvidia") in pairs
    assert ("broadcom", "arista") in pairs
    assert ("arista", "microsoft") in pairs
    assert ("marvell", "amazon") in pairs
    assert ("astera_labs", "microsoft") in pairs
    assert ("ge_vernova", "constellation") in pairs
    assert ("quanta", "dominion") in pairs
    # every new edge must carry a citation (evidence non-empty)
    new_from = {"synopsys", "cadence", "amkor", "broadcom", "arista",
                "marvell", "astera_labs", "ge_vernova", "quanta"}
    cited = edges[edges["from_id"].isin(new_from)]
    assert (cited["evidence"].str.len() > 0).all()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/kaushalchitturu/Data_Quant_project/atlas && python -m pytest tests/test_graph.py::test_seed_has_new_supply_edges -v`
Expected: FAIL — none of the new pairs present.

- [ ] **Step 3: Implement — append edge blocks**

In `seeds/value_chain.yml`, at the **end of the `edges:` list** (after the last existing `amazon -> vertiv` edge), append:

```yaml
  # --- eda -> chips (design enablement) ---
  - from: synopsys
    to: nvidia
    relationship: supplies
    note: EDA tools and IP for advanced GPU design
    evidence: "SNPS FY2024 10-K (EDA software to leading semiconductor designers)"
    as_of: 2024-01-01
  - from: synopsys
    to: amd
    relationship: supplies
    note: EDA tools and IP for advanced CPU/GPU design
    evidence: "SNPS FY2024 10-K"
    as_of: 2024-01-01
  - from: synopsys
    to: broadcom
    relationship: supplies
    note: EDA tools and IP for custom ASIC design
    evidence: "SNPS FY2024 10-K"
    as_of: 2024-01-01
  - from: cadence
    to: nvidia
    relationship: supplies
    note: EDA tools and IP for advanced GPU design
    evidence: "CDNS FY2024 10-K (EDA software to leading designers)"
    as_of: 2024-01-01
  - from: cadence
    to: amd
    relationship: supplies
    note: EDA tools and IP for advanced CPU/GPU design
    evidence: "CDNS FY2024 10-K"
    as_of: 2024-01-01
  - from: cadence
    to: broadcom
    relationship: supplies
    note: EDA tools and IP for custom ASIC design
    evidence: "CDNS FY2024 10-K"
    as_of: 2024-01-01
  # --- packaging -> chips (OSAT assembly/test) ---
  - from: amkor
    to: nvidia
    relationship: supplies
    note: Outsourced assembly and test (OSAT) for data-center GPUs
    evidence: "AMKR FY2024 10-K customer concentration"
    as_of: 2024-01-01
  - from: amkor
    to: amd
    relationship: supplies
    note: Outsourced assembly and test (OSAT) for data-center accelerators
    evidence: "AMKR FY2024 10-K customer concentration"
    as_of: 2024-01-01
  # --- chips -> networking (merchant switch silicon) ---
  - from: broadcom
    to: arista
    relationship: supplies
    note: Merchant switch silicon (Tomahawk / Jericho) for data-center switches
    evidence: "AVGO networking-silicon commentary; ANET FY2024 10-K platform sourcing"
    as_of: 2024-01-01
  # --- networking -> cloud (interconnect to hyperscalers) ---
  - from: arista
    to: microsoft
    relationship: supplies
    note: Data-center networking switches
    evidence: "ANET FY2024 10-K (Microsoft customer concentration)"
    as_of: 2024-01-01
  - from: arista
    to: meta
    relationship: supplies
    note: Data-center networking switches for AI clusters
    evidence: "ANET FY2024 10-K (Meta customer concentration)"
    as_of: 2024-01-01
  - from: marvell
    to: amazon
    relationship: supplies
    note: Custom AI silicon and interconnect for AWS
    evidence: "MRVL FY2024 10-K (cloud custom-silicon concentration)"
    as_of: 2024-01-01
  - from: marvell
    to: microsoft
    relationship: supplies
    note: Custom AI silicon and interconnect
    evidence: "MRVL FY2024 10-K (cloud custom-silicon concentration)"
    as_of: 2024-01-01
  - from: astera_labs
    to: microsoft
    relationship: supplies
    note: Connectivity / retimer silicon for AI servers
    evidence: "ALAB FY2024 10-K (hyperscaler connectivity concentration)"
    as_of: 2024-01-01
  - from: astera_labs
    to: amazon
    relationship: supplies
    note: Connectivity / retimer silicon for AI servers
    evidence: "ALAB FY2024 10-K (hyperscaler connectivity concentration)"
    as_of: 2024-01-01
  # --- grid -> power (buildout equipment to utilities) ---
  - from: ge_vernova
    to: constellation
    relationship: supplies
    note: Gas turbines and grid equipment to power generators
    evidence: "GEV FY2024 10-K (power generation & grid equipment)"
    as_of: 2024-01-01
  - from: ge_vernova
    to: vistra
    relationship: supplies
    note: Gas turbines and grid equipment
    evidence: "GEV FY2024 10-K"
    as_of: 2024-01-01
  - from: ge_vernova
    to: dominion
    relationship: supplies
    note: Grid equipment to utility
    evidence: "GEV FY2024 10-K"
    as_of: 2024-01-01
  - from: quanta
    to: dominion
    relationship: supplies
    note: Grid / datacenter infrastructure construction services
    evidence: "PWR FY2024 10-K (electric power infrastructure services)"
    as_of: 2024-01-01
  - from: quanta
    to: constellation
    relationship: supplies
    note: Grid infrastructure construction services
    evidence: "PWR FY2024 10-K"
    as_of: 2024-01-01
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/kaushalchitturu/Data_Quant_project/atlas && python -m pytest tests/test_graph.py::test_seed_has_new_supply_edges -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/kaushalchitturu/Data_Quant_project
git add atlas/seeds/value_chain.yml atlas/tests/test_graph.py
git commit -m "feat: add sourced eda/packaging/networking/grid supply edges"
```

---

## Task 4: Fix orphans + correct reversed power-edge direction

**Files:**
- Modify: `seeds/value_chain.yml`
- Test: `tests/test_graph.py`

This removes the 3 orphans (`oracle`, `nrg`, `eaton`) and flips the 4 reversed power edges to the correct utility→cloud direction.

- [ ] **Step 1: Write the failing test (and update the stale one)**

In `tests/test_graph.py`, **replace** the existing `test_power_stage_nodes_and_edges_load` (lines 121-129) with:

```python
def test_power_edges_point_to_cloud_and_no_orphans():
    from config import SEED_PATH

    nodes, edges = load_graph(SEED_PATH)
    pairs = set(zip(edges["from_id"], edges["to_id"]))
    # power edges now point utility -> cloud (corrected direction)
    assert ("dominion", "microsoft") in pairs
    assert ("vistra", "amazon") in pairs
    assert ("constellation", "microsoft") in pairs
    assert ("vertiv", "amazon") in pairs
    # the old reversed edges are gone
    assert ("microsoft", "dominion") not in pairs
    assert ("amazon", "vistra") not in pairs
    # orphans fixed
    assert ("nvidia", "oracle") in pairs
    assert ("nrg", "amazon") in pairs
    assert ("eaton", "microsoft") in pairs
    # no node is orphaned
    linked = set(edges["from_id"]) | set(edges["to_id"])
    assert set(nodes["id"]) <= linked
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/kaushalchitturu/Data_Quant_project/atlas && python -m pytest tests/test_graph.py::test_power_edges_point_to_cloud_and_no_orphans -v`
Expected: FAIL — reversed edges still present; orphan edges absent.

- [ ] **Step 3: Implement — flip the 4 power edges**

In `seeds/value_chain.yml`, find the block under the `# --- cloud -> power / datacenter ---` comment (the 4 edges with `as_of: "2026-06-06"`). **Replace** those 4 edge entries with:

```yaml
  # --- power / grid -> cloud (utilities supply electricity to datacenters) ---
  - from: dominion
    to: microsoft
    relationship: supplies
    note: Grid power to Microsoft data centers (Virginia)
    evidence: "MSFT datacenter siting in Dominion service territory"
    as_of: "2026-06-06"
  - from: vistra
    to: amazon
    relationship: supplies
    note: Power offtake to AWS datacenter load
    evidence: "VST hyperscaler power agreements FY2024"
    as_of: "2026-06-06"
  - from: constellation
    to: microsoft
    relationship: supplies
    note: Nuclear power-purchase agreement to Microsoft
    evidence: "CEG-MSFT nuclear PPA announcement 2024"
    as_of: "2026-06-06"
  - from: vertiv
    to: amazon
    relationship: supplies
    note: Datacenter power and cooling equipment for AWS buildout
    evidence: "VRT FY2024 10-K hyperscaler demand commentary"
    as_of: "2026-06-06"
```

- [ ] **Step 4: Implement — add the 3 orphan-fix edges**

In `seeds/value_chain.yml`, immediately after the block from Step 3, append:

```yaml
  # --- orphan fixes ---
  - from: nvidia
    to: oracle
    relationship: supplies
    note: Data-center GPUs to Oracle Cloud Infrastructure (OCI)
    evidence: "ORCL OCI GPU capacity commentary FY2024"
    as_of: 2024-01-01
  - from: nrg
    to: amazon
    relationship: supplies
    note: Power offtake to hyperscaler datacenter load
    evidence: "NRG retail/wholesale power to large-load datacenters FY2024"
    as_of: "2026-06-06"
  - from: eaton
    to: microsoft
    relationship: supplies
    note: Datacenter electrical distribution equipment
    evidence: "ETN FY2024 10-K datacenter electrical demand"
    as_of: 2024-01-01
```

- [ ] **Step 5: Run test to verify it passes (and the full ingest suite)**

Run: `cd /Users/kaushalchitturu/Data_Quant_project/atlas && python -m pytest tests/test_graph.py -v`
Expected: PASS (all tests in the file, including the updated direction/orphan test).

- [ ] **Step 6: Commit**

```bash
cd /Users/kaushalchitturu/Data_Quant_project
git add atlas/seeds/value_chain.yml atlas/tests/test_graph.py
git commit -m "fix: correct power-edge direction (utility->cloud) and de-orphan oracle/nrg/eaton"
```

---

## Task 5: Extend the frontend `StageZ` enum

**Files:**
- Modify: `web/src/lib/types.ts:4`
- Test: `web/tests/data.test.ts`

- [ ] **Step 1: Write the failing test**

Add to `web/tests/data.test.ts` inside the `describe("data parsing", ...)` block:

```typescript
  it("parses the new explore-only stages", () => {
    const g = parseGraph({
      nodes: [{ id: "arista", name: "Arista", tickers: ["ANET"], stage: "networking", region: "US", criticality: 2 }],
      edges: [],
    });
    expect(g.nodes[0].stage).toBe("networking");
  });
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/kaushalchitturu/Data_Quant_project/atlas/web && npm run test -- data.test.ts`
Expected: FAIL — Zod rejects `networking` (not in enum).

- [ ] **Step 3: Implement — widen StageZ**

In `web/src/lib/types.ts:4` replace:

```typescript
export const StageZ = z.enum(["equipment", "foundry", "chips", "cloud", "power"]);
```

with:

```typescript
export const StageZ = z.enum([
  "eda", "equipment", "foundry", "packaging",
  "chips", "networking", "grid", "power", "cloud",
]);
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/kaushalchitturu/Data_Quant_project/atlas/web && npm run test -- data.test.ts`
Expected: PASS (including the existing "rejects an invalid stage" test, since `banana` is still invalid).

- [ ] **Step 5: Commit**

```bash
cd /Users/kaushalchitturu/Data_Quant_project
git add atlas/web/src/lib/types.ts atlas/web/tests/data.test.ts
git commit -m "feat: add new stages to frontend StageZ enum"
```

---

## Task 6: Create the `stages.ts` single-source module

**Files:**
- Create: `web/src/lib/stages.ts`
- Test: `web/tests/stages.test.ts`

- [ ] **Step 1: Write the failing test**

Create `web/tests/stages.test.ts`:

```typescript
// atlas/web/tests/stages.test.ts
import { describe, expect, it } from "vitest";
import {
  STAGE_ORDER_STORY, STAGE_ORDER_EXPLORE, STAGE_COLOR, STAGE_LABEL, stageOrder,
} from "../src/lib/stages";

describe("stages module", () => {
  it("story order has 5 stages with cloud last", () => {
    expect(STAGE_ORDER_STORY).toHaveLength(5);
    expect(STAGE_ORDER_STORY[STAGE_ORDER_STORY.length - 1]).toBe("cloud");
    expect(STAGE_ORDER_STORY).not.toContain("networking");
  });

  it("explore order has 9 stages with cloud last", () => {
    expect(STAGE_ORDER_EXPLORE).toHaveLength(9);
    expect(STAGE_ORDER_EXPLORE[STAGE_ORDER_EXPLORE.length - 1]).toBe("cloud");
    expect(STAGE_ORDER_EXPLORE).toContain("eda");
    expect(STAGE_ORDER_EXPLORE).toContain("grid");
  });

  it("every explore stage has a color and label", () => {
    for (const s of STAGE_ORDER_EXPLORE) {
      expect(STAGE_COLOR[s]).toMatch(/^#/);
      expect(STAGE_LABEL[s].length).toBeGreaterThan(0);
    }
  });

  it("stageOrder switches by mode", () => {
    expect(stageOrder("story")).toBe(STAGE_ORDER_STORY);
    expect(stageOrder("explore")).toBe(STAGE_ORDER_EXPLORE);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/kaushalchitturu/Data_Quant_project/atlas/web && npm run test -- stages.test.ts`
Expected: FAIL — module `../src/lib/stages` does not exist.

- [ ] **Step 3: Implement — create the module**

Create `web/src/lib/stages.ts`:

```typescript
// src/lib/stages.ts
import type { Stage } from "./types";

// Story mode: the 5 canonical columns. Cloud is the demand terminus.
export const STAGE_ORDER_STORY: Stage[] = [
  "equipment", "foundry", "chips", "power", "cloud",
];

// Explore mode: the full chain, also terminating at cloud.
export const STAGE_ORDER_EXPLORE: Stage[] = [
  "eda", "equipment", "foundry", "packaging", "chips",
  "networking", "grid", "power", "cloud",
];

export const STAGE_COLOR: Record<Stage, string> = {
  eda: "#4cc2c4",
  equipment: "#6c8ebf",
  foundry: "#9673a6",
  packaging: "#d98cc4",
  chips: "#82b366",
  networking: "#5b6ee1",
  grid: "#c9b037",
  power: "#b5563a",
  cloud: "#d79b00",
};

export const STAGE_LABEL: Record<Stage, string> = {
  eda: "EDA",
  equipment: "EQUIPMENT",
  foundry: "FOUNDRY",
  packaging: "PACKAGING",
  chips: "CHIPS",
  networking: "NETWORKING",
  grid: "GRID",
  power: "POWER",
  cloud: "CLOUD",
};

export function stageOrder(mode: "story" | "explore"): Stage[] {
  return mode === "explore" ? STAGE_ORDER_EXPLORE : STAGE_ORDER_STORY;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/kaushalchitturu/Data_Quant_project/atlas/web && npm run test -- stages.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/kaushalchitturu/Data_Quant_project
git add atlas/web/src/lib/stages.ts atlas/web/tests/stages.test.ts
git commit -m "feat: add stages.ts single-source stage order/color/label module"
```

---

## Task 7: Make `layout.ts` mode-aware

**Files:**
- Modify: `web/src/lib/layout.ts`
- Test: `web/tests/layout.test.ts`

`computeLayout` gains a `mode` option, uses `stageOrder(mode)` for columns, and in story mode **filters out nodes (and edges touching them) whose stage is not a story column**. This keeps `ValueChainMap` from dereferencing a missing node when rendering an edge.

- [ ] **Step 1: Update the existing tests for the cloud-terminus reorder**

In `web/tests/layout.test.ts`, the sample graph uses `msft` (cloud) and `vistra` (power). After the reorder (`...chips, power, cloud`), power sits left of cloud. **Replace** the first test (`"assigns x by stage order (left to right)"`, lines 25-32) with:

```typescript
  it("assigns x by stage order with cloud as the terminus", () => {
    const { nodes } = computeLayout(g, { width: 800, height: 400 });
    const by = Object.fromEntries(nodes.map((n) => [n.id, n.x]));
    expect(by["asml"]).toBeLessThan(by["tsmc"]);
    expect(by["tsmc"]).toBeLessThan(by["nvidia"]);
    expect(by["nvidia"]).toBeLessThan(by["vistra"]); // chips < power
    expect(by["vistra"]).toBeLessThan(by["msft"]);   // power < cloud (terminus)
  });
```

- [ ] **Step 2: Add the mode-filtering test**

Append a new test inside the `describe("computeLayout", ...)` block in `web/tests/layout.test.ts`:

```typescript
  it("hides new-stage nodes in story mode and shows them in explore", () => {
    const g2: Graph = {
      nodes: [
        ...g.nodes,
        { id: "arista", name: "Arista", tickers: ["ANET"], stage: "networking", region: "US", criticality: 1 },
      ],
      edges: [
        ...g.edges,
        { from_id: "arista", to_id: "msft", relationship: "supplies", note: "", evidence: "", as_of: "" },
      ],
    };
    const story = computeLayout(g2, { width: 800, height: 400, mode: "story" });
    expect(story.nodes.find((n) => n.id === "arista")).toBeUndefined();
    // edge touching a hidden node is dropped (no dangling reference)
    expect(story.edges.find((e) => e.from_id === "arista")).toBeUndefined();

    const explore = computeLayout(g2, { width: 800, height: 400, mode: "explore" });
    expect(explore.nodes.find((n) => n.id === "arista")).toBeDefined();
    expect(explore.edges.find((e) => e.from_id === "arista")).toBeDefined();
  });
```

- [ ] **Step 3: Run tests to verify failure**

Run: `cd /Users/kaushalchitturu/Data_Quant_project/atlas/web && npm run test -- layout.test.ts`
Expected: FAIL — old order assertion (`nvidia < vistra` and the mode option) not yet supported; `mode` is ignored so the filtering test fails.

- [ ] **Step 4: Implement — rewrite `layout.ts`**

Replace the entire contents of `web/src/lib/layout.ts` with:

```typescript
// src/lib/layout.ts
import type { Edge, Graph, Node, Stage } from "./types";
import { stageOrder } from "./stages";

export interface PositionedNode extends Node { x: number; y: number; col: number; }
export interface RoutedEdge extends Edge { isBack: boolean; }
export interface LayoutOpts {
  width: number;
  height: number;
  padding?: number;
  // Extra space reserved on the left edge (e.g. for the story-mode narrative
  // card). Columns start at `padding + leftInset`. Defaults to 0.
  leftInset?: number;
  // "story" renders only the canonical stages; "explore" renders the full chain.
  mode?: "story" | "explore";
}

export function computeLayout(graph: Graph, opts: LayoutOpts) {
  const pad = opts.padding ?? 60;
  const leftInset = opts.leftInset ?? 0;
  const mode = opts.mode ?? "story";
  const cols = stageOrder(mode);
  const colSet = new Set<Stage>(cols);

  // In story mode, new-stage nodes are hidden. Drop edges touching them so the
  // renderer never dereferences a missing node.
  const visibleNodes = graph.nodes.filter((n) => colSet.has(n.stage));
  const visibleIds = new Set(visibleNodes.map((n) => n.id));
  const visibleEdges = graph.edges.filter(
    (e) => visibleIds.has(e.from_id) && visibleIds.has(e.to_id),
  );

  const left = pad + leftInset;
  const right = opts.width - pad;
  const colX = (i: number) =>
    cols.length === 1 ? (left + right) / 2 : left + (i * (right - left)) / (cols.length - 1);

  const byStage = new Map<Stage, Node[]>();
  for (const s of cols) byStage.set(s, []);
  for (const n of visibleNodes) byStage.get(n.stage)!.push(n);

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
  for (const e of visibleEdges) { addNb(e.from_id, e.to_id); addNb(e.to_id, e.from_id); }
  cols.forEach((s) => {
    const list = byStage.get(s)!.map((n) => pos.get(n.id)!);
    list.sort((a, b) => bary(a, neighbours, pos) - bary(b, neighbours, pos));
    list.forEach((n, i) => {
      n.y = list.length === 1
        ? opts.height / 2
        : pad + (i * (opts.height - 2 * pad)) / (list.length - 1);
    });
  });

  const colOf = (id: string) => pos.get(id)?.col ?? 0;
  const edges: RoutedEdge[] = visibleEdges.map((e) => ({
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

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/kaushalchitturu/Data_Quant_project/atlas/web && npm run test -- layout.test.ts`
Expected: PASS (all 4 tests).

- [ ] **Step 6: Commit**

```bash
cd /Users/kaushalchitturu/Data_Quant_project
git add atlas/web/src/lib/layout.ts atlas/web/tests/layout.test.ts
git commit -m "feat: mode-aware layout (story 5 cols / explore 9 cols, cloud terminus)"
```

---

## Task 8: Make `ValueChainMap.svelte` use `stages.ts` (mode-aware headers/colors/legend)

**Files:**
- Modify: `web/src/components/ValueChainMap.svelte`

This removes the component's local `STAGES` array and `stageColor()` and drives headers, node colors, and the legend from `stages.ts`, switching on the `mode` prop. The column-header `colX` formula must use the same `cols`/`leftInset` as `computeLayout`, and `computeLayout` must now be called with `mode`.

- [ ] **Step 1: Update the script block**

In `web/src/components/ValueChainMap.svelte`:

(a) Replace the import line `import type { Graph, LeadLag, Stage } from "../lib/types";` and add the stages import:

```typescript
  import type { Graph, LeadLag } from "../lib/types";
  import { stageOrder, STAGE_COLOR, STAGE_LABEL } from "../lib/stages";
```

(b) **Delete** the local `STAGES` constant (lines 15-21, the `const STAGES: {...}[] = [...]` block).

(c) Inside the `$effect`, after `const leftInset = ...`, derive the columns for this mode and pass `mode` to `computeLayout`:

```typescript
    const leftInset = mode === "story" ? STORY_LEFT_INSET : 0;
    const STAGES = stageOrder(mode).map((key) => ({ key, label: STAGE_LABEL[key] }));
    const { nodes, edges } = computeLayout(graph, { width, height, leftInset, mode });
```

(d) **Delete** the entire `function stageColor(s: string) { ... }` block at the bottom of the script (lines 171-179) and replace every call `stageColor(d.key)` / `stageColor(n.stage)` with `STAGE_COLOR[d.key]` / `STAGE_COLOR[n.stage]`.

- [ ] **Step 2: Make the legend mode-aware**

Replace the hardcoded `<div class="legend">` stage spans (the 5 `<span><i .../>...</span>` color entries, **keeping** the `forward` / `back/in-house` entries) with a loop. The legend block becomes:

```svelte
  <div class="legend" aria-hidden="true">
    {#each stageOrder(mode) as s}
      <span><i style="background:{STAGE_COLOR[s]}"></i>{STAGE_LABEL[s].charAt(0) + STAGE_LABEL[s].slice(1).toLowerCase()}</span>
    {/each}
    <span class="sep"><i class="solid"></i>forward</span>
    <span><i class="dashed"></i>back/in-house</span>
  </div>
```

(`stageOrder` and `STAGE_LABEL` are already imported in the script and are available in the template.)

- [ ] **Step 3: Build the web app to verify it compiles**

Run: `cd /Users/kaushalchitturu/Data_Quant_project/atlas/web && npm run build`
Expected: build succeeds with no TypeScript/Svelte errors. (If `Stage` is reported unused anywhere else, remove the dangling import.)

- [ ] **Step 4: Run the full web unit suite**

Run: `cd /Users/kaushalchitturu/Data_Quant_project/atlas/web && npm run test`
Expected: PASS (stages, layout, data, and existing suites).

- [ ] **Step 5: Commit**

```bash
cd /Users/kaushalchitturu/Data_Quant_project
git add atlas/web/src/components/ValueChainMap.svelte
git commit -m "feat: drive map headers/colors/legend from stages.ts (mode-aware)"
```

---

## Task 9: Update `export_data.py` meta stages

**Files:**
- Modify: `web/export_data.py:132`
- Test: `web/tests/test_export_data.py:59` (update the existing assertion)

- [ ] **Step 1: Update the existing meta-stages assertion (this is the failing test)**

`web/tests/test_export_data.py` already asserts the stage list inside `test_export_all_writes_expected_files`. **Replace** line 59:

```python
    assert meta["stages"] == ["equipment", "foundry", "chips", "cloud", "power"]
```

with:

```python
    assert meta["stages"] == [
        "eda", "equipment", "foundry", "packaging", "chips",
        "networking", "grid", "power", "cloud",
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/kaushalchitturu/Data_Quant_project/atlas && python -m pytest web/tests/test_export_data.py::test_export_all_writes_expected_files -v`
Expected: FAIL — `export_data.py` still emits the old 5-element list, so the updated assertion does not match.

- [ ] **Step 3: Implement — update the meta stages list**

In `web/export_data.py:132` replace:

```python
    stages = ["equipment", "foundry", "chips", "cloud", "power"]
```

with:

```python
    stages = [
        "eda", "equipment", "foundry", "packaging", "chips",
        "networking", "grid", "power", "cloud",
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd /Users/kaushalchitturu/Data_Quant_project/atlas && python -m pytest web/tests/test_export_data.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/kaushalchitturu/Data_Quant_project
git add atlas/web/export_data.py atlas/web/tests/test_export_data.py
git commit -m "feat: list all 9 stages in exported meta.json"
```

---

## Task 10: Regenerate data, run H10 regression, full verification

**Files:**
- Regenerated: `web/static/data/graph.json`, `meta.json`, `signals.json`, etc.

This rebuilds the pipeline end-to-end and proves the edge-direction flip did not change any Signal Lab number.

- [ ] **Step 1: Snapshot the current signals + power tables (pre-change baseline)**

Run:
```bash
cd /Users/kaushalchitturu/Data_Quant_project/atlas
cp web/static/data/signals.json /tmp/signals.before.json
```
Expected: baseline copied.

- [ ] **Step 2: Re-ingest the graph seed into DuckDB**

Run: `cd /Users/kaushalchitturu/Data_Quant_project/atlas && python -m ingest.graph`
Expected: prints `graph: wrote 29 nodes, <N> edges` (N = original 23 minus 4 replaced + ~20 new + 3 orphan; the exact count is fine as long as it is >23).

- [ ] **Step 3: Rebuild dbt models**

Run:
```bash
cd /Users/kaushalchitturu/Data_Quant_project/atlas/dbt_project && \
ATLAS_DATA_RAW="$(cd .. && pwd)/data/raw" ATLAS_DUCKDB_PATH="$(cd .. && pwd)/data/atlas.duckdb" dbt build --profiles-dir .
```
Expected: dbt build succeeds; the `accepted_values` test on `stage` passes with the 9 stages.

- [ ] **Step 4: Re-export web data**

Run: `cd /Users/kaushalchitturu/Data_Quant_project/atlas && python web/export_data.py --db data/atlas.duckdb --out web/static/data`
Expected: prints `export_data: wrote JSON to web/static/data`.

- [ ] **Step 5: H10 regression — signals must be unchanged**

Run: `cd /Users/kaushalchitturu/Data_Quant_project/atlas && diff <(python -m json.tool /tmp/signals.before.json) <(python -m json.tool web/static/data/signals.json) && echo "SIGNALS UNCHANGED"`
Expected: prints `SIGNALS UNCHANGED` (no diff). If there IS a diff, STOP — the edge-direction flip leaked into a signal computation; investigate before continuing (the power signals read `power_*` tables, not graph edges, so a diff means something else regressed).

- [ ] **Step 6: Verify graph.json has no orphans and contains new stages**

Run:
```bash
cd /Users/kaushalchitturu/Data_Quant_project/atlas && python -c "
import json
g=json.load(open('web/static/data/graph.json'))
ids={n['id'] for n in g['nodes']}
linked={e['from_id'] for e in g['edges']} | {e['to_id'] for e in g['edges']}
assert not (ids - linked), f'orphans: {ids - linked}'
stages={n['stage'] for n in g['nodes']}
assert {'eda','packaging','networking','grid'} <= stages, stages
print('graph.json OK:', len(g['nodes']), 'nodes,', len(g['edges']), 'edges, no orphans')
"
```
Expected: prints `graph.json OK: 29 nodes, ... edges, no orphans`.

- [ ] **Step 7: Run full Python + web test suites + lint**

Run:
```bash
cd /Users/kaushalchitturu/Data_Quant_project/atlas && python -m pytest -q && ruff check . && cd web && npm run test && npm run build
```
Expected: all green.

- [ ] **Step 8: Manual smoke (optional but recommended)**

Run: `cd /Users/kaushalchitturu/Data_Quant_project/atlas/web && npm run dev`
Then in a browser: story mode shows the 5-column chain ending at cloud with power just left of it, all 21 nodes, no floating dots; switch to Explore — the full 9-column chain appears with eda/packaging/networking/grid columns, stage-filter chips for all 9 stages, and all edges drawn solid forward (no spurious dashed back-edges except the two in-house `→ tsmc` edges).

- [ ] **Step 9: Commit the regenerated data**

```bash
cd /Users/kaushalchitturu/Data_Quant_project
git add atlas/web/static/data
git commit -m "chore: regenerate web data for expanded value-chain map"
```

---

## Self-review notes (for the executor)

- **Spec coverage:** §2 stages/order → Tasks 1,2,5,6,7,9; §3 edges → Task 3; §4 orphans+direction → Task 4; §5 layout → Task 7; §6 wiring (6 sites) → Tasks 1 (ingest+dbt), 5 (types), 7 (layout), 8 (ValueChainMap), 9 (export); §7 testing → Tasks 1-10; H10 regression → Task 10 Step 5.
- **`astera_labs` routes to cloud (microsoft/amazon), not nvidia** — deliberate deviation from the spec table to keep the edge forward rather than a back-edge into chips. Noted here so it is not "fixed" back.
- **New nodes carry no `cik`** — intentional (map-only; CIKs come with the deferred signal spec). `export_data.py` already handles missing cik (`n["cik"] or None`).
- **Edge count** is intentionally not asserted (brittle); tests assert specific pairs + no-orphans instead.
- If `npm run test -- <file>` filtering syntax differs in this vitest version, fall back to `npm run test` (runs all) — the suites are fast.
