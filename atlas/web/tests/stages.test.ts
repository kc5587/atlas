// atlas/web/tests/stages.test.ts
import { describe, expect, it } from "vitest";
import {
  STAGE_ORDER_STORY, STAGE_ORDER_EXPLORE, STAGE_COLOR, STAGE_LABEL, stageOrder,
} from "../src/lib/stages";

describe("stages module", () => {
  it("story order has 5 stages with cloud last", () => {
    expect(STAGE_ORDER_STORY).toHaveLength(5);
    expect(STAGE_ORDER_STORY[STAGE_ORDER_STORY.length - 1]).toBe("cloud");
    expect(STAGE_ORDER_STORY).not.toContain("networking");
  });

  it("explore order has 9 stages with cloud last", () => {
    expect(STAGE_ORDER_EXPLORE).toHaveLength(9);
    expect(STAGE_ORDER_EXPLORE[STAGE_ORDER_EXPLORE.length - 1]).toBe("cloud");
    expect(STAGE_ORDER_EXPLORE).toContain("eda");
    expect(STAGE_ORDER_EXPLORE).toContain("grid");
  });

  it("every explore stage has a color and label", () => {
    for (const s of STAGE_ORDER_EXPLORE) {
      expect(STAGE_COLOR[s]).toMatch(/^#/);
      expect(STAGE_LABEL[s].length).toBeGreaterThan(0);
    }
  });

  it("stageOrder switches by mode", () => {
    expect(stageOrder("story")).toBe(STAGE_ORDER_STORY);
    expect(stageOrder("explore")).toBe(STAGE_ORDER_EXPLORE);
  });
});
