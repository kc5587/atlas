# Atlas — AI Value-Chain Research Engine (v2)

**Date:** 2026-06-02
**Status:** Design approved (pending written-spec review)
**Supersedes:** v1 `ai-value-chain-data` (Airflow + MinIO + Postgres + FastAPI on EC2)

---

## 0. Phase Zero — Public-Release Security Gate (BLOCKING)

This repo targets a public showcase, and the current working tree is not safe to
publish. **No push to a public remote, no tag, and no archival of v1 may happen until
this gate passes.** Known exposures today: `ai-value-chain-data/.env` is tracked, an
`ssh_key` / `ssh_key.pub` pair is present, and DuckDB data + logs are tracked; there is
no repository `.gitignore`.

Gate steps (all required, in order):

1. **Credential audit.** Enumerate every secret in the working tree *and in git
   history* — scan with a tool (e.g., `gitleaks` / `trufflehog`) plus a manual review of
   `.env`, `*.pem`, `ssh_key*`, `*.duckdb`, and config files. Produce a written list.
2. **Rotation rule.** Treat every credential that has *ever* been committed as
   compromised: rotate it (API keys, DB passwords, SSH keypair) regardless of the
   history-scrub decision. Removal from history is not a substitute for rotation.
3. **History-scrub decision.** Decide explicitly: (a) scrub secrets from history with
   `git filter-repo` / BFG before going public, or (b) start the public repo from a
   fresh history (recommended given the messy v1 log and the fresh-scaffold migration).
   Record the choice and rationale in the README.
4. **Explicit denylist.** Add a repository `.gitignore` before any further commits:
   at minimum `.env`, `*.env`, `*.pem`, `ssh_key*`, `*.duckdb`, `data/`, `logs/`,
   `*.log`, `__pycache__/`, `.venv/`. Add a CI secret-scan step (gitleaks) that fails
   the build on any detected secret.
5. **Verification.** Re-run the secret scan on the exact tree/commit to be published and
   confirm clean before tagging or pushing public.

## 1. Purpose & Audience

Atlas maps the AI value chain and surfaces *where to look* for tradeable structure —
who supplies whom, where bottlenecks are, and how long upstream activity takes to
show up downstream. It is built as:

- A **GitHub showcase** — clone-and-run, strong narrative, a live hosted demo link.
- A **personal research engine** — a production-grade, reproducible pipeline the
  author uses to generate AI-value-chain hypotheses.

The author is the primary user. A hiring manager or peer should be able to clone the
repo, run one command, and immediately get the story.

## 2. What "Shipped" Means

- One-command local run (`make setup && make all && make app`).
- A free, public hosted demo (Streamlit Community Cloud) linked from the README.
- A nightly GitHub Actions job that refreshes data so the demo stays current.
- Reproducible, quality-checked, documented — the engineering rigor *is* the pitch.

## 3. Headline Deliverable

Three layered artifacts, built end-to-end as a slice first, then layered:

1. **Interactive value-chain map** — navigable supply-chain graph; nodes show latest
   price/return, edges encode dependency + measured lead/lag.
2. **Research report** — rendered narrative mapping the chain, the lead/lag findings,
   and explicit "where to look next" hypotheses.
3. **Dashboard** — returns charts, correlation heatmap, macro overlays.

## 4. Architecture (lean & reproducible)

```
atlas/
  ingest/                  # idempotent Python modules, one per source
    _base.py               # atomic parquet writes, retry/backoff, pandera validation
    prices.py              # yfinance -> data/raw/prices/*.parquet  (written from scratch)
    macro.py               # FRED   -> data/raw/macro/*.parquet
    graph.py               # validate value_chain.yml -> graph_nodes/graph_edges in duckdb
  seeds/
    value_chain.yml        # SINGLE SOURCE OF TRUTH: nodes + edges
  dbt/                     # dbt-duckdb project
    models/
      staging/             # stg_prices, stg_macro (clean, typed)
      marts/               # prices_daily, returns, macro_daily
      graph/               # graph_nodes, graph_edges (dbt sources from the YAML loader)
    tests/                 # schema tests = data-quality checks
  analysis/
    leadlag.py             # cross-correlation lead/lag (returns table)
  app/
    streamlit_app.py       # 3 tabs: map | dashboard | report
  reports/
    report.qmd             # rendered narrative
  .github/workflows/
    ci.yml                 # secret-scan (gitleaks) + lint + pytest + dbt build on every push
    update-data.yml        # nightly cron: ingest -> dbt build -> publish immutable DuckDB release
  data/                    # parquet landing + atlas.duckdb (gitignored; cron-refreshed)
  Makefile                 # setup / ingest / build / analyze / app / all
  pyproject.toml
  README.md
```

