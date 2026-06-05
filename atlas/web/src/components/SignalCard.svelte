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
  {#if signal.chart.type === "capex_revenue_overlay"}
    <ul class="edges">
      {#each signal.detail_rows as r}
        <li><span>{r.left} → {r.right}</span>
          <b>slope {Number(r.slope).toFixed(2)}</b>
          <span class="ci">[{Number(r.slope_lo).toFixed(2)}, {Number(r.slope_hi).toFixed(2)}]</span>
          <span class="lag">lag {r.lag}Q · n={r.n_quarters}</span></li>
      {/each}
    </ul>
  {/if}
  {#if signal.chart.type === "capex_price"}
    <p class="legend">Confirmed = <b>not yet priced in</b> · Null = priced in</p>
    <ul class="edges">
      {#each signal.detail_rows as r}
        <li><span>{r.left} → {r.right}</span>
          <b>slope {Number(r.slope).toFixed(2)}</b>
          <span class="ci">[{Number(r.slope_lo).toFixed(2)}, {Number(r.slope_hi).toFixed(2)}]</span>
          <span class="lag">{r.horizon}d · n={r.n_obs}</span></li>
      {/each}
    </ul>
  {/if}
  {#if signal.chart.type === "event_drift"}
    <ul class="edges">
      {#each signal.detail_rows as r}
        <li><span>+surprise drift {Number(r.pos_drift).toFixed(3)}</span>
          <span>-surprise {Number(r.neg_drift).toFixed(3)}</span>
          <b>slope {Number(r.slope).toFixed(3)}</b>
          <span class="lag">{r.horizon}d · n={r.n_events}</span></li>
      {/each}
    </ul>
  {/if}
  {#if signal.chart.type === "vrp_term"}
    <p class="legend">Variance risk premium = implied² − realized² (annualized)</p>
    <ul class="edges">
      {#each signal.detail_rows as r}
        <li><span>{r.pair}</span>
          <b>VRP {Number(r.mean_vrp).toFixed(4)}</b>
          <span class="ci">[{Number(r.vrp_lo).toFixed(4)}, {Number(r.vrp_hi).toFixed(4)}]</span>
          <span class="lag">ΔR² {Number(r.incremental_oos_r2).toFixed(3)} · n={r.n_obs}</span></li>
      {/each}
    </ul>
  {/if}
  {#if signal.chart.type === "termstructure_timing"}
    <p class="legend">Slope of forward return on VIX/VIX3M (one-sided, FDR-corrected)</p>
    <ul class="edges">
      {#each signal.detail_rows as r}
        <li><span>{r.target} · {r.horizon}d</span>
          <b>slope {Number(r.slope).toFixed(2)}</b>
          <span class="ci">[{Number(r.slope_lo).toFixed(2)}, {Number(r.slope_hi).toFixed(2)}]</span>
          <span class="lag">q={Number(r.q_value).toFixed(2)} · sign {Number(r.oos_sign_rate).toFixed(2)}</span></li>
      {/each}
    </ul>
  {/if}
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
  .legend { font-size:.74rem; opacity:.7; margin:.4rem 0 .2rem; }
  .edges { list-style:none; padding:0; margin:.5rem 0 0; font-size:.78rem; }
  .edges li { display:flex; gap:.5rem; justify-content:space-between; padding:.15rem 0;
    border-top:1px solid #1b2740; }
  .edges .ci,.edges .lag { opacity:.55; }
  .caveat { font-size:.74rem; color:#b58a6a; margin:.3rem 0 0; }
</style>
