<script lang="ts">
  import type { Signal } from "../lib/signals";
  let { signal }: { signal: Signal } = $props();
  const badge = $derived({
    confirmed: "#82b366", suggestive: "#d79b00", null: "#7d90a8", contradicts: "#b5563a",
  }[signal.verdict] ?? "#7d90a8");
</script>

<article class="card">
  <header>
    <h3>{signal.id} · {signal.title}</h3>
    <span class="badge" style="background:{badge}">{signal.verdict}</span>
  </header>
  <p class="claim"><b>Claim:</b> {signal.claim}</p>
  <p class="mech"><b>Mechanism:</b> {signal.mechanism}</p>
  <ol class="chain">
    {#each signal.evidence_chain as step}
      <li>{step.stage}: <b>{step.value}</b> <span>{step.metric}</span></li>
    {/each}
  </ol>
  <p class="stat">
    {signal.stat.name} = {signal.stat.value}
    {#if signal.stat.ci}[{signal.stat.ci[0]}, {signal.stat.ci[1]}]{/if}
    {#if signal.stat.q_value != null} · q={signal.stat.q_value}{/if}
    · n={signal.stat.n}
  </p>
  {#each signal.caveats as c}<p class="caveat">⚠ {c}</p>{/each}
</article>

<style>
  .card { background:#111a2b; color:#e8eef6; border-radius:12px; padding:1rem 1.2rem;
    margin:0 0 1rem; box-shadow:0 4px 18px rgba(0,0,0,.4); }
  header { display:flex; justify-content:space-between; align-items:center; gap:1rem; }
  h3 { margin:0; font-size:1rem; }
  .badge { font-size:.7rem; text-transform:uppercase; letter-spacing:.06em;
    padding:.15rem .5rem; border-radius:6px; color:#0d1422; font-weight:700; }
  .claim,.mech { margin:.4rem 0; font-size:.85rem; }
  .chain { margin:.5rem 0; padding-left:1.1rem; font-size:.82rem; }
  .chain span { opacity:.5; }
  .stat { font-variant-numeric:tabular-nums; font-size:.82rem; opacity:.9; }
  .caveat { font-size:.74rem; color:#b58a6a; margin:.3rem 0 0; }
</style>
