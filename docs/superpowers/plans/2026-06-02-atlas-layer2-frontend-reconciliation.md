# Layer 2 — Front-End Reconciliation (supersedes parts of the Layer 2 plan)

The Layer 2 plan (`2026-06-02-atlas-layer2-fundamentals.md`) was written **before** the
front-end rebuild that retired Streamlit. Its Tasks 6 and 7 reference deleted files
(`app/streamlit_app.py`, `app/data.py`, `APP_SCHEMA_VERSION`). This addendum corrects them.
**Tasks 1–5 and 8 of the Layer 2 plan are unchanged and valid.**

## Current architecture reality
- There is **no Streamlit app.** The public UI is the static Svelte site in `atlas/web/`.
- The site consumes data via `atlas/web/export_data.py`, which **already emits
  `series.fundamentals`** (capex/revenue/gross_margin) *when the `fundamentals_quarterly`
  mart exists* (see its `_has_table("fundamentals_quarterly")` branch).
- The Svelte `NodePanel.svelte` **already renders a node's capex chart** when
  `series.fundamentals[ticker]` is present, and scene 5 ("the upstream pull") is wired for
  capex. So once Layer 2 produces the mart, fundamentals flow to the live site **with no
  Streamlit work at all.**
- `meta.json` `schema_version` is already `"2"` (set in `export_data.py`); there is no app-side
  `APP_SCHEMA_VERSION` consumer anymore. Do **not** recreate one.

## REPLACE Layer 2 Task 6 (was: "Streamlit Fundamentals view")
**DROP it.** No Streamlit. Instead, a verification step:
- After the dbt `fundamentals_quarterly` mart and the lead/lag `fund_capex_rev` /
  `fund_capex_price` rows exist, run `web/export_data.py` and confirm `series.json` now
  contains a `fundamentals` object and `leadlag.json` contains `fund_*` rows.
- Confirm the existing front-end renders them: `cd atlas/web && npm run build` then the
  Playwright smoke (`npx playwright test`) still passes. (Optional polish, not required: a
  small "capex" callout in the dashboard tab — only if trivial.)
- No commit of front-end source is required unless you make the optional polish.

## REPLACE Layer 2 Task 7 (was: "CI fixtures, coverage, schema bump" touching `app/data.py`)
Keep everything EXCEPT the `app/data.py` edit (that file is gone):
- **Do:** add the fundamentals fixture (`atlas/web/tests/...` or `atlas/tests/fixtures/...`)
  consistent with how the front-end fixture DB is already built in
  `atlas/web/tests/make_fixture_db.py` — extend that helper (or add a sibling) so a
  `fundamentals_quarterly` table can be present for the export/smoke path.
- **Do:** add `stg_fundamentals` and `fundamentals_quarterly` to
  `atlas/scripts/publish_release.py` `ROW_COUNT_TABLES` (so nightly release manifests count
  them).
- **Do NOT:** touch `app/data.py` or any `APP_SCHEMA_VERSION`. `schema_version` stays `"2"`
  in `web/export_data.py`; if you decide a bump is warranted, change it ONLY there and in
  `publish_release.py` `SCHEMA_VERSION` together — but a bump is NOT required (the front-end
  reads whatever JSON it's given and degrades gracefully on missing keys).

## Shipping Layer 2 to the live site
After Tasks 1–5 + the reconciled 6–7 + 8 are committed and pushed:
- A manual `gh workflow run update-data.yml` (or the nightly) rebuilds the DuckDB **with the
  new seed CIKs + fundamentals mart**, publishes a new `data-*` release, and `deploy-web`
  ships it. The live NodePanel capex charts + capex lead/lag then light up.
- Note: SEC EDGAR also needs network from the runner. If SEC times out like FRED, apply the
  SAME per-source tolerance pattern used for macro (skip a failed CIK/metric, continue) so
  `make all` stays green — Layer 2 Task 3's resolver already returns empty on failure, but
  ensure `run()` never aborts the whole pipeline on one company's fetch error.
- Set `ATLAS_SEC_USER_AGENT` (a real contact string) in the workflow env for SEC.
