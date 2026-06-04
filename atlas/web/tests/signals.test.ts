import { describe, expect, it } from "vitest";
import { render } from "svelte/server";
import SignalCard from "../src/components/SignalCard.svelte";
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
  it("renders the capex price legend and edge rows", () => {
    const [signal] = parseSignals([{
      ...valid[0],
      id: "H5",
      chart: { type: "capex_price", ref: "h5" },
      detail_rows: [{
        left: "broadcom", right: "google", horizon: 63, slope: 0.6,
        slope_lo: 0.2, slope_hi: 1.0, n_obs: 25,
      }],
    }]);
    const { body } = render(SignalCard, { props: { signal } });
    expect(body).toContain("not yet priced in");
    expect(body).toContain("broadcom");
    expect(body).toContain("63d");
  });
});
