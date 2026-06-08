<script lang="ts">
  import { FDR_ALPHA, negLog10Q, volcanoPoints } from "../../lib/paper";
  import type { Signal } from "../../lib/signals";

  let { signals }: { signals: Signal[] } = $props();

  const W = 760;
  const H = 440;
  const m = { t: 26, r: 30, b: 54, l: 60 };
  const PW = W - m.l - m.r;
  const PH = H - m.t - m.b;
  const xs = (slope: number) => m.l + ((slope + 0.1) / 0.6) * PW;
  const ys = (y: number) => m.t + PH - (y / 2.6) * PH;
  const pts = $derived(volcanoPoints(signals));
  const fdrY = ys(negLog10Q(FDR_ALPHA)!);
  const xticks = [-0.1, 0, 0.1, 0.2, 0.3, 0.4, 0.5];
  const yticks: [number, string][] = [[1, "1.0"], [0.1, "0.1"], [0.01, ".01"]];
  const fill = (v: Signal["verdict"]) => (
    v === "confirmed" ? "var(--blue)" : v === "suggestive" ? "var(--suggest)" : "#fcfbf8"
  );
  const stroke = (v: Signal["verdict"]) => (
    v === "null" ? "var(--null)" : v === "suggestive" ? "var(--suggest)" : "var(--blue)"
  );
</script>

<svg viewBox="0 0 {W} {H}" role="img" aria-label="Volcano plot of all slope hypotheses">
  <line x1={m.l} y1={m.t} x2={m.l} y2={m.t + PH} stroke="var(--ink)" />
  <line x1={m.l} y1={m.t + PH} x2={m.l + PW} y2={m.t + PH} stroke="var(--ink)" />
  {#each xticks as v}
    <line x1={xs(v)} y1={m.t + PH} x2={xs(v)} y2={m.t + PH + 5} stroke="var(--ink)" />
    <text x={xs(v)} y={m.t + PH + 18} text-anchor="middle" font-family="var(--mono)" font-size="11" fill="var(--muted)">{v.toFixed(1)}</text>
  {/each}
  {#each yticks as [q, lab]}
    <text x={m.l - 9} y={ys(negLog10Q(q)!) + 4} text-anchor="end" font-family="var(--mono)" font-size="11" fill="var(--muted)">q={lab}</text>
  {/each}
  <line x1={xs(0)} y1={m.t} x2={xs(0)} y2={m.t + PH} stroke="var(--rule-2)" stroke-dasharray="2 4" />
  <line x1={m.l} y1={fdrY} x2={m.l + PW} y2={fdrY} stroke="var(--red)" stroke-width="1.2" stroke-dasharray="5 4" />
  <text x={m.l + PW} y={fdrY - 7} text-anchor="end" font-family="var(--mono)" font-size="11" fill="var(--red)">FDR q = 0.10</text>
  <text x={m.l + PW / 2} y={H - 12} text-anchor="middle" font-family="var(--serif)" font-style="italic" font-size="14" fill="var(--ink-soft)">effect size (slope)</text>
  {#each pts as p}
    <circle cx={xs(p.slope)} cy={ys(p.y)} r={p.verdict === "confirmed" ? 6 : 5} fill={fill(p.verdict)} stroke={stroke(p.verdict)} stroke-width="1.4" />
    <text
      x={p.slope > 0.33 ? xs(p.slope) - 10 : xs(p.slope) + 10}
      y={ys(p.y) + 4}
      text-anchor={p.slope > 0.33 ? "end" : "start"}
      font-family="var(--mono)"
      font-size={p.verdict === "null" ? 10 : 11}
      fill={p.verdict === "null" ? "var(--muted)" : "var(--ink)"}
    >{p.id}</text>
  {/each}
</svg>
