// src/stores.ts
import { writable } from "svelte/store";
import type { Graph, LeadLag, Series, Meta } from "./lib/types";

export const activeScene = writable<number>(0);
export const mode = writable<"story" | "explore">("story");
export const selectedNode = writable<string | null>(null);
export const dataset = writable<{ graph: Graph; leadlag: LeadLag[]; series: Series; meta: Meta } | null>(null);
