<script lang="ts">
  import type { Correlogram } from "../../lib/paper";

  let { data }: { data: Correlogram } = $props();

  const W = 760;
  const H = 300;
  const m = { t: 16, r: 24, b: 40, l: 48 };
  const PW = W - m.l - m.r;
  const PH = H - m.t - m.b;

  const xs = (lag: number) => m.l + ((lag + data.maxLag) / (2 * data.maxLag)) * PW;
  const yMax = $derived(
    Math.max(
      0.1,
      ...data.points.flatMap((p) => [Math.abs(p.ciHi), Math.abs(p.ciLo), Math.abs(p.corr)]),
    ),
  );
  const ys = (c: number) => m.t + PH / 2 - (c / yMax) * (PH / 2);
  const barW = $derived((PW / (2 * data.maxLag + 1)) * 0.6);
</script>

<svg viewBox="0 0 {W} {H}" role="img" aria-label="Lead-lag cross-correlogram">
  <path
    d={`M ${data.points.map((p) => `${xs(p.lag)} ${ys(p.ciHi)}`).join(" L ")}
        L ${[...data.points].reverse().map((p) => `${xs(p.lag)} ${ys(p.ciLo)}`).join(" L ")} Z`}
    fill="var(--rule-2)"
    opacity="0.35"
  />
  <line x1={m.l} y1={ys(0)} x2={m.l + PW} y2={ys(0)} stroke="var(--ink)" />
  {#each data.points as p}
    <rect
      x={xs(p.lag) - barW / 2}
      y={Math.min(ys(0), ys(p.corr))}
      width={barW}
      height={Math.abs(ys(p.corr) - ys(0))}
      fill={p.isPeak ? "var(--blue)" : p.passesFdr ? "var(--blue)" : "var(--null)"}
      opacity={p.isPeak ? 1 : p.passesFdr ? 0.7 : 0.4}
    />
  {/each}
  {#each data.points.filter((p) => p.isPeak) as p}
    <text
      x={xs(p.lag)}
      y={ys(p.corr) - 6}
      text-anchor="middle"
      font-family="var(--mono)"
      font-size="11"
      fill="var(--blue)"
    >peak λ={p.lag}</text>
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
    lag (trading days) · {data.pairLabel}
  </text>
</svg>
