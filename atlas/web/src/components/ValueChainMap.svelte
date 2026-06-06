<script lang="ts">
  import * as d3 from "d3";
  import { computeLayout } from "../lib/layout";
  import { edgeStyle, leadLagFor } from "../lib/leadlag";
  import type { Graph, LeadLag } from "../lib/types";
  import { stageOrder, STAGE_COLOR, STAGE_LABEL } from "../lib/stages";

  let { graph, leadlag, highlight = null, showLeadLag = false, mode = "story", onSelect = (_: string) => {} }:
    { graph: Graph; leadlag: LeadLag[]; highlight?: Set<string> | null; showLeadLag?: boolean;
      mode?: "story" | "explore"; onSelect?: (id: string) => void } = $props();

  let svgEl: SVGSVGElement;
  let width = $state(960);
  let height = $state(560);

  const HEADER_Y = 22;
  // Reserve left space in STORY mode so the leftmost (equipment) column clears
  // the ~460px narrative card. EXPLORE mode pans/zooms freely, so no inset.
  const STORY_LEFT_INSET = 460;

  $effect(() => {
    if (!svgEl) return;
    const leftInset = mode === "story" ? STORY_LEFT_INSET : 0;
    const STAGES = stageOrder(mode).map((key) => ({ key, label: STAGE_LABEL[key] }));
    const { nodes, edges } = computeLayout(graph, { width, height, leftInset, mode });
    const byId = new Map(nodes.map((n) => [n.id, n]));
    const svg = d3.select(svgEl);
    svg.selectAll("*").remove();
    const g = svg.append("g");

    if (mode === "explore") {
      svg.call(
        d3.zoom<SVGSVGElement, unknown>().scaleExtent([0.5, 4])
          .on("zoom", (e) => g.attr("transform", e.transform.toString())),
      );
    }

    // Stage column headers (don't rely on color alone)
    const colCount = STAGES.length;
    const pad = 60;
    const left = pad + leftInset;
    const right = width - pad;
    const colX = (i: number) => left + (i * (right - left)) / (colCount - 1);
    g.selectAll("text.stage-header").data(STAGES).join("text")
      .attr("class", "stage-header")
      .attr("x", (_, i) => colX(i))
      .attr("y", HEADER_Y)
      .attr("text-anchor", "middle")
      .attr("font-size", 12)
      .attr("font-weight", 700)
      .attr("letter-spacing", "0.08em")
      .attr("fill", (d) => STAGE_COLOR[d.key])
      .text((d) => d.label);

    g.selectAll("path.edge").data(edges).join("path")
      .attr("class", "edge")
      .attr("d", (e) => {
        const a = byId.get(e.from_id)!, b = byId.get(e.to_id)!;
        const mx = (a.x + b.x) / 2;
        return `M${a.x},${a.y} C${mx},${a.y} ${mx},${b.y} ${b.x},${b.y}`;
      })
      .attr("fill", "none")
      .attr("stroke", (e) => (e.isBack ? "#c0883a" : "#7aa2c8"))
      .attr("stroke-dasharray", (e) => (e.isBack ? "4 3" : null))
      .attr("stroke-width", (e) => {
        if (!showLeadLag) return 1.25;
        return edgeStyle(leadLagFor(leadlag, e.from_id, e.to_id), 0.1).width;
      })
      .attr("opacity", (e) => {
        if (dim(e.from_id, e.to_id)) return 0.08;
        if (!showLeadLag) return 0.5;
        const row = leadLagFor(leadlag, e.from_id, e.to_id);
        const st = edgeStyle(row, 0.1);
        // Mute non-significant edges hard so the map doesn't imply causation.
        return st.significant ? st.opacity : 0.15;
      })
      .each(function (e) {
        if (!showLeadLag) return;
        const row = leadLagFor(leadlag, e.from_id, e.to_id);
        if (!row) return;
        const st = edgeStyle(row, 0.1);
        const isEdge = row.pair_type === "edge";
        // Pulses: only with prefers-reduced-motion: no-preference, only on
        // pair_type === "edge" significant + stable edges. Encodes direction.
        if (isEdge && st.significant) {
          d3.select(this)
            .attr("stroke-dashoffset", 0)
            .append("title").text(`lag ${Math.abs(row.lag)} d (q=${row.q_value.toFixed(3)})`);
        }
      });

    // Pulse animation: direction-only, gated on reduced-motion media query.
    if (showLeadLag && typeof window !== "undefined"
        && window.matchMedia("(prefers-reduced-motion: no-preference)").matches) {
      g.selectAll<SVGPathElement, (typeof edges)[number]>("path.edge")
        .filter((e) => {
          const row = leadLagFor(leadlag, e.from_id, e.to_id);
          return !!row && row.pair_type === "edge" && edgeStyle(row, 0.1).significant
            && !dim(e.from_id, e.to_id);
        })
        .attr("stroke-dasharray", "6 8")
        .each(function (e) {
          const row = leadLagFor(leadlag, e.from_id, e.to_id)!;
          const delay = edgeStyle(row, 0.1).pulseDelayMs;
          const path = d3.select(this);
          const animate = () => {
            path.attr("stroke-dashoffset", 28)
              .transition().duration(900).ease(d3.easeLinear)
              .attr("stroke-dashoffset", 0)
              .on("end", animate);
          };
          window.setTimeout(animate, delay);
        });
    }

    // Numeric lag labels on significant edges (the readable encoding).
    if (showLeadLag) {
      const sigEdges = edges.filter((e) => {
        const row = leadLagFor(leadlag, e.from_id, e.to_id);
        return !!row && edgeStyle(row, 0.1).significant && !dim(e.from_id, e.to_id);
      });
      g.selectAll("text.lag-label").data(sigEdges).join("text")
        .attr("class", "lag-label")
        .attr("x", (e) => (byId.get(e.from_id)!.x + byId.get(e.to_id)!.x) / 2)
        .attr("y", (e) => (byId.get(e.from_id)!.y + byId.get(e.to_id)!.y) / 2 - 4)
        .attr("text-anchor", "middle")
        .attr("font-size", 10)
        .attr("fill", "#e8eef6")
        .attr("pointer-events", "none")
        .text((e) => {
          const row = leadLagFor(leadlag, e.from_id, e.to_id)!;
          return `≈${Math.abs(row.lag)} d`;
        });
    }

    const node = g.selectAll("g.node").data(nodes).join("g")
      .attr("class", "node")
      .attr("transform", (n) => `translate(${n.x},${n.y})`)
      .style("cursor", "pointer")
      .on("click", (_, n) => onSelect(n.id));
    node.append("circle")
      .attr("r", (n) => 8 + 3 * Math.sqrt(n.criticality))
      .attr("fill", (n) => STAGE_COLOR[n.stage])
      .attr("opacity", (n) => (dimNode(n.id) ? 0.12 : 1));
    node.append("circle")
      .attr("class", "hit-target")
      .attr("r", 28)
      .attr("fill", "transparent")
      .attr("pointer-events", "all");
    // SR a11y: each node gets a <title> with name + stage + ticker.
    node.append("title")
      .text((n) => `${n.name} — ${n.stage}${n.tickers.length ? ` (${n.tickers.join(", ")})` : ""}`);
    node.append("text").text((n) => n.name).attr("y", -16)
      .attr("text-anchor", "middle").attr("font-size", 11)
      .attr("fill", "#e8eef6").attr("opacity", (n) => (dimNode(n.id) ? 0.15 : 1));

    function dimNode(id: string) { return highlight != null && !highlight.has(id); }
    function dim(a: string, b: string) { return highlight != null && !(highlight.has(a) && highlight.has(b)); }

    return () => {
      // Cleanup so zoom handlers don't accumulate across re-renders.
      svg.on(".zoom", null);
    };
  });


