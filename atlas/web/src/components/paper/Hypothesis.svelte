<script lang="ts">
  import type { Signal } from "../../lib/signals";
  import Figure from "./Figure.svelte";
  import EvidenceStrip from "./EvidenceStrip.svelte";
  import DetailFigure from "./DetailFigure.svelte";
  let { signal, section, figureNo }: { signal: Signal; section: string; figureNo: number } = $props();
  const cls = (v: string) => (v === "confirmed" ? "c" : v === "suggestive" ? "s" : "n");
</script>

<section class="hyp body">
  <h3 class="sub"><span class="hn num">{section}</span>{signal.title}
    <span class="vd {cls(signal.verdict)}">{signal.verdict}</span></h3>
  <p class="claim">{signal.claim}</p>
  <EvidenceStrip {signal} />
</section>

{#if signal.detail_rows.length}
  <Figure n={figureNo}>
    {#snippet caption()}
      <em>{signal.id} detail.</em> Per-edge effect with 95% confidence intervals; filled markers clear FDR control at q = 0.10.
    {/snippet}
    <DetailFigure {signal} />
  </Figure>
{/if}

<section class="hyp body">
  <ul class="caveats">
    {#each signal.caveats as c}<li>{c}</li>{/each}
  </ul>
</section>

<style>
  .sub { font-weight: 600; font-size: 19px; margin: 28px 0 .3rem; }
  .hn { font-family: var(--mono); font-size: 14px; color: var(--blue); margin-right: .5em; font-weight: 500; }
  .vd { font-family: var(--mono); font-size: 11px; text-transform: uppercase; margin-left: .5em; }
  .vd.c { color: var(--blue); } .vd.s { color: var(--suggest); } .vd.n { color: var(--muted); }
  .claim { font-style: italic; color: var(--ink-soft); margin: 0 0 .6rem; }
  .caveats { font-size: 14px; color: var(--muted); padding-left: 1.1rem; margin: 6px 0 0; }
  .caveats li { margin-bottom: 3px; }
</style>
