You are executing a pre-approved implementation plan task-by-task. Treat each task as an
isolated unit of work (subagent-driven discipline): finish one fully, commit, then move to
the next.

## Authoritative documents (read both before starting)
- PLAN: /Users/kaushalchitturu/Data_Quant_project/docs/superpowers/plans/2026-06-02-atlas-value-chain-slice.md
- SPEC: /Users/kaushalchitturu/Data_Quant_project/docs/superpowers/specs/2026-06-02-atlas-value-chain-design.md

The PLAN is the source of truth for what to build. The SPEC explains why; consult it when
a task's intent is unclear. Do NOT redesign — implement the plan as written.

## Repository
- Repo root: /Users/kaushalchitturu/Data_Quant_project
- New code goes in a fresh `atlas/` package (clean-room rebuild).
- Python 3.11 via `uv`. From `atlas/`: `uv venv && uv pip install -e ".[dev]"`, run tests
  with `uv run pytest`.

## Execution protocol (per task)
1. Announce the task number and title.
2. Execute its steps **in the exact order given**. For TDD tasks this means:
   a. Write the failing test verbatim from the plan.
   b. Run it and CONFIRM it fails for the stated reason. If it does not fail as expected,
      STOP and report — do not proceed.
   c. Write the implementation from the plan.
   d. Run the test and confirm it passes.
   e. Run the commit command exactly as written in the plan (use its commit message).
3. Use the plan's exact file paths, code, commands, and commit messages. The code blocks
   are complete — type them as given; do not invent extra abstractions or "improvements".
4. After each task: print a 2-3 line summary (files changed, tests passing) and continue to
   the next task automatically unless a STOP condition is hit.

## Hard rules
- TDD is mandatory. NEVER write implementation before its failing test. NEVER edit a test
  to make it pass — if implementation can't satisfy the test after a genuine attempt, STOP
  and report the blocker.
- No placeholders, no TODOs, no stubbed logic. Every function must be fully implemented.
- Clean-room: do NOT copy, import, or adapt any code from `ai-value-chain-data/` (v1). Do
  NOT reuse v1 data files, `.env`, secrets, or infra config. v1 is read-only reference.
- Commit after every task (the plan gives messages). Frequent small commits.
- Do NOT push to any remote. Do NOT create tags. Do NOT make the repo public. (Phase 0 is a
  security gate; publishing is a later human decision.)
- Stay within the repo root sandbox.

## Phase 0 contains human-only actions — PAUSE, don't fake
Phase 0 includes credential rotation (Task 0.4 Step 1) and a history-scrub decision that
require a human. When you reach a step that needs the operator to rotate a real secret at a
provider, or to confirm the fresh-history decision:
- Do the parts you CAN do (write `.gitignore`, untrack files, run gitleaks, write
  `SECURITY_AUDIT.md` with findings).
- Then STOP and print exactly what the human must do (which credentials to rotate, paste
  the gitleaks history findings) before Phase 0 can be marked green.
- Do NOT invent secret values or claim rotation happened.

## Tooling note
- gitleaks: if not installed, print the install command (`brew install gitleaks`) and pause
  rather than skipping the scan.
- `dbt build` / Streamlit smoke tasks need real ingested data. For ingestion tasks that hit
  the network (yfinance/FRED), run them once to produce `data/raw/`; if the network is
  unavailable in this sandbox, STOP and report so the operator can run `make ingest`.

## Deviation handling
If the codebase reality differs from the plan (a path exists, a dependency fails to
resolve, an API signature changed), STOP and report the discrepancy with options. Do not
silently work around it.

## Start
Begin with Phase 0, Task 0.1. Work sequentially through to Phase 9, Task 9.3, pausing only
at STOP conditions and Phase 0 human-action gates. After each phase, print a one-line phase
summary.
