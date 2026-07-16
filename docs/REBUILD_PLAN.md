# Atlas Rebuild Plan

This plan is deliberately finite. The destination and stopping rule are in
[V1_RELEASE_SPEC.md](V1_RELEASE_SPEC.md); this file only describes the order of
work needed to reach it.

## Phase 1 — Contract and core (complete)

- Product thesis, fixed scope, evidence rules, and v1 acceptance criteria.
- Immutable observations, provenance, graph validation, and scoring.
- Deterministic fixture ranking and versioned export contract.

## Phase 2 — Live refresh layer (complete)

- EIA refresh for the seven fixed balancing authorities.
- SEC refresh for the eight fixed public companies.
- Raw response caching, checksums, schema validation, and refresh manifest.
- Safe failure semantics: failed refreshes do not look current.

## Phase 3 — Research pipeline (complete)

- Connect live observations to the existing demand, supply, and price transforms.
- Add filed capex trend calculations and company evidence tables.
- Add the separate execution-friction evidence panel from authoritative reports.
- Add sensitivity checks for lookback windows and component weights.

## Phase 4 — Report and release (complete)

- Generate the static report and JSON export from one snapshot.
- Add source drill-down, methodology, missing-data, and caveat sections.
- Add `make setup`, `make test`, `make refresh`, and `make report`.
- Run clean-checkout, coverage, security, and reproducibility gates.

Release verification passed: 46 tests, 89.4% package coverage, deterministic
fixture snapshot/report generation, Python compilation, and diff hygiene.

## Scope-control rules

- Work must map to one v1 acceptance criterion or fix a release blocker.
- New data sources require removing or deferring something else in v1.
- No UI polish before the live pipeline can produce a complete snapshot.
- No composite component is added without a comparable source and a testable
  definition.
- Once v1 acceptance passes, stop and release; do not continue polishing inside
  the v1 milestone.
