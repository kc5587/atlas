# Atlas v1 Release Specification

## Destination

Atlas v1 is a static, reproducible research report and data export answering:

> Which US electricity regions show the strongest evidence of near-term AI
> infrastructure pressure, what is driving that pressure, and how strong is the
> evidence?

When the acceptance criteria below pass, v1 is finished. New ideas become v1.1
issues rather than silently expanding this release.

## Intended user

The primary user is a research-minded analyst who wants to inspect AI
infrastructure claims against public electricity and company-disclosure data.
The product must be useful without trusting Atlas's composite score: every
ranking has raw components, source links, observation dates, and caveats.

## Fixed v1 coverage

### Electricity regions

Seven US balancing authorities with public operating data:

- ERCOT (`ERCO`)
- PJM (`PJM`)
- MISO (`MISO`)
- California ISO (`CISO`)
- Southwest Power Pool (`SWPP`)
- New York ISO (`NYIS`)
- ISO New England (`ISNE`)

The Southeast is excluded from v1 because it is not represented by one clean
balancing-authority unit in the initial data contract.

### Public companies

Eight companies with relevant public infrastructure disclosures:

- Microsoft, Amazon, Alphabet, Meta, Oracle
- Equinix, Digital Realty, Vertiv

Company coverage is limited to filed SEC data. Private-company estimates and
press-reported capex are excluded.

### Time and refresh

- Electricity history: 2019 to the latest available observation.
- Company history: latest five fiscal years available through EDGAR.
- Refresh cadence: weekly snapshot, with the exact retrieval time recorded.
- v1 is a snapshot product, not a real-time monitoring service.
- Wholesale price history is supplied through the official EIA spreadsheet
  export converted to CSV; `WHOLESALE_PRICE_CSV` is optional, and regions with
  no supported hub history are explicitly marked unavailable.

## Fixed analytical output

Each region receives three automated, descriptive components:

1. **Demand pressure** — current daily peak versus a trailing 28-day baseline.
2. **Supply tightness** — worst aligned-hour net-generation headroom proxy.
3. **Price stress** — current daily peak wholesale price percentile versus a
   trailing 365-day baseline.

The composite is a 0–100 weighted average of available components. Missing data
is never converted to zero; it lowers confidence and appears in the output.

Capital commitment is a separate company panel showing filed capex and change
over time. Execution friction is a separate evidence panel containing
authoritative scenario and project-status references; it is not included in the
v1 composite unless a comparable machine-readable source is established.

## Fixed v1 deliverables

- A clean-checkout command sequence: `make setup`, `make test`, `make refresh`,
  `make report`.
- A versioned JSON export consumed by the report/UI.
- A static report with one overview table, seven regional detail cards, and a
  company capex table.
- Source-linked methodology notes explaining every transform and limitation.
- A refresh manifest containing source URLs, retrieval times, row counts,
  checksums, and schema version.
- Deterministic fixtures and tests that run without network access.

## Definition of done

V1 is releasable only when:

- All seven regions appear in the output or are explicitly marked unavailable.
- Every available component includes its value, weight, confidence, and input
  observation IDs.
- Every company capex point includes filing vintage and accession-linked
  provenance.
- The report visibly distinguishes observed, estimated, and inferred evidence.
- A refresh failure cannot silently publish stale data as current data.
- A clean checkout reproduces the fixture report and passes the full test suite.
- Coverage remains at least 80% for the Python package.
- No credentials, raw caches, or generated database files enter Git.

## Explicitly deferred to v1.1+

- Global regional coverage.
- Real-time alerts, outage prediction, or shortage probabilities.
- Forecasting, machine learning, and portfolio or trading recommendations.
- News scraping, sentiment analysis, and unreviewed private-company estimates.
- Automated execution-friction scoring.
- User accounts, APIs, mobile polish, and multi-user infrastructure.
- Advanced network maps beyond the fixed region/company views.

## Stopping rule

After the definition of done passes, we publish v1, document known gaps, and
stop feature work. Any additional feature must have a separate v1.1 scope,
success metric, and explicit decision that it is worth extending the product.
