<script lang="ts">
  import "../lib/paper.css";
  import { correlogramPoints, eventStudyPoints, vrpSeriesPoints } from "../lib/paper";
  import type { Signal } from "../lib/signals";
  import type { Graph } from "../lib/types";
  import CorrelogramFigure from "./paper/CorrelogramFigure.svelte";
  import EvidenceStrip from "./paper/EvidenceStrip.svelte";
  import EventStudyFigure from "./paper/EventStudyFigure.svelte";
  import Figure from "./paper/Figure.svelte";
  import Hypothesis from "./paper/Hypothesis.svelte";
  import ResultsTable from "./paper/ResultsTable.svelte";
  import Sidenote from "./paper/Sidenote.svelte";
  import ValueChainFigure from "./paper/ValueChainFigure.svelte";
  import VolcanoFigure from "./paper/VolcanoFigure.svelte";
  import VrpFigure from "./paper/VrpFigure.svelte";

  let {
    graph,
    signals,
    correlogram = null,
    vrp = null,
  }: {
    graph: Graph;
    signals: Signal[];
    correlogram?: unknown;
    vrp?: unknown;
  } = $props();

  const n = $derived({
    c: signals.filter((s) => s.verdict === "confirmed").length,
    s: signals.filter((s) => s.verdict === "suggestive").length,
    n: signals.filter((s) => s.verdict === "null").length,
  });
  // §4 headline figures reserve 3-6 for forest, correlogram, event-study, and VRP.
  const findings = $derived(signals.filter((s) => s.detail_rows.length > 0));
  const evidenceSignal = $derived(signals.find((signal) => signal.evidence_chain.length > 0));
  const correlogramVM = $derived(correlogramPoints(correlogram));
  const vrpVM = $derived(vrpSeriesPoints(vrp));
  const detailFigureNo = (_signal: Signal, index: number) => (index === 0 ? 3 : index + 7);
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
    <p>Figure 2 plots each slope hypothesis by its standardized effect (a t-statistic) against
    selection-aware significance, with the false-discovery threshold drawn explicitly.<sup class="ref">2</sup></p>
  </section>
  <Sidenote n={2}>q-values are Benjamini–Hochberg adjusted within each family over finite, eligible edges. The dashed line is q = 0.10. H0 (an edge count) and H6 (variance premium, criterion-based) are reported in Table 1.</Sidenote>

  <Figure n={2}>
    {#snippet caption()}
      <em>Volcano plot.</em> Standardized effect (t = slope ÷ SE) versus −log<sub>10</sub> q for all slope hypotheses; the t-statistic makes heterogeneous slopes comparable. Points above the dashed line clear FDR control at q = 0.10.
    {/snippet}
    <VolcanoFigure {signals} />
  </Figure>

  <div class="body"><ResultsTable {signals} /></div>

  <section class="body">
    <h2 class="sec"><span class="hn num">3</span>Method</h2>
    <p>Every verdict is the end of a fixed evidence chain: a raw contemporaneous correlation, the same
    relationship after de-beta'ing market and sector factors (M2), an out-of-sample sign-retention check,
    and a selection-aware q-value that already accounts for the lag/horizon search. A hypothesis is
    <em>confirmed</em> only when the selection-aware q clears Benjamini–Hochberg control within its family
    and the effect carries the expected sign; <em>suggestive</em> rests on the slope CI alone; everything
    else is <em>null</em>. "Contradicts" is reserved for a statistically significant reversal.<sup class="ref">3</sup></p>
  </section>
  <Sidenote n={3}>Nulls surface the closest-to-significant edge, so each card shows that even the strongest
  link does not pass — "priced in", not "not looked at".</Sidenote>

  <section class="body">
    <h2 class="sec"><span class="hn num">4</span>Findings</h2>
    <p>Each hypothesis is reported with its within-family detail: the individual edges, cells, or
    indicators that compose it, shown as effect sizes with confidence intervals.</p>
  </section>

  {#each findings as s, i}
    <Hypothesis signal={s} section={`4.${i + 1}`} figureNo={detailFigureNo(s, i)} />
    {#if s.id === "H1" && correlogramVM}
      <Figure n={4}>
        {#snippet caption()}
          <em>Lead-lag cross-correlogram.</em> By-lag residual cross-correlation for
          {correlogramVM.pairLabel}; the shaded band is a block-bootstrap confidence
          interval and the labelled stem marks the selected peak.
        {/snippet}
        <CorrelogramFigure data={correlogramVM} />
      </Figure>
    {/if}
    {#if s.id === "H2"}
      {@const h2Event = eventStudyPoints(s)}
      {#if h2Event.length}
        <Figure n={5}>
          {#snippet caption()}
            <em>Event-study CAR by horizon.</em> The same H2 detail rows shown as a connected
            horizon profile; filled markers clear FDR control at q = 0.10.
          {/snippet}
          <EventStudyFigure points={h2Event} />
        </Figure>
      {/if}
    {/if}
    {#if s.id === "H6" && vrpVM}
      <Figure n={6}>
        {#snippet caption()}
          <em>Variance risk premium.</em> Implied variance (blue) sits persistently above
          subsequent realized variance (grey) for {vrpVM.label}: the options market charges
          a positive premium (H6).
        {/snippet}
        <VrpFigure data={vrpVM} />
      </Figure>
    {/if}
  {/each}

  <section class="body">
    <h2 class="sec"><span class="hn num">5</span>Thesis</h2>
    <p>The pattern across {signals.length} hypotheses is consistent with efficient pricing of slow,
    public fundamental signals: capex, the chip cycle, and power demand are largely <em>priced in</em>
    by the time they are observable. Two exceptions survive — genuine capex→revenue propagation along
    the supply chain (H1, with H11 suggestive), and a compensated volatility risk premium (H6, H7) that
    pays for bearing stress rather than offering free alpha. The eight nulls are not gaps in the search;
    they are the finding. An honest board reports what the market has already arbitraged away.</p>
  </section>
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

  :global(.paper .body) {
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
