// atlas/web/tests/leadlag.test.ts
import { describe, expect, it } from "vitest";
import { edgeStyle, leadLagFor } from "../src/lib/leadlag";
import type { LeadLag } from "../src/lib/types";

const rows: LeadLag[] = [
  { pair_type: "edge", left: "asml", right: "tsmc", lag: 5, corr: 0.6, p_value: 0.001, q_value: 0.02, n_eff: 300, stable: true },
  { pair_type: "edge", left: "tsmc", right: "nvidia", lag: 3, corr: 0.2, p_value: 0.3, q_value: 0.4, n_eff: 300, stable: false },
];

describe("leadlag styling", () => {
  it("finds the row for an edge", () => {
    expect(leadLagFor(rows, "asml", "tsmc")?.lag).toBe(5);
    expect(leadLagFor(rows, "x", "y")).toBeUndefined();
  });
  it("bolds FDR-significant + stable edges", () => {
    const sig = edgeStyle(rows[0], 0.1);
    const ns = edgeStyle(rows[1], 0.1);
    expect(sig.width).toBeGreaterThan(ns.width);
    expect(sig.significant).toBe(true);
    expect(ns.significant).toBe(false);
  });
  it("derives pulse delay from |lag|", () => {
    expect(edgeStyle(rows[0], 0.1).pulseDelayMs).toBeGreaterThan(0);
  });
});
