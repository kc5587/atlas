import { describe, expect, it } from "vitest";
import {
  confirmedPairs,
  dagLayout,
  effectSize,
  negLog10Q,
  tableRows,
  volcanoPoints,
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

  it("volcanoPoints includes only slope hypotheses with a finite q", () => {
    const signals = [
      sig({ id: "H1", verdict: "confirmed", stat: { name: "slope", value: 0.41, q_value: 0.055, n: 11 } }),
      sig({ id: "H0", stat: { name: "edges_confirmed", value: 1, q_value: 0.04, n: 1 } }),
      sig({ id: "H6", verdict: "confirmed", stat: { name: "mean_vrp", value: 0.009, q_value: null, n: 4120 } }),
    ];
    const pts = volcanoPoints(signals);
    expect(pts.map((p) => p.id)).toEqual(["H1"]);
    expect(pts[0]).toMatchObject({
      id: "H1",
      slope: 0.41,
      y: expect.any(Number),
      verdict: "confirmed",
    });
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