### Data flow

```
yfinance / FRED
   -> ingest/*.py  (validate -> atomic parquet write)
   -> data/raw/**.parquet
   -> dbt-duckdb staging (clean/typed)
ingest/graph.py: validate value_chain.yml -> graph_nodes/graph_edges (dbt sources)
   -> marts (prices_daily, returns, macro_daily) + graph models (read graph_nodes/edges)
   -> analysis/leadlag.py (reads marts -> leadlag table in duckdb)
   -> app/streamlit_app.py (reads marts + leadlag) + reports/report.qmd
```

### Value-chain graph model

`seeds/value_chain.yml` is the version-controlled spine. Extending this file is how
fundamentals, forgotten plays, and new edges get added later.

**Loading mechanism (important):** dbt seeds are CSV-only, so the YAML is **not** a dbt
seed. A small, tested loader `ingest/graph.py` validates the YAML (pandera/pydantic) and
writes two tables into DuckDB — `graph_nodes` and `graph_edges`. dbt then reads these as
**sources** (`graph/` models reference them), not as seeds. (Alternative considered:
compile YAML → CSV seeds; rejected because the YAML carries nested/edge metadata that
maps poorly to flat CSV and we want one validated loader.)

Schema requirements:

- **Stable node ID.** Each node has an immutable `id` (slug, e.g. `asml`) that is the
  primary key — *not* the ticker. Tickers change/relist; edges reference `id`.
- **Ticker aliases.** `tickers:` is a list (primary + aliases/historical) so renames and
  multi-listing don't break joins to price data.
- **Edge direction is explicit:** `from` = upstream supplier, `to` = downstream customer
  (goods/value flow upstream→downstream). Stated once, enforced in the loader.
- **Provenance:** every edge carries `evidence` (source/citation) and `as_of` (date the
  relationship was asserted) so the graph is auditable and time-aware.

```yaml
nodes:
  - id: asml
    name: ASML Holding
    tickers: [ASML]
    stage: equipment        # equipment | foundry | chips | cloud
    region: NL
  # ...
edges:
  - from: asml              # upstream supplier (node id)
    to: tsmc                # downstream customer (node id)
    relationship: supplies  # supplies | partner
    note: EUV lithography systems
    evidence: "ASML FY2023 20-F, customer concentration"
    as_of: 2024-01-01
  # ...
```

`networkx` is used for layout/analysis off `graph_nodes` / `graph_edges`.

### Lead/lag analysis

- **Inputs:** daily log returns per node (and per macro series, differenced to
  stationarity where levels are non-stationary, e.g. rates).
- **Lag convention (explicit):** lag `k` correlates `upstream_t` with `downstream_{t+k}`;
  positive `k` means upstream **leads** downstream by `k` trading days. Direction is
  defined once and asserted in tests.
- **Sample window:** a fixed, documented lookback (default: trailing 3 years of trading
  days) plus the full-history run, both reported. The window is a config constant.
- **Calendar alignment:** align on a shared trading-day calendar; do **not** forward-fill
  prices across missing market days. Price↔price pairs are inner-joined on date.
- **Low-frequency macro — native-frequency analysis is mandatory.** A monthly/weekly
  macro series must **never** be forward-filled onto daily dates for the correlation
  itself — repeated values distort both the correlation magnitude and the inferred lag,
  and counting them as daily observations is meaningless. For a (price, macro) pair, the
  correlation/lag scan is computed at the macro series' **native frequency**: resample
  price returns to that frequency (e.g. monthly log returns) and run the lag scan in that
  frequency's units; lags are expressed in native periods (months), not trading days.
  The **effective-observations** count (= number of distinct native macro releases in the
  window) is used *additionally* — for the `N_min` threshold and for the
  autocorrelation-aware inference — not as a substitute for native-frequency analysis.
