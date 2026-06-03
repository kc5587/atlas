You are executing the Atlas Layer 2 (SEC EDGAR fundamentals) plan task-by-task with TDD.
An orchestrator (Claude) will read your stdout, patch on deviations, and resume you. Work
autonomously.

## Documents (read all three)
- PLAN:        /Users/kaushalchitturu/Data_Quant_project/docs/superpowers/plans/2026-06-02-atlas-layer2-fundamentals.md
- RECONCILE:   /Users/kaushalchitturu/Data_Quant_project/docs/superpowers/plans/2026-06-02-atlas-layer2-frontend-reconciliation.md  ← OVERRIDES the plan's Tasks 6 & 7
- SCOPE/DECISIONS: /Users/kaushalchitturu/Data_Quant_project/docs/superpowers/specs/2026-06-02-atlas-layer2-fundamentals-scope.md
- RULES:       /Users/kaushalchitturu/Data_Quant_project/docs/superpowers/plans/codex-execution-prompt.md (hard rules still apply)

## Critical: the plan is partly stale
The PLAN predates the front-end rebuild that REMOVED Streamlit. `atlas/app/` now contains only
`__init__.py` — there is NO `streamlit_app.py` and NO `app/data.py`. Follow the RECONCILE doc
for Tasks 6 & 7: do NOT create or edit any Streamlit file or `APP_SCHEMA_VERSION`. The Svelte
front-end already consumes fundamentals via `web/export_data.py` + `NodePanel.svelte`.

## Execute
- Tasks 1–5 of the PLAN as written (CIK in value_chain.yml + loader; SEC config + FUNDAMENTAL_SCHEMA;
  `ingest/fundamentals.py` resolver + point-in-time normalize; dbt `stg_fundamentals` +
  `fundamentals_quarterly`; `leadlag.py` quarterly capex→revenue + capex→price pairs).
- Task 6: use the RECONCILE version (verify export/build/smoke; NO Streamlit).
- Task 7: use the RECONCILE version (fundamentals fixture + publish_release ROW_COUNT_TABLES;
  NO app/data.py).
- Task 8 (docs) as written.

## Behavior / hard rules
- Strict TDD: failing test first, confirm it fails, implement, confirm pass, commit per task.
  Run Python via `uv` from `atlas/`: `uv run --extra dev python -m pytest ...`.
- NEVER edit a test to force a pass. Path-scoped commits only — NEVER `git add -A`. Do NOT
  commit generated data (`data/`, `web/static/data/`, `dist/`, `node_modules/`).
- NO push, NO tags (the orchestrator/human handles pushing to the public repo).
- SEC resilience: `ingest/fundamentals.py` `run()` must tolerate a failed CIK/metric fetch
  (skip + continue), mirroring the macro per-series tolerance — one company's SEC timeout must
  not abort `make all`. Set/expect `ATLAS_SEC_USER_AGENT` for SEC requests.
- Note: `value_chain.yml` was just expanded to 15 nodes — add `cik` to the US-filer nodes
  among them (NVDA, AMD, AVGO, MU, AMAT, LRCX, MSFT, GOOGL, AMZN, META, ORCL, DELL, SMCI);
  ASML/TSM stay without cik (foreign filers, deferred).

## STOP conditions
Emit `STOP:` and exit for: a test you can't pass without editing it, a genuine plan-vs-reality
contradiction, or a blocked network/data step (e.g. SEC unreachable AND no fixture path).

## End
Print a `RUN SUMMARY`: tasks completed with commit hashes, any STOPs, human-action items.
Begin at Task 1.
