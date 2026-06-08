import type { Signal } from "./signals";

export const FDR_ALPHA = 0.1;

export interface VolcanoPoint {
  id: string;
  slope: number;
  /** Standardized effect: t = slope / SE, comparable across heterogeneous hypotheses. */
  t: number;
  y: number;
  q: number;
  verdict: Signal["verdict"];
}

/** Standard error from a 95% CI: SE = (hi - lo) / (2 * 1.96). */
export function standardError(ci: readonly [number, number] | null | undefined): number | null {
  if (!ci) return null;
  const se = (ci[1] - ci[0]) / (2 * 1.96);
  return Number.isFinite(se) && se > 0 ? se : null;
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

/**
 * Slope hypotheses with a finite q AND a CI (needed to standardize). Raw slopes are not
 * comparable across hypotheses (different units/scales), so the x-axis is the t-statistic.
 */
export function volcanoPoints(signals: Signal[]): VolcanoPoint[] {
  return signals.flatMap((signal) => {
    if (!signal.stat.name.endsWith("slope")) return [];
    const y = negLog10Q(signal.stat.q_value);
    const se = standardError(signal.stat.ci);
    if (y == null || signal.stat.q_value == null || se == null) return [];
    return [{
      id: signal.id,
      slope: effectSize(signal),
      t: effectSize(signal) / se,
      y,
      q: signal.stat.q_value,
      verdict: signal.verdict,
    }];
  });
}

/** Padded [min, max] t-domain for the volcano x-axis; always spans zero. */
export function volcanoXDomain(points: VolcanoPoint[]): [number, number] {
  const ts = points.map((p) => p.t);
  const lo = Math.min(0, ...ts);
  const hi = Math.max(0, ...ts);
  const pad = (hi - lo) * 0.08 || 0.5;
  return [lo - pad, hi + pad];
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

export interface DetailCoefficient {
  label: string;
  effect: number;
  lo: number | null;
  hi: number | null;
  passes: boolean; // q <= FDR_ALPHA
}

const numOr = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);

export function labelForDetailRow(row: Record<string, unknown>): string {
  if (typeof row.left === "string" && typeof row.right === "string") return `${row.left} → ${row.right}`;
  if (typeof row.target === "string" && row.horizon != null) return `${row.target} · ${row.horizon}d`;
  if (typeof row.indicator === "string") return row.indicator;
  if (typeof row.name === "string") return row.name;
  if (typeof row.pair === "string") return row.pair;
  return "row 1";
}

/** Common {label, effect, lo, hi, passes} per detail row, across heterogeneous schemas. */
export function detailCoefficients(sig: Signal): DetailCoefficient[] {
  return sig.detail_rows.map((raw, i) => {
    const row = raw as Record<string, unknown>;
    const effect = numOr(row.slope) ?? numOr(row.mean_vrp) ?? numOr(row.corr) ?? 0;
    const lo = numOr(row.slope_lo) ?? numOr(row.vrp_lo);
    const hi = numOr(row.slope_hi) ?? numOr(row.vrp_hi);
    const q = numOr(row.q_value);
    const label = labelForDetailRow(row) === "row 1" ? `row ${i + 1}` : labelForDetailRow(row);
    return { label, effect, lo, hi, passes: q != null && q <= FDR_ALPHA };
  });
}

export interface CorrelogramPoint {
  lag: number;
  corr: number;
  ciLo: number;
  ciHi: number;
  isPeak: boolean;
  passesFdr: boolean;
}

export interface Correlogram {
  pairLabel: string;
  maxLag: number;
  peakLag: number;
  points: CorrelogramPoint[];
}

export function correlogramPoints(raw: unknown): Correlogram | null {
  const r = raw as {
    pair?: { left?: string; right?: string; left_ticker?: string; right_ticker?: string };
    max_lag?: number;
    points?: Array<Record<string, unknown>>;
  } | null;
  if (!r?.points?.length) return null;
  const points: CorrelogramPoint[] = r.points.map((p) => ({
    lag: Number(p.lag),
    corr: Number(p.corr),
    ciLo: Number(p.ci_lo),
    ciHi: Number(p.ci_hi),
    isPeak: Boolean(p.is_peak),
    passesFdr: Boolean(p.passes_fdr),
  }));
  const peak = points.find((p) => p.isPeak) ?? points.reduce((a, b) => (
    Math.abs(b.corr) > Math.abs(a.corr) ? b : a
  ));
  const lt = r.pair?.left_ticker ?? r.pair?.left ?? "";
  const rt = r.pair?.right_ticker ?? r.pair?.right ?? "";
  return {
    pairLabel: `${lt} → ${rt}`,
    maxLag: Number(r.max_lag ?? 0),
    peakLag: peak.lag,
    points,
  };
}

export interface VrpPoint {
  date: Date;
  impliedVar: number;
  realizedVar: number;
  vrp: number;
}

export interface VrpSeries {
  label: string;
  points: VrpPoint[];
}

export function vrpSeriesPoints(raw: unknown): VrpSeries | null {
  const r = raw as {
    pair?: { implied?: string; underlying?: string };
    points?: Array<Record<string, unknown>>;
  } | null;
  if (!r?.points?.length) return null;
  const points: VrpPoint[] = r.points.map((p) => ({
    date: new Date(String(p.date)),
    impliedVar: Number(p.implied_var),
    realizedVar: Number(p.realized_var),
    vrp: Number(p.vrp),
  }));
  return { label: `${r.pair?.implied ?? ""} vs ${r.pair?.underlying ?? ""}`, points };
}

export interface EventStudyPoint {
  horizon: number;
  effect: number;
  lo: number | null;
  hi: number | null;
  passes: boolean;
}

export function eventStudyPoints(signal: Signal): EventStudyPoint[] {
  return detailCoefficients(signal)
    .map((coef, index) => {
      const row = signal.detail_rows[index] as Record<string, unknown>;
      const horizon = typeof row.horizon === "number"
        ? row.horizon
        : Number.parseFloat(coef.label);
      return {
        horizon,
        effect: coef.effect,
        lo: coef.lo,
        hi: coef.hi,
        passes: coef.passes,
      };
    })
    .filter((point) => Number.isFinite(point.horizon))
    .sort((a, b) => a.horizon - b.horizon);
}
