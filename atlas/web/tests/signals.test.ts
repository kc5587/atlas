import { describe, expect, it } from "vitest";
import { parseSignals } from "../src/lib/signals";

const valid = [{
  id: "H0", title: "Daily lead/lag is sector beta", claim: "x", mechanism: "y",
  horizon: "daily", verdict: "null",
  evidence_chain: [{ stage: "raw", metric: "|corr|", value: 0.14 }],
  stat: { name: "edges_confirmed", value: 0, q_value: 0.17, n: 19 },
  caveats: ["c"], chart: { type: "edge_corr_bars", ref: "h0" }, detail_rows: [],
}];

describe("signals parsing", () => {
  it("parses a valid signal record", () => {
    const s = parseSignals(valid);
    expect(s[0].verdict).toBe("null");
    expect(s[0].evidence_chain[0].value).toBe(0.14);
  });
  it("rejects an invalid verdict", () => {
    const bad = [{ ...valid[0], verdict: "amazing" }];
    expect(() => parseSignals(bad)).toThrow();
  });
});
