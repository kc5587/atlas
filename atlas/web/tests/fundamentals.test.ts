// atlas/web/tests/fundamentals.test.ts
import { describe, expect, it } from "vitest";
import { formatPct, formatUSD, fundLeadLagFor, latestPoint, nodesWithCapex } from "../src/lib/fundamentals";
import type { Graph, LeadLag, Series } from "../src/lib/types";

describe("latestPoint", () => {
  it("returns the most recent non-null point by date", () => {
    const p = latestPoint([
      { date: "2023-01-01", value: 10 },
      { date: "2024-06-01", value: 30 },
      { date: "2023-06-01", value: 20 },
    ]);
    expect(p).toEqual({ date: "2024-06-01", value: 30 });
  });

  it("skips trailing null values and returns the latest dated value", () => {
    const p = latestPoint([
      { date: "2023-01-01", value: 10 },
      { date: "2024-06-01", value: null },
    ]);
    expect(p).toEqual({ date: "2023-01-01", value: 10 });
  });

  it("returns null when there is no data or all values are null", () => {
    expect(latestPoint(undefined)).toBeNull();
    expect(latestPoint([])).toBeNull();
    expect(latestPoint([{ date: "2024-01-01", value: null }])).toBeNull();
  });
});

describe("fundLeadLagFor", () => {
  const rows: LeadLag[] = [
    { pair_type: "edge", left: "asml", right: "tsmc", lag: 5, corr: 0.6, p_value: 0.001, q_value: 0.02, n_eff: 300, stable: true },
    { pair_type: "fund_capex_price", left: "nvidia", right: "nvidia", lag: -3, corr: -0.18, p_value: 0.48, q_value: 0.48, n_eff: 23, stable: false },
    { pair_type: "macro", left: "nvidia", right: "IPG3344S", lag: 11, corr: 0.2, p_value: 0.01, q_value: 0.02, n_eff: 184, stable: false },
  ];

  it("returns the self-paired capex→price row for a node", () => {
    expect(fundLeadLagFor(rows, "nvidia")?.lag).toBe(-3);
  });

  it("ignores edge and macro rows for the same node", () => {
    const row = fundLeadLagFor(rows, "nvidia");
    expect(row?.pair_type).toBe("fund_capex_price");
  });

  it("returns undefined when the node has no capex→price pair", () => {
    expect(fundLeadLagFor(rows, "asml")).toBeUndefined();
  });
});

describe("formatUSD", () => {
  it("abbreviates billions and millions", () => {
    expect(formatUSD(80146000000)).toBe("$80.1B");
    expect(formatUSD(372000000)).toBe("$372.0M");
  });
  it("handles negatives and null", () => {
    expect(formatUSD(-1500000000)).toBe("-$1.5B");
    expect(formatUSD(null)).toBe("—");
  });
});

describe("formatPct", () => {
  it("renders a 0..1 ratio as a percentage", () => {
    expect(formatPct(0.6822215422276622)).toBe("68.2%");
  });
  it("returns an em dash for null", () => {
    expect(formatPct(null)).toBe("—");
  });
});

describe("nodesWithCapex", () => {
  const graph: Graph = {
    nodes: [
      { id: "nvidia", name: "NVIDIA", tickers: ["NVDA"], stage: "chips", region: "US", cik: "0001045810", criticality: 3 },
      { id: "asml", name: "ASML", tickers: ["ASML"], stage: "equipment", region: "NL", cik: null, criticality: 3 },
    ],
    edges: [],
  };
  const series: Series = {
    prices: {},
    fundamentals: {
      NVDA: { capex: [{ date: "2024-01-01", value: 5 }], revenue: [], gross_margin: [] },
      // ASML present but capex all null → excluded
      ASML: { capex: [{ date: "2024-01-01", value: null }], revenue: [], gross_margin: [] },
    },
  };

  it("returns node ids whose ticker has non-null capex data", () => {
    const ids = nodesWithCapex(graph, series);
    expect(ids.has("nvidia")).toBe(true);
  });

  it("excludes nodes without usable capex data", () => {
    const ids = nodesWithCapex(graph, series);
    expect(ids.has("asml")).toBe(false);
  });

  it("returns an empty set when no fundamentals are present", () => {
    expect(nodesWithCapex(graph, { prices: {} }).size).toBe(0);
  });
});
