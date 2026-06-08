<script lang="ts">
  import type { EventStudyPoint } from "../../lib/paper";

  let { points }: { points: EventStudyPoint[] } = $props();

  const W = 760;
  const H = 260;
  const m = { t: 18, r: 26, b: 42, l: 58 };
  const PW = W - m.l - m.r;
  const PH = H - m.t - m.b;

  const h0 = $derived(points[0].horizon);
  const h1 = $derived(points[points.length - 1].horizon);
  const xs = (horizon: number) => m.l + ((horizon - h0) / (h1 - h0 || 1)) * PW;
  const domain = $derived.by((): [number, number] => {
    const vals = points.flatMap((p) => [p.effect, p.lo ?? p.effect, p.hi ?? p.effect]);
    const lo = Math.min(0, ...vals);
    const hi = Math.max(0, ...vals);
    const pad = (hi - lo) * 0.12 || 0.01;
    return [lo - pad, hi + pad];
  });
  const ys = (value: number) => m.t + PH - ((value - domain[0]) / (domain[1] - domain[0])) * PH;
  const path = $derived(points
    .map((p, i) => `${i ? "L" : "M"} ${xs(p.horizon)} ${ys(p.effect)}`)
    .join(" "));
</script>

<svg viewBox="0 0 {W} {H}" role="img" aria-label="Event-study drift by horizon">
  <line x1={m.l} y1={ys(0)} x2={m.l + PW} y2={ys(0)} stroke="var(--rule-2)" stroke-dasharray="2 4" />
  <line x1={m.l} y1={m.t + PH} x2={m.l + PW} y2={m.t + PH} stroke="var(--ink)" />
  <path d={path} fill="none" stroke="var(--blue)" stroke-width="1.4" />
  {#each points as p}
    {#if p.lo != null && p.hi != null}
      <line x1={xs(p.horizon)} y1={ys(p.lo)} x2={xs(p.horizon)} y2={ys(p.hi)} stroke={p.passes ? "var(--blue)" : "var(--null)"} stroke-width="1.2" />
    {/if}
    <circle
      cx={xs(p.horizon)}
      cy={ys(p.effect)}
      r="4.2"
      fill={p.passes ? "var(--blue)" : "#fcfbf8"}
      stroke={p.passes ? "var(--blue)" : "var(--null)"}
      stroke-width="1.3"
    />
    <text x={xs(p.horizon)} y={m.t + PH + 18} text-anchor="middle" font-family="var(--mono)" font-size="11" fill="var(--muted)">{p.horizon}d</text>
  {/each}
  <text
    x={m.l + PW / 2}
    y={H - 8}
    text-anchor="middle"
    font-family="var(--serif)"
    font-style="italic"
    font-size="13"
    fill="var(--ink-soft)"
  >
    post-event cumulative abnormal return slope by horizon
  </text>
</svg>