</script>

<div class="map-wrap">
  <svg bind:this={svgEl} viewBox={`0 0 ${width} ${height}`} style="width:100%;height:100%;background:#0d1422" role="img" aria-label="AI value chain map"></svg>
  <div class="legend" aria-hidden="true">
    {#each stageOrder(mode) as s}
      <span><i style="background:{STAGE_COLOR[s]}"></i>{STAGE_LABEL[s].charAt(0) + STAGE_LABEL[s].slice(1).toLowerCase()}</span>
    {/each}
    <span class="sep"><i class="solid"></i>forward</span>
    <span><i class="dashed"></i>back/in-house</span>
  </div>
</div>

<style>
  .map-wrap { position: relative; width: 100%; height: 100%; }
  .legend {
    position: absolute; top: .6rem; left: .8rem; display: flex; flex-wrap: wrap; gap: .8rem;
    font-size: .72rem; color: #9fb3c8; background: rgba(13,20,34,0.6); padding: .35rem .6rem;
    border-radius: 8px;
  }
  .legend span { display: inline-flex; align-items: center; gap: .3rem; }
  .legend i { width: 12px; height: 12px; border-radius: 3px; display: inline-block; }
  .legend i.solid { height: 0; border-top: 2px solid #7aa2c8; border-radius: 0; }
  .legend i.dashed { height: 0; border-top: 2px dashed #c0883a; border-radius: 0; }
  .legend .sep { margin-left: .4rem; }
</style>
