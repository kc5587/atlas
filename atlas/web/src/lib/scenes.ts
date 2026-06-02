// src/lib/scenes.ts
export interface Scene {
  id: string;
  title: string;
  body: string;
  highlightNodeIds?: string[];   // empty/undefined = whole graph
  highlightPath?: [string, string][];
  focusStage?: string;
  showLeadLag?: boolean;
  showCapex?: boolean;
}

export const SCENES: Scene[] = [
  { id: "whole", title: "The AI value chain", body: "Every layer, from lithography to the cloud." },
  { id: "path", title: "One path", body: "ASML enables TSMC, which fabricates NVIDIA, which powers Microsoft.",
    highlightPath: [["asml", "tsmc"], ["tsmc", "nvidia"], ["nvidia", "msft"]] },
  { id: "bottlenecks", title: "Bottlenecks & geography", body: "A few chokepoints carry the chain: EUV, advanced packaging, Taiwan.",
    focusStage: "foundry" },
  { id: "leadlag", title: "Measured lead/lag", body: "Upstream moves show up downstream days later.", showLeadLag: true },
  { id: "capex", title: "The upstream pull", body: "Hyperscaler capex pulls orders back up the chain.", showCapex: true },
  { id: "forgotten", title: "Forgotten plays", body: "Power, cooling, fiber — the unpriced edges (coming in Layer 3)." },
  { id: "explore", title: "Explore", body: "Roam the chain yourself." },
];
