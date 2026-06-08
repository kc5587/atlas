<script lang="ts">
  import type { VrpSeries } from "../../lib/paper";

  let { data }: { data: VrpSeries } = $props();

  const W = 760;
  const H = 300;
  const m = { t: 16, r: 24, b: 40, l: 56 };
  const PW = W - m.l - m.r;
  const PH = H - m.t - m.b;

  const t0 = $derived(data.points[0].date.getTime());
  const t1 = $derived(data.points[data.points.length - 1].date.getTime());
  const xs = (d: Date) => m.l + ((d.getTime() - t0) / (t1 - t0 || 1)) * PW;
  const vMax = $derived(
    Math.max(...data.points.flatMap((p) => [p.impliedVar, p.realizedVar])) || 0.1,
  );
  const ys = (v: number) => m.t + PH - (v / vMax) * PH;
  const path = (key: "impliedVar" | "realizedVar") => data.points
    .map((p, i) => `${i ? "L" : "M"} ${xs(p.date)} ${ys(p[key])}`)
    .join(" ");
</script>

<svg viewBox="0 0 {W} {H}" role="img" aria-label="Variance risk premium series">
  <line x1={m.l} y1={m.t + PH} x2={m.l + PW} y2={m.t + PH} stroke="var(--ink)" />
  <path d={path("realizedVar")} fill="none" stroke="var(--null)" stroke-width="1.2" />
  <path d={path("impliedVar")} fill="none" stroke="var(--blue)" stroke-width="1.4" />
  <text
    x={m.l + PW}
    y={m.t + 4}
    text-anchor="end"
    font-family="var(--mono)"
    font-size="11"
    fill="var(--blue)"
  >implied²</text>
  <text
    x={m.l + PW}
    y={m.t + 18}
    text-anchor="end"
    font-family="var(--mono)"
    font-size="11"
    fill="var(--null)"
  >realized²</text>
  <text
    x={m.l + PW / 2}
    y={H - 8}
    text-anchor="middle"
    font-family="var(--serif)"
    font-style="italic"
    font-size="13"
    fill="var(--ink-soft)"
  >
    annualized variance · {data.label}
  </text>
</svg>
