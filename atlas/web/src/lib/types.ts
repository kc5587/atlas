// src/lib/types.ts
import { z } from "zod";

export const StageZ = z.enum([
  "eda", "equipment", "foundry", "packaging",
  "chips", "networking", "grid", "power", "cloud",
]);
export const NodeZ = z.object({
  id: z.string(), name: z.string(), tickers: z.array(z.string()),
  stage: StageZ, region: z.string(), cik: z.string().nullable().optional(),
  criticality: z.number(),
});
export const EdgeZ = z.object({
  from_id: z.string(), to_id: z.string(), relationship: z.string(),
  note: z.string(), evidence: z.string(), as_of: z.string(),
});
export const GraphZ = z.object({ nodes: z.array(NodeZ), edges: z.array(EdgeZ) });
export const LeadLagZ = z.object({
  pair_type: z.string(), left: z.string(), right: z.string(), lag: z.number(),
  corr: z.number(), p_value: z.number(), q_value: z.number(),
  n_eff: z.number(), stable: z.boolean(),
  // Priority 1 hardening (optional; present on hardened edge rows):
  factor_model: z.string().nullable().optional(),
  corr_raw: z.number().nullable().optional(),
  corr_resid: z.number().nullable().optional(),
  p_selection: z.number().nullable().optional(),
  oos_sign_rate: z.number().nullable().optional(),
  oos_corr_median: z.number().nullable().optional(),
  confirmed: z.boolean().nullable().optional(),
  survives_sector_control: z.boolean().nullable().optional(),
  contradicts_thesis: z.boolean().nullable().optional(),
  inverse_lead: z.boolean().nullable().optional(),
});
export const SeriesPointZ = z.object({ date: z.string(), value: z.number().nullable() });
export const SeriesZ = z.object({
  prices: z.record(z.array(SeriesPointZ)),
  fundamentals: z.record(z.object({
    capex: z.array(SeriesPointZ), revenue: z.array(SeriesPointZ),
    gross_margin: z.array(SeriesPointZ),
  })).optional(),
});
export const MetaZ = z.object({
  generated_at: z.string(), schema_version: z.string(),
  tickers: z.array(z.string()), stages: z.array(z.string()),
});

export type SeriesPoint = z.infer<typeof SeriesPointZ>;
export type Stage = z.infer<typeof StageZ>;
export type Node = z.infer<typeof NodeZ>;
export type Edge = z.infer<typeof EdgeZ>;
export type Graph = z.infer<typeof GraphZ>;
export type LeadLag = z.infer<typeof LeadLagZ>;
export type Series = z.infer<typeof SeriesZ>;
export type Meta = z.infer<typeof MetaZ>;
