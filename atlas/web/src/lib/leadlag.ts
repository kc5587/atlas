// src/lib/leadlag.ts
import type { LeadLag } from "./types";

export function leadLagFor(rows: LeadLag[], from: string, to: string): LeadLag | undefined {
  const matches = rows.filter(
    (r) => (r.left === from && r.right === to) || (r.left === to && r.right === from),
  );
  return matches.find((r) => r.factor_model === "M2_market_sector") ?? matches[0];
}

export interface EdgeStyle { width: number; significant: boolean; pulseDelayMs: number; opacity: number; }

export function edgeStyle(row: LeadLag | undefined, alpha: number): EdgeStyle {
  if (!row) return { width: 1, significant: false, pulseDelayMs: 0, opacity: 0.35 };
  const significant = row.q_value <= alpha && row.stable;
  return {
    width: significant ? 3.5 : 1.25,
    significant,
    pulseDelayMs: Math.max(0, Math.abs(row.lag)) * 120,
    opacity: significant ? 0.95 : 0.4,
  };
}
