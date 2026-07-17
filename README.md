# Atlas: AI Infrastructure Bottleneck Monitor

Atlas is a provenance-first research pipeline for examining where the physical
and financial constraints of AI infrastructure may be tightening. It combines
electricity-system observations, wholesale-market data, public-company filings,
and interconnection-queue evidence into an auditable regional pressure report.

Atlas is descriptive and exploratory. Its pressure score is not a shortage
probability, outage forecast, price forecast, trading signal, causal estimate,
or investment recommendation.

## Release status

**v1.1 implementation complete — last repository verification: 2026-07-17.**

The fixed v1.1 scope is implemented and the repository checks pass:

- 61 automated tests pass.
- Package coverage is 86%, above the CI gate of 80%.
- The deterministic fixture snapshot and static report build successfully.
- No unfinished-work markers were found in the
  source, scripts, tests, or release documentation.

The live v1.1 validation bundle has also been run against the fixed
2022–2025 window: 529,434 observations, seven benchmark regions, and zero
validation violations. ERCO remains the documented wholesale-price source
limitation; the other six required price regions have source coverage. Report
headline cards use the latest complete common operating day, so partial UTC
days cannot distort the current score.

The full live snapshot and validation outputs are intentionally ignored by Git
because they contain raw source responses and generated artifacts. Therefore,
this checkout verifies the implementation and offline reproducibility gates;
an operator must run the live workflow with credentials and source files before
treating a new data vintage as a completed live validation release.

The scope, acceptance criteria, and stopping rule are defined in
[docs/V1_1_RELEASE_SPEC.md](docs/V1_1_RELEASE_SPEC.md).

## What Atlas measures

Atlas evaluates seven US balancing-authority regions:

| ID | Region |
| --- | --- |
| ERCO | ERCOT |
| PJM | PJM |
| MISO | MISO |
| CISO | CAISO |
| SWPP | SPP |
| NYIS | NYISO |
| ISNE | ISO-NE |

The live refresh also extracts filed capital-expenditure observations for
eight public infrastructure buyers: Microsoft, Amazon, Alphabet, Meta, Oracle,
Equinix, Digital Realty, and Vertiv.

## Research model

### Evidence and provenance

Every observation carries an identifier, metric, entity, period, value, unit,
source, source URL, retrieval time, source vintage, evidence type, and quality
flags. Derived scores retain the observation IDs that contributed to each
component. This makes the report inspectable rather than a collection of
untraceable numbers.

Atlas distinguishes three evidence types:

- **Observed:** directly reported by a source, such as hourly demand or a filed
  accounting fact.
- **Estimated:** produced by a published scenario or methodology, such as IEA
  or Berkeley Lab context.
- **Inferred:** an Atlas transformation or interpretation, such as the
  unweighted mean of NYISO zonal prices.

### Regional pressure score

Each available component is normalised to a 0–100 pressure scale and combined
using the default weights below:

| Component | Default weight | Implementation |
| --- | ---: | --- |
| Demand pressure | 35% | Current daily peak versus a trailing daily-peak baseline. |
| Supply tightness | 30% | Worst aligned same-hour generation headroom relative to demand. |
| Price stress | 20% | Current daily high price percentile versus trailing history. |
| Execution friction | 15% | First-class component for connection and execution evidence. |

Execution friction is never fabricated. When no comparable regional observation
is available, it remains missing: pressure is calculated from available
components, while confidence is reduced and the missing component is shown in
the report. Interconnection evidence is presented separately as a benchmark
panel rather than silently converted into a score.

The score exposes raw component values, weights, contributions, confidence,
observation IDs, and missing components. Region ranking breaks ties
deterministically by region ID.

## Data pipeline

The pipeline has four stages:

~~~text
source files / APIs
        |
        v
validated observations with provenance
        |
        v
checksummed, atomic snapshot
        |
        v
scores + historical evaluation + benchmark
        |
        v
JSON export and dependency-free static HTML report
~~~

### Ingestion and refresh

- EIA Grid Monitor API: paginated hourly demand and generation data.
- EIA-930 bulk balance files: sustained historical demand and net generation.
- EIA wholesale exports: supported regional daily high-price observations.
- NYISO archived zonal LBMP files: hourly NYISO zone means mapped to NYIS,
  explicitly marked as an inferred unweighted zone mean.
- SEC Company Facts: filed capital-expenditure facts for the supported public
  companies.
- Berkeley Lab Queued Up 2025: interconnection projects aggregated by region
  into active capacity, project counts, withdrawal rates, and time to
  commercial operation.

