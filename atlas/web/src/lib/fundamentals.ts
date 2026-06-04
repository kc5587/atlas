// src/lib/fundamentals.ts
// Pure helpers for surfacing Layer 2 SEC fundamentals in the UI.
import type { Graph, LeadLag, Series, SeriesPoint } from "./types";

// Most recent point that actually has a value (null quarters are skipped so the
// shown date communicates how fresh the figure is). Returns null if none.
export function latestPoint(points: SeriesPoint[] | undefined): SeriesPoint | null {
  if (!points || points.length === 0) return null;
  let best: SeriesPoint | null = null;
  for (const p of points) {
    if (p.value == null) continue;
    if (!best || p.date > best.date) best = p;
  }
  return best;
}

// Abbreviated USD for large filing figures, e.g. "$80.1B" / "-$1.5B" / "$372.0M".
export function formatUSD(value: number | null | undefined): string {
  if (value == null) return "—";
  const sign = value < 0 ? "-" : "";
  const abs = Math.abs(value);
  if (abs >= 1e9) return `${sign}$${(abs / 1e9).toFixed(1)}B`;
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${sign}$${(abs / 1e3).toFixed(1)}K`;
  return `${sign}$${abs.toFixed(0)}`;
}

// A 0..1 ratio rendered as a percentage, e.g. "68.2%".
export function formatPct(ratio: number | null | undefined): string {
  if (ratio == null) return "—";
  return `${(ratio * 100).toFixed(1)}%`;
}

// A node's own capex→price lead/lag (self-paired fund_capex_price row).
export function fundLeadLagFor(rows: LeadLag[], nodeId: string): LeadLag | undefined {
  return rows.find(
    (r) => r.pair_type === "fund_capex_price" && r.left === nodeId && r.right === nodeId,
  );
}

// Node ids whose first ticker has at least one usable (non-null) capex value.
export function nodesWithCapex(graph: Graph, series: Series): Set<string> {
  const ids = new Set<string>();
  const funds = series.fundamentals;
  if (!funds) return ids;
  for (const node of graph.nodes) {
    const ticker = node.tickers[0];
    if (!ticker) continue;
    if (latestPoint(funds[ticker]?.capex)) ids.add(node.id);
  }
  return ids;
}
