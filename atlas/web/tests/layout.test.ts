// atlas/web/tests/layout.test.ts
import { describe, expect, it } from "vitest";
import { computeLayout } from "../src/lib/layout";
import type { Graph } from "../src/lib/types";

const g: Graph = {
  nodes: [
    { id: "asml", name: "ASML", tickers: ["ASML"], stage: "equipment", region: "NL", criticality: 1 },
    { id: "tsmc", name: "TSMC", tickers: ["TSM"], stage: "foundry", region: "TW", criticality: 2 },
    { id: "nvidia", name: "NVIDIA", tickers: ["NVDA"], stage: "chips", region: "US", criticality: 3 },
    { id: "msft", name: "Microsoft", tickers: ["MSFT"], stage: "cloud", region: "US", criticality: 2 },
    { id: "vistra", name: "Vistra", tickers: ["VST"], stage: "power", region: "US", criticality: 1 },
  ],
  edges: [
    { from_id: "asml", to_id: "tsmc", relationship: "supplies", note: "", evidence: "", as_of: "" },
    { from_id: "tsmc", to_id: "nvidia", relationship: "supplies", note: "", evidence: "", as_of: "" },
    { from_id: "nvidia", to_id: "msft", relationship: "supplies", note: "", evidence: "", as_of: "" },
    { from_id: "msft", to_id: "vistra", relationship: "supplies", note: "", evidence: "", as_of: "" },
    // back-edge: cloud builds its own silicon -> chips
    { from_id: "msft", to_id: "nvidia", relationship: "supplies", note: "in-house", evidence: "", as_of: "" },
  ],
};

describe("computeLayout", () => {
  it("assigns x by stage order with cloud as the terminus", () => {
    const { nodes } = computeLayout(g, { width: 800, height: 400 });
    const by = Object.fromEntries(nodes.map((n) => [n.id, n.x]));
    expect(by["asml"]).toBeLessThan(by["tsmc"]);
    expect(by["tsmc"]).toBeLessThan(by["nvidia"]);
    expect(by["nvidia"]).toBeLessThan(by["vistra"]); // chips < power
    expect(by["vistra"]).toBeLessThan(by["msft"]);   // power < cloud (terminus)
  });

  it("gives every node a finite position", () => {
    const { nodes } = computeLayout(g, { width: 800, height: 400 });
    for (const n of nodes) {
      expect(Number.isFinite(n.x)).toBe(true);
      expect(Number.isFinite(n.y)).toBe(true);
    }
  });

  it("flags back-edges (downstream stage -> upstream stage)", () => {
    const { edges } = computeLayout(g, { width: 800, height: 400 });
    const back = edges.find((e) => e.from_id === "msft" && e.to_id === "nvidia");
    expect(back?.isBack).toBe(true);
    const fwd = edges.find((e) => e.from_id === "asml" && e.to_id === "tsmc");
    expect(fwd?.isBack).toBe(false);
  });

  it("hides new-stage nodes in story mode and shows them in explore", () => {
    const g2: Graph = {
      nodes: [
        ...g.nodes,
        { id: "arista", name: "Arista", tickers: ["ANET"], stage: "networking", region: "US", criticality: 1 },
      ],
      edges: [
        ...g.edges,
        { from_id: "arista", to_id: "msft", relationship: "supplies", note: "", evidence: "", as_of: "" },
      ],
    };
    const story = computeLayout(g2, { width: 800, height: 400, mode: "story" });
    expect(story.nodes.find((n) => n.id === "arista")).toBeUndefined();
    // edge touching a hidden node is dropped (no dangling reference)
    expect(story.edges.find((e) => e.from_id === "arista")).toBeUndefined();

    const explore = computeLayout(g2, { width: 800, height: 400, mode: "explore" });
    expect(explore.nodes.find((n) => n.id === "arista")).toBeDefined();
    expect(explore.edges.find((e) => e.from_id === "arista")).toBeDefined();
  });
});
