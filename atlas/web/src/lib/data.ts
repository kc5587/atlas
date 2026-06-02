// src/lib/data.ts
import { GraphZ, LeadLagZ, MetaZ, SeriesZ } from "./types";
import type { Graph, LeadLag, Meta, Series } from "./types";

export function parseGraph(raw: unknown): Graph { return GraphZ.parse(raw); }
export function parseLeadLag(raw: unknown): LeadLag[] { return LeadLagZ.array().parse(raw); }
export function parseSeries(raw: unknown): Series { return SeriesZ.parse(raw); }
export function parseMeta(raw: unknown): Meta { return MetaZ.parse(raw); }

async function getJSON(path: string): Promise<unknown> {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`failed to load ${path}: ${r.status}`);
  return r.json();
}

export async function loadAll(base = "data") {
  const [graph, leadlag, series, meta] = await Promise.all([
    getJSON(`${base}/graph.json`).then(parseGraph),
    getJSON(`${base}/leadlag.json`).then(parseLeadLag),
    getJSON(`${base}/series.json`).then(parseSeries),
    getJSON(`${base}/meta.json`).then(parseMeta),
  ]);
  return { graph, leadlag, series, meta };
}
