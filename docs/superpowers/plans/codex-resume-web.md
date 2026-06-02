You are executing a pre-approved implementation plan task-by-task. An orchestrator (Claude)
reads your stdout, patches the plan on deviations, and resumes you. Work autonomously.

## Documents
- PLAN:  /Users/kaushalchitturu/Data_Quant_project/docs/superpowers/plans/2026-06-02-atlas-datastory-map.md
- SPEC:  /Users/kaushalchitturu/Data_Quant_project/docs/superpowers/specs/2026-06-02-atlas-datastory-map-design.md
- RULES: /Users/kaushalchitturu/Data_Quant_project/docs/superpowers/plans/codex-execution-prompt.md  (all hard rules still apply)

## Scope
Build the new static front-end in `atlas/web/` (Vite + Svelte 5 + TypeScript) plus the
Python `web/export_data.py`. The data pipeline (ingest/dbt/analysis) is UNCHANGED — do not
touch it except to read its DuckDB. Start at Task 1 and go through Task 11.

## Behavior
- Hard rules from RULES: strict TDD order (write failing test, confirm it fails, implement,
  pass, commit), NEVER edit a test to pass, NO push, NO tags, commit per task.
- COMMIT SCOPING: never `git add -A` / `git add .`. Stage only the exact paths each task
  lists. The repo has unrelated files.
- Environments: Python via `uv` (from `atlas/`); Node 20 + npm (from `atlas/web/`). Run
  `npm install` in Task 2 and commit `package-lock.json`. Run `npx playwright install
  --with-deps chromium` before the smoke test.
- Generated data (`atlas/web/static/data/`), `node_modules/`, and `dist/` are gitignored —
  never commit them.
- Streamlit removal (Task 11) only after the web app's smoke test is green.

## When to STOP (emit a line starting `STOP:` and exit)
Only for: (a) a failing test you cannot satisfy without editing the test, (b) a genuine
plan-vs-reality contradiction (e.g. a library API differs from the plan's code), or (c) a
blocked step needing network/data you can't produce (e.g. no `atlas.duckdb` to export from,
or a fixtures DuckDB is needed for CI/smoke). For network-data needs: try `make all` to build
the DB locally first; if that needs blocked network, STOP and ask the human to run it.

## Notes
- Svelte 5 runes (`$state`, `$derived`, `$effect`, `$props`) and `mount()` are intentional —
  do not downgrade to Svelte 4 syntax.
- The smoke test (Task 10) and CI (Task 11) need real exported JSON; if `atlas/data/atlas.duckdb`
  is absent, build it (`make all`) or create a tiny `atlas/tests/fixtures/atlas.duckdb` (reuse
  the Task 1 fixture helper) and export from that.

## End of run
Print a `RUN SUMMARY`: tasks completed (with commit hashes), any STOPs (with reason), and any
human-action items. Begin at Task 1 now.
