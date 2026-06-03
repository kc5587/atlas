<script lang="ts">
  import type { Graph, Series } from "../lib/types";
  import LeadLagChart from "./LeadLagChart.svelte";
  let { graph, series, nodeId, onClose = () => {} }:
    { graph: Graph; series: Series; nodeId: string; onClose?: () => void } = $props();
  const node = $derived(graph.nodes.find((n) => n.id === nodeId));
  const ticker = $derived(node?.tickers[0] ?? "");
  const price = $derived(series.prices[ticker] ?? []);
  const fundamentals = $derived(ticker ? series.fundamentals?.[ticker] : undefined);
</script>

{#if node}
  <aside class="panel" role="dialog" aria-label={`${node.name} details`}>
    <button class="close" onclick={onClose} aria-label="Close panel">×</button>
    <h3>{node.name}</h3>
    <p class="meta">{node.stage} · {node.region} · {node.tickers.join(", ")}</p>
    <h4>Cumulative return</h4>
    {#if price.length}
      <LeadLagChart points={price} />
    {:else}
      <p class="empty">No price series available.</p>
    {/if}
    {#if fundamentals}
      <h4>Capex</h4>
      <LeadLagChart points={fundamentals.capex} />
    {:else}
      <p class="empty">Fundamentals coming with Layer 2.</p>
    {/if}
  </aside>
{/if}

<style>
  .panel {
    position: absolute; top: 1rem; right: 1rem; z-index: 5; width: 360px;
    background: #111a2b; color: #e8eef6; padding: 1rem 1.2rem; border-radius: 12px;
    box-shadow: 0 8px 30px rgba(0, 0, 0, 0.5);
  }
  .close {
    position: absolute; top: 0.5rem; right: 0.6rem; background: none; border: 0;
    color: #9fb3c8; font-size: 1.3rem; cursor: pointer;
  }
  h3 { margin: 0 0 0.2rem; }
  h4 { margin: 1rem 0 0.4rem; font-size: 0.9rem; opacity: 0.85; }
  .meta { opacity: 0.7; font-size: 0.85rem; }
  .empty { opacity: 0.55; font-size: 0.8rem; font-style: italic; }
</style>
