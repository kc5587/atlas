<script lang="ts">
  import type { Signal } from "../../lib/signals";
  import { detailCoefficients } from "../../lib/paper";
  let { signal }: { signal: Signal } = $props();

  const rows = $derived(detailCoefficients(signal));
  const W = 760;
  const rowH = 26;
  const m = { t: 14, r: 30, b: 34, l: 150 };
  const H = $derived(m.t + m.b + rows.length * rowH);
  const PW = W - m.l - m.r;
  const domain = $derived.by((): [number, number] => {
    const vals = rows.flatMap((r) => [r.effect, r.lo ?? r.effect, r.hi ?? r.effect]);
    const lo = Math.min(0, ...vals), hi = Math.max(0, ...vals);
    const pad = (hi - lo) * 0.08 || 0.1;
    return [lo - pad, hi + pad];
  });
  const xs = (v: number) => m.l + ((v - domain[0]) / (domain[1] - domain[0])) * PW;
</script>

{#if rows.length}
  <svg viewBox="0 0 {W} {H}" role="img" aria-label={`Coefficient plot for ${signal.id}`}>
    <line x1={xs(0)} y1={m.t} x2={xs(0)} y2={m.t + rows.length * rowH} stroke="var(--rule-2)" stroke-dasharray="2 4" />
    {#each rows as r, i}
      {@const y = m.t + i * rowH + rowH / 2}
      <text x={m.l - 12} {y} dy="4" text-anchor="end" font-family="var(--mono)" font-size="11" fill="var(--ink-soft)">{r.label}</text>
      {#if r.lo != null && r.hi != null}
        <line x1={xs(r.lo)} y1={y} x2={xs(r.hi)} y2={y} stroke={r.passes ? "var(--blue)" : "var(--null)"} stroke-width="1.4" />
      {/if}
      <circle cx={xs(r.effect)} cy={y} r="4" fill={r.passes ? "var(--blue)" : "#fcfbf8"} stroke={r.passes ? "var(--blue)" : "var(--null)"} stroke-width="1.4" />
    {/each}
    <line x1={m.l} y1={m.t + rows.length * rowH} x2={m.l + PW} y2={m.t + rows.length * rowH} stroke="var(--ink)" />
    <text x={m.l + PW / 2} y={H - 8} text-anchor="middle" font-family="var(--serif)" font-style="italic" font-size="13" fill="var(--ink-soft)">effect ± 95% CI (filled = clears FDR)</text>
  </svg>
{/if}
