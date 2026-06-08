<script lang="ts">
  import { tableRows } from "../../lib/paper";
  import type { Signal } from "../../lib/signals";

  let { signals }: { signals: Signal[] } = $props();

  const rows = $derived(tableRows(signals));
  const cls = (v: string) => (v === "confirmed" ? "c" : v === "suggestive" ? "s" : "n");
</script>

<table class="t1">
  <caption>Table 1 — Hypotheses, effect sizes, and verdicts</caption>
  <thead>
    <tr>
      <th>ID</th>
      <th>Claim</th>
      <th>slope</th>
      <th>q</th>
      <th>n</th>
      <th>verdict</th>
    </tr>
  </thead>
  <tbody>
    {#each rows as r}
      <tr>
        <td class="num">{r.id}</td>
        <td>{r.claim}</td>
        <td class="num">{r.slope.toFixed(2)}</td>
        <td class="num">{r.q == null ? "—" : r.q.toFixed(3)}</td>
        <td class="num">{r.n}</td>
        <td><span class="vd {cls(r.verdict)}">{r.verdict}</span></td>
      </tr>
    {/each}
  </tbody>
</table>

<style>
  .t1 {
    border-collapse: collapse;
    width: 100%;
    margin: 18px 0;
    font-size: 16px;
  }

  caption {
    font-family: var(--mono);
    font-size: 12px;
    color: var(--ink);
    text-align: left;
    padding-bottom: 8px;
    border-bottom: 2px solid var(--ink);
  }

  th {
    font-family: var(--mono);
    font-size: 11px;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    color: var(--muted);
    text-align: left;
    padding: 9px 10px;
    border-bottom: 1px solid var(--rule-2);
    font-weight: 500;
  }

  td {
    padding: 8px 10px;
    border-bottom: 1px solid var(--rule);
  }

  td.num {
    font-variant-numeric: tabular-nums;
    font-size: 14px;
    color: var(--ink-soft);
  }

  .vd {
    font-family: var(--mono);
    font-size: 11px;
    text-transform: uppercase;
  }

  .vd.c {
    color: var(--blue);
  }

  .vd.s {
    color: var(--suggest);
  }

  .vd.n {
    color: var(--muted);
  }
</style>
