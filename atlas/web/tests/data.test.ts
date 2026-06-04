// atlas/web/tests/data.test.ts
import { describe, expect, it } from "vitest";
import { parseGraph, parseLeadLag } from "../src/lib/data";

describe("data parsing", () => {
  it("parses a valid graph", () => {
    const g = parseGraph({
      nodes: [{ id: "nvidia", name: "NVIDIA", tickers: ["NVDA"], stage: "chips", region: "US", criticality: 3 }],
      edges: [{ from_id: "tsmc", to_id: "nvidia", relationship: "supplies", note: "", evidence: "", as_of: "2024-01-01" }],
    });
    expect(g.nodes[0].stage).toBe("chips");
    expect(g.edges[0].from_id).toBe("tsmc");
  });

  it("rejects an invalid stage", () => {
    expect(() => parseGraph({
      nodes: [{ id: "x", name: "X", tickers: [], stage: "banana", region: "US", criticality: 0 }],
      edges: [],
    })).toThrow();
  });

  it("parses lead/lag rows", () => {
    const ll = parseLeadLag([
      { pair_type: "edge", left: "a", right: "b", lag: 2, corr: 0.4, p_value: 0.01, q_value: 0.05, n_eff: 300, stable: true },
    ]);
    expect(ll[0].stable).toBe(true);
  });

  it("parses hardened lead/lag rows with new fields", () => {
    const ll = parseLeadLag([
      { pair_type: "edge", left: "nvidia", right: "microsoft", lag: 2,
        corr: 0.4, p_value: 0.01, q_value: 0.05, n_eff: 1200, stable: true,
        factor_model: "M2_market_sector", corr_raw: 0.6, corr_resid: 0.4,
        p_selection: 0.01, oos_sign_rate: 0.8, confirmed: true,
        survives_sector_control: true, contradicts_thesis: false },
    ]);
    expect(ll[0].factor_model).toBe("M2_market_sector");
    expect(ll[0].confirmed).toBe(true);
  });
});
