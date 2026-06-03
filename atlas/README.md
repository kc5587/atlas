# Atlas

Atlas maps the AI value chain and shows where to look with reproducible,
quality-checked, free data.

Live site: <https://kc5587.github.io/atlas/>

## Quickstart

```bash
make setup && make all && make web-data && make web-dev
```

## Architecture

The implementation follows the lean, reproducible architecture described in the
[design spec](../docs/superpowers/specs/2026-06-02-atlas-value-chain-design.md).

```mermaid
flowchart LR
    Y["yfinance prices"] --> I["validated Python ingest"]
    F["FRED macro"] --> I
    E["SEC EDGAR fundamentals"] --> I
    S["value_chain.yml"] --> G["validated graph loader"]
    I --> P["atomic Parquet files"]
    P --> D["dbt-duckdb models and tests"]
    G --> K["graph_nodes and graph_edges"]
    K --> D
    D --> A["lead/lag analysis"]
    A --> DB["atlas.duckdb"]
    DB --> EX["web/export_data.py → static JSON"]
    EX --> WEB["static data-story + explorable map (GitHub Pages)"]
```

`value_chain.yml` is the single source of truth for the value-chain graph.
`ingest/graph.py` validates it and writes `graph_nodes` and `graph_edges` into
DuckDB before dbt consumes them as sources.

Layer 2 adds SEC EDGAR company fundamentals for US filers: revenue, capex, and
gross margin. The analysis uses quarterly, filed-date-aligned capex lead/lag
pairs to compare upstream AI buildout signals with downstream revenue and price
returns. ASML and TSMC remain in the graph and price analysis, but their
fundamentals are deferred to Layer 2b because foreign-filer XBRL is sparse and
less comparable.

## Front-end (static data-story + explorable map)

The front-end is a static site (Vite + Svelte 5 + TypeScript) with no server:
`web/export_data.py` turns the DuckDB marts into compact JSON, and the site loads
that JSON once to render everything client-side — a stage-column value-chain map
(D3), a scroll-driven narrative (scrollama), and a free-explore mode with pan/zoom,
stage filters, and per-node drill-down. The nightly workflow exports the JSON,
builds the site, and deploys it to GitHub Pages; the data pipeline is untouched.

Run it locally:

```bash
make web-data   # export JSON from data/atlas.duckdb into web/static/data
make web-dev    # start the Vite dev server
```

## Data Refresh

The nightly GitHub Actions job runs the full pipeline and publishes an immutable,
timestamped GitHub Release such as `data-2026-06-02T040000Z`. Each release
contains `atlas.duckdb` and a `manifest.json` with the schema version, asset URL,
SHA-256 checksum, and row counts.

Publishing is atomic: the job creates a draft release, uploads all assets,
downloads the uploaded database back for checksum verification, and publishes
only after verification passes. Retention deletes whole releases, keeping the
latest 14. The app resolves the newest valid remote release and falls back to the
previous valid release with a staleness banner when needed.

## v1 to v2 Rebuild

Atlas v2 is a clean-room restart, not a refactor or code port. It was built fresh
under `atlas/` without reusing v1 code, data, environment files, or
infrastructure. The legacy `ai-value-chain-data/` tree remains reference-only.
Its archive move is intentionally pending the Phase 0 credential-rotation gate
and will be handled as a dedicated human step.

## Non-Goals

1. **Not a trading system** — no backtesting, execution, portfolio optimization, or P&L.
   It surfaces hypotheses/descriptive signals; it does not trade.
2. **Lead/lag is exploratory, not predictive** — no ML forecasting, no claimed alpha,
   explicit correlation≠causation caveats.
3. **Daily granularity is the backbone** — no real-time/streaming in the core pipeline.
4. **Free data sources only** — yfinance, FRED, EDGAR. No Bloomberg/Refinitiv; no
   point-in-time / survivorship-bias-corrected data; history bounded by free APIs.
5. **No web scraping** of analyst notes / report PDFs — structured APIs and filings only.
6. **Single-machine scale** — DuckDB, dozens–low-hundreds of tickers; no distributed
   compute, no lakehouse (Iceberg/Delta).
7. **No multi-user / auth / accounts / billing.**
8. **No heavy orchestration** — Makefile + GitHub Actions cron is the ceiling; no
   Airflow/Prefect.
9. **Geopolitical concentration risk** (Taiwan/Netherlands) is captured as graph
   metadata + narrative, not a quantitative risk model.
10. **Hosting is best-effort** — a static GitHub Pages site rebuilt nightly; not an
    HA service. Desktop layout, not mobile-polished.

**One-line scope:** Atlas maps the AI value chain and shows *where to look* with
reproducible, quality-checked, free data — it does **not** tell you what to trade,
predict prices, or run as production infrastructure.