Each refresh stages raw and curated artifacts, writes SHA-256 checksums and
source metadata to a manifest, and publishes the snapshot atomically. A failed
refresh writes a failure marker and never presents partial data as current.

### v1.1 historical validation

The fixed validation design covers 2022-01-01 through 2025-12-31, subject to
source availability and the recorded as-of date. It:

1. Chooses the last observed demand day in each month as the as-of date.
2. Requires at least 365 days of history before scoring a date.
3. Compares each as-of score with realised composite pressure 30 and 90 days
   later.
4. Reports observation counts, Spearman rank correlation, and mean future
   pressure change.
5. Runs fixed sensitivity scenarios across demand lookbacks, price lookbacks,
   and baseline/demand-heavy/market-heavy weight sets.
6. Checks date coverage, minimum history, structural duplicates, and required
   price coverage before publishing validation output.

The backtest is look-ahead-safe: scores use observations through the as-of
date, while outcomes use only subsequent observations.

## Generated outputs

The live validation command writes the following artifacts to its output
directory:

- validation.json — coverage, date-range, duplicate, and release-gate checks.
- backtest.json — 30/90-day hindcast rows and summaries.
- sensitivity.json — score ranges and stability across fixed scenarios.
- report.json — versioned report payload with scores, history, companies,
  caveats, and benchmark data.
- report.html — dependency-free static report with regional cards, component
  history, validation tables, source links, and limitations.

## Quickstart

The project requires Python 3.12 or newer and uses uv for environment setup.

~~~bash
make setup
make test
make fixture-report
~~~

make fixture-report is the offline reproducibility check. It builds a small
deterministic snapshot from data/fixtures/ and renders a temporary HTML report
without network access.

### Live refresh

Set both required credentials before refreshing:

~~~bash
export EIA_API_KEY="..."
export SEC_USER_AGENT="Atlas Research <you@example.com>"

make refresh
~~~

The default historical window is 2022-01-01 through 2025-12-31. Optional local
price and bulk operating files can be supplied through the underlying script:

~~~bash
PYTHONPATH=src python3 scripts/refresh_snapshot.py \
  --start 2022-01-01 \
  --end 2025-12-31 \
  --wholesale-price-csv /path/to/wholesale.csv \
  --nyiso-price-root /path/to/nyiso-zips \
  --eia930-balance-root /path/to/eia930-csvs
~~~

### Report and validation

Generate a report from the latest complete snapshot:

~~~bash
make report
~~~

Run the complete v1.1 validation bundle after preparing any Berkeley Lab
benchmark JSON:

~~~bash
make validation \
  LIVE_SNAPSHOT=data/snapshots/<snapshot-id> \
  VALIDATION_OUTPUT=/path/to/validation-output \
  BENCHMARK_JSON=/path/to/atlas-queue-benchmark.json
~~~

The live workflow fails loudly when credentials, snapshots, source coverage,
or required inputs are missing.

## Repository layout

~~~text
src/atlas/
  evidence.py       immutable observation and source contracts
  graph.py          value-chain graph validation
  scoring.py        transparent weighted pressure score
  refresh.py        atomic snapshot orchestration
  snapshot.py       JSON persistence, manifests, and checksums
  ingest/            EIA, EIA-930, wholesale, NYISO, and SEC adapters
  analysis/          demand, supply, price, evaluation, validation, and queue logic
  reporting.py       versioned export and static HTML renderer
  report_pipeline.py snapshot-to-report composition

scripts/
  refresh_snapshot.py
  run_validation.py
  generate_report.py
  build_fixture_snapshot.py
  prepare_interconnection_benchmark.py
  download_*.py / prepare_*.py

tests/                              unit and integration coverage
data/fixtures/                      deterministic offline inputs
docs/                                project design and release contracts
.github/workflows/ci.yml             Python 3.12 test and 80% coverage gate
~~~

## Methodological boundaries

Atlas intentionally does not:

- forecast outages, wholesale prices, company earnings, or data-centre load;
- make investment or portfolio decisions;
- claim causal relationships from descriptive correlations;
- estimate private data-centre demand from public filings;
- silently fill missing regional data or treat missingness as zero pressure;
- create a global ranking from incomparable regional definitions;
- add a new dataset or region without a separately approved v1.2 scope.

For the full research thesis, evidence standard, source plan, and non-goals,
see [docs/PROJECT_SPEC.md](docs/PROJECT_SPEC.md). For the finite delivery
history, see [docs/REBUILD_PLAN.md](docs/REBUILD_PLAN.md).
