import { z } from "zod";

export const VerdictZ = z.enum(["confirmed", "suggestive", "null", "contradicts"]);
export const EvidenceStepZ = z.object({
  stage: z.string(), metric: z.string(), value: z.number(),
});
export const SignalZ = z.object({
  id: z.string(), title: z.string(), claim: z.string(), mechanism: z.string(),
  horizon: z.string(), verdict: VerdictZ,
  evidence_chain: z.array(EvidenceStepZ),
  stat: z.object({
    name: z.string(), value: z.number(),
    q_value: z.number().nullable().optional(),
    ci: z.tuple([z.number(), z.number()]).nullable().optional(),
    n: z.number(),
  }),
  caveats: z.array(z.string()),
  chart: z.object({ type: z.string(), ref: z.string() }),
  detail_rows: z.array(z.record(z.any())),
});
export type Signal = z.infer<typeof SignalZ>;

export function parseSignals(raw: unknown): Signal[] {
  return SignalZ.array().parse(raw);
}

export async function loadSignals(base = "data"): Promise<Signal[]> {
  const r = await fetch(`${base}/signals.json`);
  if (!r.ok) throw new Error(`failed to load signals: ${r.status}`);
  return parseSignals(await r.json());
}
