// atlas/web/tests/data.test.ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { loadOptionalJSON, parseGraph, parseLeadLag } from "../src/lib/data";

afterEach(() => {
  vi.unstubAllGlobals();
});

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

  it("parses the new explore-only stages", () => {
    const g = parseGraph({
      nodes: [{ id: "arista", name: "Arista", tickers: ["ANET"], stage: "networking", region: "US", criticality: 2 }],
      edges: [],
    });
    expect(g.nodes[0].stage).toBe("networking");
  });

  it("parses legacy lead/lag rows with null hardening fields", () => {
    const ll = parseLeadLag([
      { pair_type: "macro", left: "nvidia", right: "DFF", lag: 2,
        corr: 0.2, p_value: 0.3, q_value: 0.4, n_eff: 80, stable: false,
        factor_model: null, p_selection: null, oos_sign_rate: null,
        confirmed: null, survives_sector_control: null,
        contradicts_thesis: null, inverse_lead: null },
    ]);
    expect(ll[0].factor_model).toBeNull();
  });

  it("loads optional JSON, tolerates 404, and ignores SPA-fallback HTML", async () => {
    const make = (opts: { ok: boolean; status: number; contentType: string; body: () => unknown }) => ({
      ok: opts.ok,
      status: opts.status,
      headers: { get: (h: string) => (h.toLowerCase() === "content-type" ? opts.contentType : null) },
      json: async () => opts.body(),
    });
    const fetchMock = vi.fn(async (path: string) => {
      if (path.includes("present")) {
        return make({ ok: true, status: 200, contentType: "application/json", body: () => ({ points: [1] }) });
      }
      if (path.includes("fallback")) {
        // Static host serves index.html (200) for a missing file: parsing it would throw.
        return make({ ok: true, status: 200, contentType: "text/html", body: () => { throw new SyntaxError("Unexpected token '<'"); } });
      }
      return make({ ok: false, status: 404, contentType: "text/plain", body: () => null });
    });
    vi.stubGlobal("fetch", fetchMock);

    await expect(loadOptionalJSON("data/present.json")).resolves.toEqual({ points: [1] });
    await expect(loadOptionalJSON("data/missing.json")).resolves.toBeNull();
    await expect(loadOptionalJSON("data/fallback.json")).resolves.toBeNull();
  });
});
