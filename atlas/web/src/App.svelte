<script lang="ts">
  import { onMount } from "svelte";
  import Paper from "./components/Paper.svelte";
  import { loadAll, loadOptionalJSON } from "./lib/data";
  import { loadSignals } from "./lib/signals";
  import type { Signal } from "./lib/signals";

  let error = $state<string | null>(null);
  let data = $state<Awaited<ReturnType<typeof loadAll>> | null>(null);
  let signals = $state<Signal[]>([]);
  let correlogram = $state<unknown | null>(null);
  let vrp = $state<unknown | null>(null);

  onMount(async () => {
    try {
      [data, signals, correlogram, vrp] = await Promise.all([
        loadAll(),
        loadSignals(),
        loadOptionalJSON("data/correlogram.json"),
        loadOptionalJSON("data/vrp.json"),
      ]);
    } catch (e) {
      error = e instanceof Error ? e.message : String(e);
    }
  });
</script>

{#if error}
  <p class="state error">Failed to load: {error}</p>
{:else if data}
  <Paper graph={data.graph} {signals} {correlogram} {vrp} />
{:else}
  <p class="state">Loading…</p>
{/if}

<style>
  :global(body) {
    margin: 0;
    background: #fbfaf6;
  }

  .state {
    font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    padding: 40px;
    color: #8a8377;
  }

  .error {
    color: #9b2d2d;
  }
</style>
