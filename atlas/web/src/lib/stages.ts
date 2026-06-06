// src/lib/stages.ts
import type { Stage } from "./types";

// Story mode: the 5 canonical columns. Cloud is the demand terminus.
export const STAGE_ORDER_STORY: Stage[] = [
  "equipment", "foundry", "chips", "power", "cloud",
];

// Explore mode: the full chain, also terminating at cloud.
export const STAGE_ORDER_EXPLORE: Stage[] = [
  "eda", "equipment", "foundry", "packaging", "chips",
  "networking", "grid", "power", "cloud",
];

export const STAGE_COLOR: Record<Stage, string> = {
  eda: "#4cc2c4",
  equipment: "#6c8ebf",
  foundry: "#9673a6",
  packaging: "#d98cc4",
  chips: "#82b366",
  networking: "#5b6ee1",
  grid: "#c9b037",
  power: "#b5563a",
  cloud: "#d79b00",
};

export const STAGE_LABEL: Record<Stage, string> = {
  eda: "EDA",
  equipment: "EQUIPMENT",
  foundry: "FOUNDRY",
  packaging: "PACKAGING",
  chips: "CHIPS",
  networking: "NETWORKING",
  grid: "GRID",
  power: "POWER",
  cloud: "CLOUD",
};

export function stageOrder(mode: "story" | "explore"): Stage[] {
  return mode === "explore" ? STAGE_ORDER_EXPLORE : STAGE_ORDER_STORY;
}
