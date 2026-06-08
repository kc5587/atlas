<script lang="ts">
  import "../lib/paper.css";
  import type { Signal } from "../lib/signals";
  import type { Graph } from "../lib/types";
  import EvidenceStrip from "./paper/EvidenceStrip.svelte";
  import Figure from "./paper/Figure.svelte";
  import ResultsTable from "./paper/ResultsTable.svelte";
  import Sidenote from "./paper/Sidenote.svelte";
  import ValueChainFigure from "./paper/ValueChainFigure.svelte";
  import VolcanoFigure from "./paper/VolcanoFigure.svelte";

  let { graph, signals }: { graph: Graph; signals: Signal[] } = $props();

  const n = $derived({
    c: signals.filter((s) => s.verdict === "confirmed").length,
    s: signals.filter((s) => s.verdict === "suggestive").length,
    n: signals.filter((s) => s.verdict === "null").length,
  });
  const evidenceSignal = $derived(signals.find((signal) => signal.evidence_chain.length > 0));
</script>

<main class="paper page">
  <header class="body">
    <div class="kicker">Atlas · Working Paper · Draft, June 2026</div>
    <h1 class="title">Honest Signal Detection Across the AI Value Chain</h1>
    <p class="subtitle">Lead–lag structure, variance risk premia, and the discipline of the null result</p>
  </header>
  <hr class="rule heavy body" />

  <section class="abstract body">
    <span class="lbl">Abstract</span>
    <p>We test whether economically motivated signals propagate across the AI supply chain, or are
    arbitraged away. Each hypothesis is evaluated with a selection-aware bootstrap null,
    Benjamini–Hochberg control across declared families, and out-of-sample validation. Of {signals.length}
    hypotheses, <span class="num">{n.c}</span> are confirmed, <span class="num">{n.s}</span> suggestive,
    and <span class="num">{n.n}</span> null. The nulls are not failures; they are the result.</p>
  </section>

  {#if evidenceSignal}
    <section class="body evidence">
      <span class="lbl">Evidence Chain</span>
      <EvidenceStrip signal={evidenceSignal} />
    </section>
  {/if}

  <section class="body">
    <h2 class="sec"><span class="hn num">1</span>The value chain</h2>
    <p class="drop">The object of study is a directed graph of supplier relationships among the firms that
    build and operate AI infrastructure.<sup class="ref">1</sup> The question throughout is whether a shock
    at one node is informative about a later move downstream.</p>
  </section>
  <Sidenote n={1}>Nodes carry a CIK where a US filer exists; stage membership is fixed ex-ante and never tuned to a result.</Sidenote>

  <Figure n={1}>
    {#snippet caption()}
      The AI value chain. Hairline edges denote supplier relations; <span class="caption-blue">blue edges</span> mark confirmed capex→revenue propagation (H1, H11).
    {/snippet}
    <ValueChainFigure {graph} {signals} />
  </Figure>

  <section class="body">
    <h2 class="sec"><span class="hn num">2</span>The testing campaign at a glance</h2>
    <p>Figure 2 plots each slope hypothesis by effect size against selection-aware significance, with the
    false-discovery threshold drawn explicitly.<sup class="ref">2</sup></p>
  </section>
  <Sidenote n={2}>q-values are Benjamini–Hochberg adjusted within each family over finite, eligible edges. The dashed line is q = 0.10. H0 (an edge count) and H6 (variance premium, criterion-based) are reported in Table 1.</Sidenote>

  <Figure n={2}>
    {#snippet caption()}
      <em>Volcano plot.</em> Effect size versus −log<sub>10</sub> q for all slope hypotheses. Points above the dashed line clear FDR control at q = 0.10.
    {/snippet}
    <VolcanoFigure {signals} />
  </Figure>

  <div class="body"><ResultsTable {signals} /></div>
</main>

<style>
  .page {
    max-width: 1120px;
    margin: 0 auto;
    padding: 84px 40px 120px;
    display: grid;
    grid-template-columns: minmax(0, 680px) 36px 230px;
    justify-content: center;
  }

  .body {
    grid-column: 1;
  }

  :global(.paper figure),
  :global(.paper .sidenote) {
    grid-column: 1 / -1;
  }

  :global(.paper aside.sidenote) {
    grid-column: 3;
  }

  .kicker {
    font-family: var(--mono);
    font-size: 12px;
    letter-spacing: 0.22em;
    text-transform: uppercase;
    color: var(--muted);
  }

  .title {
    font-weight: 600;
    font-size: 40px;
    line-height: 1.12;
    margin: 0.5rem 0 0;
  }

  .subtitle {
    font-style: italic;
    color: var(--ink-soft);
    font-size: 22px;
    margin-top: 10px;
  }

  .rule.heavy {
    border: 0;
    border-top: 2px solid var(--ink);
    margin: 26px 0;
  }

  .abstract {
    font-size: 18px;
    color: var(--ink-soft);
  }

  .evidence {
    margin: 10px 0 28px;
  }

  .lbl {
    font-family: var(--mono);
    font-size: 11px;
    letter-spacing: 0.18em;
    text-transform: uppercase;
    color: var(--muted);
    display: block;
    margin-bottom: 6px;
  }

  .sec {
    font-weight: 600;
    font-size: 24px;
    margin: 0 0 0.4rem;
  }

  .hn {
    font-size: 16px;
    color: var(--blue);
    margin-right: 0.6em;
    font-weight: 500;
  }

  p {
    margin: 0 0 1.05rem;
    text-align: justify;
    hyphens: auto;
  }

  .drop::first-letter {
    font-size: 3.1em;
    line-height: 0.86;
    float: left;
    padding: 0.06em 0.08em 0 0;
    font-weight: 600;
  }

  .ref {
    font-family: var(--mono);
    font-size: 0.62em;
    color: var(--blue);
  }

  .caption-blue {
    color: var(--blue);
  }

  @media (max-width: 980px) {
    .page {
      grid-template-columns: 1fr;
      padding: 54px 22px 90px;
    }

    :global(.paper aside.sidenote) {
      grid-column: 1;
      margin: 6px 0 20px;
    }
  }
</style>
