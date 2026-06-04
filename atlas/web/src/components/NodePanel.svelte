<script lang="ts">
  import type { Graph, LeadLag, Series } from "../lib/types";
  import { formatPct, formatUSD, fundLeadLagFor, latestPoint } from "../lib/fundamentals";
  import LeadLagChart from "./LeadLagChart.svelte";
  let { graph, series, leadlag = [], nodeId, onClose = () => {} }:
    { graph: Graph; series: Series; leadlag?: LeadLag[]; nodeId: string; onClose?: () => void } = $props();
  const node = $derived(graph.nodes.find((n) => n.id === nodeId));
  const ticker = $derived(node?.tickers[0] ?? "");
  const price = $derived(series.prices[ticker] ?? []);
  const fundamentals = $derived(ticker ? series.fundamentals?.[ticker] : undefined);

  const latestRevenue = $derived(latestPoint(fundamentals?.revenue));
  const latestCapex = $derived(latestPoint(fundamentals?.capex));
  const latestMargin = $derived(latestPoint(fundamentals?.gross_margin));
  const capexPrice = $derived(node ? fundLeadLagFor(leadlag, node.id) : undefined);

  // A node carries Layer 2 fundamentals only if at least one metric has data.
  const hasFundamentals = $derived(!!(latestRevenue || latestCapex || latestMargin));

  function lagText(row: LeadLag): string {
    const d = Math.abs(row.lag);
    const dir = row.lag > 0 ? "capex leads price" : row.lag < 0 ? "price leads capex" : "coincident";
    return `${dir} by ≈${d} d · corr ${row.corr.toFixed(2)} · q ${row.q_value.toFixed(2)}`;
  }
</script>

{#if node}
  <aside class="panel" role="dialog" aria-label={`${node.name} details`}>
    <button class="close" onclick={onClose} aria-label="Close panel">×</button>
    <h3>{node.name}</h3>
    <p class="meta">{node.stage} · {node.region} · {node.tickers.join(", ")}</p>
    {#if node.cik}
      <p class="cik">SEC CIK {node.cik}</p>
    {:else}
      <p class="cik none">No SEC CIK in this layer</p>
    {/if}

    <h4>Cumulative return</h4>
    {#if price.length}
      <LeadLagChart points={price} />
    {:else}
      <p class="empty">No price series available.</p>
    {/if}

    <h4>SEC fundamentals</h4>
    {#if hasFundamentals}
      <dl class="facts">
        <dt>Revenue</dt>
        <dd>{formatUSD(latestRevenue?.value)} <span class="asof">{latestRevenue?.date ?? ""}</span></dd>
        <dt>Capex</dt>
        <dd>{formatUSD(latestCapex?.value)} <span class="asof">{latestCapex?.date ?? ""}</span></dd>
        <dt>Gross margin</dt>
        <dd>{formatPct(latestMargin?.value)} <span class="asof">{latestMargin?.date ?? ""}</span></dd>
      </dl>
      {#if capexPrice}
        <p class="leadlag">Capex→price: {lagText(capexPrice)}</p>
      {/if}
      {#if latestCapex}
        <h4>Capex history</h4>
        <LeadLagChart points={fundamentals!.capex} />
      {/if}
    {:else}
      <p class="empty">No SEC fundamentals in this layer.</p>
    {/if}
  </aside>
{/if}

<style>
  .panel {
    position: fixed; top: 1rem; right: 1rem; z-index: 5; width: min(360px, calc(100vw - 2rem));
    max-height: calc(100vh - 2rem); overflow-y: auto;
    background: #111a2b; color: #e8eef6; padding: 1rem 1.2rem; border-radius: 12px;
    box-shadow: 0 8px 30px rgba(0, 0, 0, 0.5);
  }
  .close {
    position: absolute; top: 0.5rem; right: 0.6rem; background: none; border: 0;
    color: #9fb3c8; font-size: 1.3rem; cursor: pointer;
  }
  h3 { margin: 0 0 0.2rem; }
  h4 { margin: 1rem 0 0.4rem; font-size: 0.9rem; opacity: 0.85; }
  .meta { opacity: 0.7; font-size: 0.85rem; margin: 0 0 0.2rem; }
  .cik { font-size: 0.75rem; margin: 0; color: #8fd0a8; }
  .cik.none { color: #b58a6a; font-style: italic; }
  .facts { display: grid; grid-template-columns: auto 1fr; gap: 0.15rem 0.8rem; margin: 0.2rem 0 0; font-size: 0.85rem; }
  .facts dt { opacity: 0.6; }
  .facts dd { margin: 0; text-align: right; font-variant-numeric: tabular-nums; }
  .asof { opacity: 0.45; font-size: 0.72rem; margin-left: 0.3rem; }
  .leadlag { font-size: 0.76rem; opacity: 0.8; margin: 0.5rem 0 0; }
  .empty { opacity: 0.55; font-size: 0.8rem; font-style: italic; }
</style>
