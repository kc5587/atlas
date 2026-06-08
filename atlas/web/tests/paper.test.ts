import { describe, expect, it } from "vitest";
import {
  confirmedPairs,
  correlogramPoints,
  dagLayout,
  detailCoefficients,
  effectSize,
  labelForDetailRow,
  negLog10Q,
  tableRows,
  volcanoPoints,
  volcanoXDomain,
  vrpSeriesPoints,
} from "../src/lib/paper";
import type { Signal } from "../src/lib/signals";

const sig = (over: Partial<Signal> & { id: string }): Signal => ({
  id: over.id,
  title: over.title ?? over.id,
  claim: over.claim ?? "",
  mechanism: over.mechanism ?? "",
  horizon: over.horizon ?? "",
  verdict: over.verdict ?? "null",
  evidence_chain: over.evidence_chain ?? [],
  caveats: over.caveats ?? [],
  chart: over.chart ?? { type: "", ref: "" },
  detail_rows: over.detail_rows ?? [],
  stat: over.stat ?? { name: "slope", value: 0, q_value: 1, n: 0 },
});

describe("paper transforms", () => {
  it("effectSize returns the headline statistic value", () => {
    expect(effectSize(sig({
      id: "H1",
      stat: { name: "slope", value: 0.41, q_value: 0.055, n: 11 },
    }))).toBe(0.41);
  });

  it("negLog10Q maps q to significance height; null q -> null", () => {
    expect(negLog10Q(0.1)).toBeCloseTo(1, 6);
    expect(negLog10Q(0.001)).toBeCloseTo(3, 6);
    expect(negLog10Q(null)).toBeNull();
  });

  it("volcanoPoints standardizes effect to a t-statistic and needs slope+q+ci", () => {
    const signals = [
      // slope 0.4 with CI width 0.4 -> SE=(0.6-0.2)/3.92, t = 0.4/SE = 3.92
      sig({ id: "H1", verdict: "confirmed", stat: { name: "slope", value: 0.4, q_value: 0.055, ci: [0.2, 0.6], n: 11 } }),
      // large raw slope but comparable once standardized (would have clipped a slope axis)
      sig({ id: "H8", verdict: "confirmed", stat: { name: "slope", value: 2.58, q_value: 0.04, ci: [1.68, 4.07], n: 6 } }),
      sig({ id: "H0", stat: { name: "edges_confirmed", value: 1, q_value: 0.04, ci: [0, 2], n: 1 } }),      // excluded: not a slope
      sig({ id: "H6", verdict: "confirmed", stat: { name: "mean_vrp", value: 0.009, q_value: null, n: 4120 } }), // excluded: null q
      sig({ id: "HX", stat: { name: "slope", value: 0.2, q_value: 0.2, n: 5 } }),                            // excluded: no CI -> no SE
    ];
    const pts = volcanoPoints(signals);
    expect(pts.map((p) => p.id)).toEqual(["H1", "H8"]);
    expect(pts[0].t).toBeCloseTo(3.92, 2);
    expect(pts[1].t).toBeGreaterThan(3); // H8 visible & comparable, not clipped off a slope axis
    expect(pts[0]).toMatchObject({ id: "H1", y: expect.any(Number), verdict: "confirmed" });
  });

  it("volcanoXDomain pads the t-range and always includes zero", () => {
    const [lo, hi] = volcanoXDomain([
      { id: "a", slope: 0, t: 0.5, y: 1, q: 0.1, verdict: "null" },
      { id: "b", slope: 0, t: 4.2, y: 2, q: 0.01, verdict: "confirmed" },
    ]);
    expect(lo).toBeLessThanOrEqual(0);
    expect(hi).toBeGreaterThanOrEqual(4.2);
  });
});

