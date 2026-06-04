<script lang="ts">
  import { onMount } from "svelte";
  import { loadAll } from "./lib/data";
  import { nodesWithCapex } from "./lib/fundamentals";
  import { SCENES } from "./lib/scenes";
  import { activeScene, mode, selectedNode, dataset } from "./stores";
  import ValueChainMap from "./components/ValueChainMap.svelte";
  import Scroller from "./components/Scroller.svelte";
  import NodePanel from "./components/NodePanel.svelte";
  import Controls from "./components/Controls.svelte";
  import SignalLab from "./components/SignalLab.svelte";

  let error = $state<string | null>(null);
  let data = $state<Awaited<ReturnType<typeof loadAll>> | null>(null);

  // Explore-mode stage filter (descoped time scrubber per council review).
  let stageFilter = $state<Set<string>>(new Set());

  onMount(async () => {
    try {
      data = await loadAll();
      dataset.set(data);
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
  });

  const scene = $derived(SCENES[$activeScene]);

  const storyHighlight = $derived.by(() => {
    if (!scene) return null;
    if (scene.highlightPath) return new Set(scene.highlightPath.flat());
    if (scene.focusStage && data)
      return new Set(
        data.graph.nodes.filter((n) => n.stage === scene.focusStage).map((n) => n.id),
      );
    // "The upstream pull" scene: spotlight nodes that carry SEC capex data.
    if (scene.showCapex && data) return nodesWithCapex(data.graph, data.series);
    return null;
  });

  // In explore mode, the highlight derives from the active stage filters.
  const exploreHighlight = $derived.by(() => {
    if (!data || stageFilter.size === 0) return null;
    return new Set(
      data.graph.nodes.filter((n) => stageFilter.has(n.stage)).map((n) => n.id),
    );
  });

  const highlight = $derived($mode === "explore" ? exploreHighlight : storyHighlight);

  function toggleStage(s: string) {
    const next = new Set(stageFilter);
    if (next.has(s)) next.delete(s);
    else next.add(s);
    stageFilter = next;
  }
</script>

<main>
  {#if error}
    <div class="state">Couldn’t load data: {error}</div>
  {:else if !data}
    <div class="state">Loading the value chain…</div>
  {:else}
    <div class="map-layer">
      <ValueChainMap
        graph={data.graph}
        leadlag={data.leadlag}
        highlight={highlight}
        showLeadLag={scene?.showLeadLag ?? false}
        mode={$mode === "lab" ? "story" : $mode}
        onSelect={(id) => selectedNode.set(id)}
      />
    </div>

    <!-- Scroller stays mounted across mode changes (toggling visibility avoids
         collapsing page height and bouncing scrollama). -->
    <div class="scroller-layer" class:hidden={$mode === "explore"} aria-hidden={$mode === "explore"}>
      <Scroller />
    </div>

    {#if $selectedNode}
      <NodePanel
        graph={data.graph}
        series={data.series}
        leadlag={data.leadlag}
        nodeId={$selectedNode}
        onClose={() => selectedNode.set(null)}
      />
    {/if}

    {#if $mode === "explore"}
      <Controls stages={data.meta.stages} active={stageFilter} onToggle={toggleStage} />
    {/if}

    {#if $mode === "lab"}
      <SignalLab />
    {:else}
      <button class="lab-entry" onclick={() => mode.set("lab")}>Signal Lab</button>
    {/if}

    <p class="caption">Correlation, not causation. Edge styling reflects measured lead/lag, not proven cause.</p>
  {/if}
</main>

<style>
  :global(body) { margin: 0; background: #0d1422; font-family: system-ui, sans-serif; }
  .map-layer { position: fixed; inset: 0; z-index: 1; }
  .scroller-layer { position: relative; z-index: 2; }
  .scroller-layer.hidden { visibility: hidden; pointer-events: none; }
  .state { position: fixed; inset: 0; display: grid; place-items: center; color: #9fb3c8; }
  .caption {
    position: fixed; bottom: 0.6rem; left: 50%; transform: translateX(-50%);
    z-index: 6; margin: 0; font-size: 0.72rem; color: #7d90a8;
    background: rgba(13, 20, 34, 0.7); padding: 0.3rem 0.7rem; border-radius: 8px;
    pointer-events: none; text-align: center; max-width: 90vw;
  }
  .lab-entry { position: fixed; top: 1rem; left: 1rem; z-index: 6;
    background: #1b2740; color: #cfe0f5; border: 0; border-radius: 8px;
    padding: .4rem .8rem; cursor: pointer; }
  main { position: relative; }
</style>