- **Minimum observations:** a pair is skipped (not reported) below `N_min` *effective*
  observations after alignment — `N_min = 250` for daily price↔price pairs; a separate,
  smaller native-frequency floor for macro pairs (e.g. `≥ 36` monthly observations).
- **Lag scan:** `-20…+20` trading days for price↔price (41 lags); a frequency-appropriate
  window for macro pairs. The peak is **not** reported as significant on its own.
- **Base p-values must be autocorrelation-aware.** Financial returns are serially
  dependent, so ordinary Pearson p-values understate uncertainty. Compute base p-values
  via a **stationary/circular block bootstrap** (block length tuned to series memory) or
  a temporal-structure-preserving **permutation** test — not the closed-form Pearson
  p-value. (HAC/Newey–West-adjusted inference is an acceptable alternative.)
- **Multiple-testing correction:** treat the (lags × pairs) family together and apply
  **Benjamini–Hochberg FDR** to the autocorrelation-aware base p-values; flag only
  pairs/lags surviving the threshold. The raw peak is shown but labeled "uncorrected."
- **Stability check:** recompute over two non-overlapping subperiods (and/or a rolling
  window); a finding is marked "stable" only if the peak lag's sign and approximate
  magnitude persist. Unstable peaks are reported but flagged.
- **Output:** a tidy table (pair, lag, corr, q-value, n_obs, stable?) consumed by app +
  report.
- **Framing:** descriptive/exploratory only — correlation ≠ causation, stated explicitly.

### Data quality & error handling

- **Ingest:** pandera schema validation on every external response *before* writing;
  atomic parquet writes (temp file -> rename) so a partial failure writes nothing;
  retry with exponential backoff.
- **Transform:** dbt tests — `not_null`, `unique(ticker, date)`, accepted `stage`
  values, freshness / row-count thresholds.
- **CI:** every push runs lint + pytest + a full `dbt build` against tiny fixtures.

## 5. First Vertical Slice (this spec's implementation scope)

**Prerequisite:** Section 0 (Phase Zero security gate) and the Section 10 clean-room
boundary must be satisfied before the slice ships publicly.

Touches every layer on a tight scope:

- **Universe:** ~12–15 tickers along the core spine
  (ASML → TSMC → NVDA/AMD/Broadcom → MSFT/GOOGL/AMZN hyperscalers — exact list curated
  in `value_chain.yml`).
- **Data:** daily prices (yfinance) + a few FRED macro series (e.g., Fed Funds, 10Y,
  semiconductor billings / SOX-proxy).
- **Graph:** `value_chain.yml` for the spine -> `graph_nodes` / `graph_edges`.
- **Analysis:** lead/lag cross-correlation for edges and (node, macro) pairs.
- **Presentation:** Streamlit app — interactive map + dashboard + embedded report.
- **Ops:** Makefile one-command run; CI green; nightly cron; hosted on Streamlit Cloud.

## 6. Reproducibility

- `make setup` — create env, install deps (uv/pip via pyproject.toml).
- `make all` — ingest -> dbt build -> analysis.
- `make app` — launch Streamlit.

**Hosted-refresh handoff (corrected).** Streamlit Community Cloud serves files from the
repo; GitHub Actions *artifacts* are workflow-scoped and are **not** visible to the app,
so the nightly job cannot "publish an artifact" and have Streamlit pick it up. Real path:

- **Primary: immutable, date-tagged data releases.** Each run publishes a new
  **immutable** release — never a mutable `data-latest` asset, which can leave a
  half-updated DB/checksum pair if a job fails mid-upload. Each release carries:
  - `atlas.duckdb` (the DB asset),
  - `manifest.json` — `{ generated_at, schema_version, db_asset_url, sha256, row_counts }`.
