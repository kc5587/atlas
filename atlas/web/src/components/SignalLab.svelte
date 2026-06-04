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
