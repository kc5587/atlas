import { svelte } from "@sveltejs/vite-plugin-svelte";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [svelte()],
  base: "./",
  publicDir: "static",          // copies static/data/*.json into dist/data/ — REQUIRED
  build: { outDir: "dist" },
  // Vitest owns unit tests (*.test.ts); Playwright owns smoke specs (*.spec.ts).
  test: { include: ["tests/**/*.test.ts"] },
});