- **Release lifecycle (atomic publish).** The cron must: (1) create the release as a
  **draft**, (2) upload *all* assets to the draft, (3) verify the uploaded `sha256`
  matches the manifest, then (4) **publish** the draft. A run that fails before step 4
  leaves only an unpublished draft the app never sees — so no consumer ever observes a
  partial release.
- **Unique, never-reused tags.** Immutable release tag names cannot be reused, so tags
  are timestamped, not date-only: `data-2026-06-02T040000Z`. This makes same-day reruns
  and backfills safe.
- **Resolution:** the app lists releases, picks the **newest release whose manifest +
  checksum validate**, downloads that `atlas.duckdb`, and re-verifies `sha256` before
  loading. A manifest `schema_version` mismatch with the app is treated as invalid.
- **Durable fallback is remote, not local.** Streamlit Community Cloud does **not**
  guarantee local-file persistence across restarts, so a local cache is treated as
  *best-effort within a warm instance only*. The authoritative fallback is to step back
  one release: if the newest release fails to validate/download, resolve the
  **previous valid date-tagged release** remotely. The app shows a "data as of <ts>"
  staleness banner whenever it serves anything other than the newest release.
- **Retention:** the cron prunes old data by deleting **entire releases** (release + its
  tag + all its assets), keeping the last N (e.g. 14) — never deleting individual assets
  out of a retained release, which would corrupt that release's manifest/checksum pair.
- **Alternatives considered:** (a) Git LFS `data` branch — bloats repo, LFS quota; (b)
  external object storage (S3/R2) — cleaner for large data but adds a credential + cost.
  Immutable release assets are the zero-cost, no-secret default at this scale.

## 7. Testing

- **pytest** on ingest modules: mocked HTTP, schema validation, idempotency.
- **dbt tests** for data-quality.
- **CI smoke test** building the whole pipeline on tiny fixtures.
- Target **80%+** coverage on Python library code.

## 8. Non-Goals (v2 will NOT do these — stated in README)

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
10. **Hosting is best-effort** — free Streamlit Cloud sleeps when idle; not an HA
    service. Desktop layout, not mobile-polished.

**One-line scope:** Atlas maps the AI value chain and shows *where to look* with
reproducible, quality-checked, free data — it does **not** tell you what to trade,
predict prices, or run as production infrastructure.

## 9. Roadmap (post-slice layers)

- **Layer 2 — Fundamentals:** SEC EDGAR capex/revenue/margins; capex→downstream lead/lag.
- **Layer 3 — Forgotten plays:** extend `value_chain.yml` with power utilities, cooling,
  fiber, edge; add a ranking of "not-yet-priced-in" candidates.
- **Layer 4 — Query API:** optional FastAPI over DuckDB for programmatic QR access.
- **Layer 5 — Intraday event-study module:** optional, bounded minute-bar analysis around
  earnings / monthly-sales releases. Not part of the core daily pipeline.

## 10. Migration from v1 (operational boundary)

The restart is a **clean-room rebuild**, not a refactor or a port:

- **Built from scratch.** v2 is built fresh in a new `atlas/` tree with its own history
  (see Phase 0 history-scrub decision). **No v1 code is ported** — `ingest/prices.py` is
  written from scratch against the current yfinance API, not lifted from v1.
- **v1 is reference-only.** The legacy `ai-value-chain-data/` tree is frozen — no edits,
  no commits, no code reuse. It may be *read* for inspiration only. It is archived
  (tagged branch or `legacy/`) after the Phase 0 security gate passes, and referenced in
  the README as the deliberate "v1 → v2 rebuild" engineering-judgment narrative.
- **No legacy reuse, full stop.** Do **not** reuse legacy code, data files (`*.duckdb`,
  parquet, CSV exports), `.env` / secrets, or any infrastructure config (docker-compose,
  Airflow, MinIO, EC2). v2 regenerates everything from source.
- **Dropped infra:** Airflow (-> GH Actions cron), MinIO (-> parquet), Postgres serving +
  FastAPI (-> deferred to Layer 4; DuckDB serves the app directly), EC2/SSH ops
  (-> Streamlit Cloud).
