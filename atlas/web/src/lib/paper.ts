import type { Signal } from "./signals";

export const FDR_ALPHA = 0.1;

export interface VolcanoPoint {
  id: string;
  slope: number;
  y: number;
  q: number;
  verdict: Signal["verdict"];
}

export interface TableRow {
  id: string;
  claim: string;
  slope: number;
  q: number | null;
  n: number;
  verdict: Signal["verdict"];
}

export interface DagInputNode {
  id: string;
  name: string;
  stage: string;
}

export interface DagInputEdge {
  from_id: string;
  to_id: string;
}

export interface DagNode extends DagInputNode {
  x: number;
  y: number;
}

export interface DagEdge {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  confirmed: boolean;
}

export interface DagLayout {
  nodes: DagNode[];
  edges: DagEdge[];
}

type DetailRow = Record<string, unknown>;

/** Headline effect size for a hypothesis. */
export function effectSize(sig: Signal): number {
  return sig.stat.value;
}

/** -log10(q); null when q is missing, non-finite, or non-positive. */
export function negLog10Q(q: number | null | undefined): number | null {
  if (q == null || !Number.isFinite(q) || q <= 0) return null;
  return -Math.log10(q);
}

/** Slope hypotheses with a finite selection-aware q. */
export function volcanoPoints(signals: Signal[]): VolcanoPoint[] {
  return signals.flatMap((signal) => {
    if (!signal.stat.name.endsWith("slope")) return [];
    const y = negLog10Q(signal.stat.q_value);
    if (y == null || signal.stat.q_value == null) return [];
    return [{
      id: signal.id,
      slope: effectSize(signal),
      y,
      q: signal.stat.q_value,
      verdict: signal.verdict,
    }];
  });
}

export function tableRows(signals: Signal[]): TableRow[] {
  return signals.map((signal) => ({
    id: signal.id,
    claim: signal.claim,
    slope: effectSize(signal),
    q: signal.stat.q_value ?? null,
    n: signal.stat.n,
    verdict: signal.verdict,
  }));
}

/** "from|to" keys for H1/H11 detail edges with q <= FDR_ALPHA. */
export function confirmedPairs(signals: Signal[]): Set<string> {
  return new Set(
    signals
      .filter((signal) => signal.id === "H1" || signal.id === "H11")
      .flatMap((signal) => signal.detail_rows)
      .flatMap((row: DetailRow) => {
        const left = row.left;
        const right = row.right;
        const q = row.q_value;
        if (typeof left !== "string" || typeof right !== "string") return [];
        if (typeof q !== "number" || q > FDR_ALPHA) return [];
        return [`${left}|${right}`];
      }),
  );
}

export function dagLayout(
  graph: { nodes: DagInputNode[]; edges: DagInputEdge[] },
  stageOrder: string[],
  confirmed: Set<string>,
  width: number,
  height: number,
): DagLayout {
  const mTop = 34;
  const mBot = 26;
  const mX = 24;
  const colW = (width - mX * 2) / Math.max(stageOrder.length, 1);
  const xByStage = (stage: string) => {
    const idx = Math.max(stageOrder.indexOf(stage), 0);
    return mX + colW * (idx + 0.5);
  };

  const nodes = stageOrder.flatMap((stage) => {
    const stageNodes = graph.nodes.filter((node) => node.stage === stage);
    const gap = (height - mTop - mBot) / (stageNodes.length + 1);
    return stageNodes.map((node, index) => ({
      ...node,
      x: xByStage(stage),
      y: mTop + gap * (index + 1),
    }));
  });
  const byId = new Map(nodes.map((node) => [node.id, node]));

  const edges = graph.edges.flatMap((edge) => {
    const from = byId.get(edge.from_id);
    const to = byId.get(edge.to_id);
    if (!from || !to) return [];
    return [{
      x1: from.x,
      y1: from.y,
      x2: to.x,
      y2: to.y,
      confirmed: confirmed.has(`${edge.from_id}|${edge.to_id}`),
    }];
  });

  return { nodes, edges };
}
