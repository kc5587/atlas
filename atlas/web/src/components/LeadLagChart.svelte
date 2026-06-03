<script lang="ts">
  import * as d3 from "d3";
  let { points = [] as { date: string; value: number | null }[] } = $props();
  let el: SVGSVGElement;
  $effect(() => {
    if (!el) return;
    const w = 320, h = 120, m = 24;
    const data = points.filter((p) => p.value != null) as { date: string; value: number }[];
    const svg = d3.select(el);
    svg.selectAll("*").remove();
    if (!data.length) return;
    const x = d3.scaleLinear([0, data.length - 1], [m, w - m]);
    const y = d3.scaleLinear(d3.extent(data, (d) => d.value) as [number, number], [h - m, m]);
    const line = d3.line<{ value: number }>().x((_, i) => x(i)).y((d) => y(d.value));
    svg.append("path").datum(data)
      .attr("fill", "none").attr("stroke", "#82b366").attr("stroke-width", 2)
      .attr("d", line as any);
  });
</script>

<svg bind:this={el} viewBox="0 0 320 120" style="width:100%"></svg>
