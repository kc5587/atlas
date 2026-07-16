# Atlas v1.1 Validation Release Specification

## Destination

Atlas v1.1 converts the v1 monitor from a well-tested foundation into a
historically validated research release. It will answer whether the regional
pressure signal is stable, whether it is associated with subsequent observed
pressure, and whether electricity-market and interconnection evidence support
the interpretation.

This is a finite release. When the acceptance criteria below pass, v1.1 is
finished. New regions, predictive models, automated alerts, and new datasets
become v1.2 work.

## Fixed evaluation design

- Historical window: 2022-01-01 through 2025-12-31, subject to source
  availability and a recorded as-of date.
- Evaluation cadence: monthly as-of dates after 365 days of history.
- Forward horizons: 30 and 90 days.
- Regions: the existing seven balancing authorities only.
- Price coverage: EIA/ICE hubs for five regions, a clearly labelled NYISO
  zonal-LBMP aggregate for NYIS, and an explicit ERCO source limitation. The
  EIA/ICE export is sparse for MISO, so minimum price coverage is 90 observed
  days rather than a fabricated daily fill.
- Benchmark: Berkeley Lab's Queued Up 2025 project-level interconnection
  dataset, aggregated to the seven regions where the source provides a usable
  mapping.

## Work included

1. A sustained EIA-930 bulk historical refresh for the fixed window, plus a
   paginated API client for incremental refreshes, with row-count and
   date-range checks.
2. Multi-year EIA wholesale files plus NYISO monthly archived LBMP files,
   normalised into the existing observation contract.
3. A transparent hindcast evaluation: score at month-end using information
   available then, compare with the next 30/90-day realised component pressure,
   and report rank correlation and top-versus-bottom spreads.
4. Sensitivity analysis over demand and price lookbacks and three fixed weight
   sets, reporting score ranges and rank stability.
5. A visual report with time-series sparklines, score/component history, and
   validation summary tables. No interactive web application is required.
6. A benchmark panel comparing Atlas pressure with queued capacity, active
   project counts, withdrawal rates, and time-to-commercial-operation evidence.

## Definition of done

- A live validation run completes for the fixed window or fails loudly with a
  source-specific diagnosis; no partial result is labelled complete.
- All seven regions have either price observations or a documented source/data
  limitation. NYIS must use the NYISO adapter rather than remain silently
  unavailable.
- Historical ingestion proves pagination, monotonic coverage, structural
  duplicate handling, and expected minimum observation counts. Multiple
  same-day wholesale hubs are retained as separate price observations.
- Backtest outputs contain no look-ahead: each signal uses observations through
  its as-of date, while outcomes use only the subsequent window.
- Sensitivity output reports score range and rank stability for every region.
- The report shows the score history, component history, validation results,
  and interconnection benchmark with source links and caveats.
- Deterministic fixtures cover every new transform and the full suite remains
  at least 80% covered.
- The live validation artifact is stored outside Git; credentials and raw data
  remain ignored.

## Explicit non-goals

- No outage or price forecasting claim.
- No machine learning, trading signal, causal estimate, or significance claim
  beyond descriptive validation statistics.
- No attempt to estimate private data-centre load from company filings.
- No national/global ranking and no second benchmark dataset in this release.

## Stopping rule

After the fixed historical run, validation, sensitivity analysis, visual report,
and benchmark pass the definition of done, publish v1.1 and stop. Anything
outside this document requires a separately approved v1.2 scope.