describe("paper table + dag", () => {
  it("tableRows projects id/claim/slope/q/n/verdict", () => {
    const rows = tableRows([
      sig({
        id: "H1",
        claim: "Capex -> revenue",
        verdict: "confirmed",
        stat: { name: "slope", value: 0.41, q_value: 0.055, n: 11 },
      }),
    ]);
    expect(rows[0]).toEqual({
      id: "H1",
      claim: "Capex -> revenue",
      slope: 0.41,
      q: 0.055,
      n: 11,
      verdict: "confirmed",
    });
  });

  it("confirmedPairs extracts H1/H11 edges that clear FDR", () => {
    const s = sig({
      id: "H1",
      verdict: "confirmed",
      detail_rows: [
        { left: "asml", right: "tsmc", q_value: 0.04 },
        { left: "x", right: "y", q_value: 0.5 },
      ],
    });
    expect(confirmedPairs([s])).toEqual(new Set(["asml|tsmc"]));
  });

  it("dagLayout places nodes by stage column and finite edge coordinates", () => {
    const graph = {
      nodes: [
        { id: "asml", name: "ASML", stage: "equipment" },
        { id: "tsmc", name: "TSMC", stage: "foundry" },
      ],
      edges: [{ from_id: "asml", to_id: "tsmc" }],
    };
    const lay = dagLayout(graph, ["equipment", "foundry"], new Set(["asml|tsmc"]), 800, 300);
    expect(lay.nodes.find((n) => n.id === "asml")!.x).toBeLessThan(
      lay.nodes.find((n) => n.id === "tsmc")!.x,
    );
    expect(lay.edges[0].confirmed).toBe(true);
    for (const v of [lay.edges[0].x1, lay.edges[0].y1, lay.edges[0].x2, lay.edges[0].y2]) {
      expect(Number.isFinite(v)).toBe(true);
    }
  });
});

describe("detail coefficients", () => {
  it("labels rows from their identity fields", () => {
    expect(labelForDetailRow({ left: "asml", right: "tsmc" })).toBe("asml → tsmc");
    expect(labelForDetailRow({ target: "SPY", horizon: 21 })).toBe("SPY · 21d");
    expect(labelForDetailRow({ indicator: "CAPUTLG3344S" })).toBe("CAPUTLG3344S");
    expect(labelForDetailRow({ pair: "^VIX~SPY" })).toBe("^VIX~SPY");
    expect(labelForDetailRow({ foo: 1 })).toBe("row 1");
  });

  it("extracts effect/CI/passes from slope rows", () => {
    const s = sig({ id: "H1", detail_rows: [
      { left: "asml", right: "tsmc", slope: 0.41, slope_lo: 0.12, slope_hi: 0.58, q_value: 0.04 },
      { left: "x", right: "y", slope: -0.02, slope_lo: -0.1, slope_hi: 0.06, q_value: 0.7 },
    ] });
    const cs = detailCoefficients(s);
    expect(cs[0]).toEqual({ label: "asml → tsmc", effect: 0.41, lo: 0.12, hi: 0.58, passes: true });
    expect(cs[1].passes).toBe(false);
  });

  it("falls back to mean_vrp / vrp CI for H6-style rows", () => {
    const s = sig({ id: "H6", detail_rows: [{ pair: "^VIX~SPY", mean_vrp: 0.009, vrp_lo: 0.003, vrp_hi: 0.014 }] });
    expect(detailCoefficients(s)[0]).toMatchObject({ label: "^VIX~SPY", effect: 0.009, lo: 0.003, hi: 0.014 });
  });
});

describe("correlogramPoints", () => {
  it("maps rows and finds the peak lag", () => {
    const raw = {
      pair: { left: "A", right: "B", left_ticker: "AA", right_ticker: "BB" },
      max_lag: 2,
      points: [
        { lag: -1, corr: 0.1, ci_lo: -0.2, ci_hi: 0.3, is_peak: false, passes_fdr: false },
        { lag: 0, corr: 0.5, ci_lo: 0.2, ci_hi: 0.7, is_peak: true, passes_fdr: true },
        { lag: 1, corr: -0.2, ci_lo: -0.4, ci_hi: 0.0, is_peak: false, passes_fdr: false },
      ],
    };
    const out = correlogramPoints(raw);
    expect(out!.points).toHaveLength(3);
    expect(out!.peakLag).toBe(0);
    expect(out!.pairLabel).toBe("AA → BB");
  });

  it("returns null on empty points", () => {
    expect(correlogramPoints({ pair: {}, max_lag: 2, points: [] })).toBeNull();
  });
});

describe("vrpSeriesPoints", () => {
  it("parses dates and keeps the three series", () => {
    const raw = {
      pair: { implied: "^VIX", underlying: "SPY" },
      horizon: 21,
      points: [{ date: "2021-01-04", implied_var: 0.04, realized_var: 0.03, vrp: 0.01 }],
    };
    const out = vrpSeriesPoints(raw);
    expect(out!.points[0].impliedVar).toBeCloseTo(0.04);
    expect(out!.label).toContain("^VIX");
  });
});
