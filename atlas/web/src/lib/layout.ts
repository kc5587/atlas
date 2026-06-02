// src/lib/layout.ts
import type { Edge, Graph, Node, Stage } from "./types";

const STAGE_ORDER: Stage[] = ["equipment", "foundry", "chips", "cloud"];

export interface PositionedNode extends Node { x: number; y: number; col: number; }
export interface RoutedEdge extends Edge { isBack: boolean; }
export interface LayoutOpts { width: number; height: number; padding?: number; }

export function computeLayout(graph: Graph, opts: LayoutOpts) {
  const pad = opts.padding ?? 60;
  const cols = STAGE_ORDER;
  const colX = (i: number) =>
    cols.length === 1 ? opts.width / 2 : pad + (i * (opts.width - 2 * pad)) / (cols.length - 1);

  const byStage = new Map<Stage, Node[]>();
  for (const s of cols) byStage.set(s, []);
  for (const n of graph.nodes) (byStage.get(n.stage) ?? byStage.get("chips"))!.push(n);

  // initial y: evenly spaced within each column
  const pos = new Map<string, PositionedNode>();
  cols.forEach((s, ci) => {
    const list = byStage.get(s)!;
    list.forEach((n, i) => {
      const y = list.length === 1
        ? opts.height / 2
        : pad + (i * (opts.height - 2 * pad)) / (list.length - 1);
      pos.set(n.id, { ...n, x: colX(ci), y, col: ci });
    });
  });

  // one barycenter pass: order each column by mean neighbour y to reduce crossings
  const neighbours = new Map<string, string[]>();
  const addNb = (a: string, b: string) => {
    let arr = neighbours.get(a);
    if (!arr) neighbours.set(a, (arr = []));
    arr.push(b);
  };
  for (const e of graph.edges) { addNb(e.from_id, e.to_id); addNb(e.to_id, e.from_id); }
  cols.forEach((s, ci) => {
    const list = byStage.get(s)!.map((n) => pos.get(n.id)!);
    list.sort((a, b) => bary(a, neighbours, pos) - bary(b, neighbours, pos));
    list.forEach((n, i) => {
      n.y = list.length === 1
        ? opts.height / 2
        : pad + (i * (opts.height - 2 * pad)) / (list.length - 1);
    });
  });

  const colOf = (id: string) => pos.get(id)?.col ?? 0;
  const edges: RoutedEdge[] = graph.edges.map((e) => ({
    ...e,
    isBack: colOf(e.from_id) > colOf(e.to_id),
  }));

  return { nodes: [...pos.values()], edges };
}

function bary(n: PositionedNode, nb: Map<string, string[]>, pos: Map<string, PositionedNode>): number {
  const ns = (nb.get(n.id) ?? []).map((id) => pos.get(id)?.y).filter((y): y is number => y != null);
  return ns.length ? ns.reduce((a, b) => a + b, 0) / ns.length : n.y;
}
