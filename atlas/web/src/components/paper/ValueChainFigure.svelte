<script lang="ts">
  import { confirmedPairs, dagLayout } from "../../lib/paper";
  import type { Signal } from "../../lib/signals";
  import { stageOrder } from "../../lib/stages";
  import type { Graph } from "../../lib/types";

  let { graph, signals }: { graph: Graph; signals: Signal[] } = $props();

  const W = 920;
  const H = 380;
  const lay = $derived(dagLayout(graph, stageOrder("explore"), confirmedPairs(signals), W, H));
</script>

<svg viewBox="0 0 {W} {H}" role="img" aria-label="The AI value chain">
  {#each lay.edges as e}
    {@const mx = (e.x1 + e.x2) / 2}
    <path
      d={`M${e.x1 + 6},${e.y1} C${mx},${e.y1} ${mx},${e.y2} ${e.x2 - 7},${e.y2}`}
      fill="none"
      stroke={e.confirmed ? "var(--blue)" : "var(--rule)"}
      stroke-width={e.confirmed ? 1.6 : 0.9}
      opacity={e.confirmed ? 0.85 : 0.7}
    />
  {/each}
  {#each lay.nodes as n}
    <circle cx={n.x} cy={n.y} r="3.2" fill="var(--ink)" />
    <text x={n.x} y={n.y - 8} text-anchor="middle" font-family="var(--serif)" font-size="13" fill="var(--ink-soft)">{n.name}</text>
  {/each}
</svg>
