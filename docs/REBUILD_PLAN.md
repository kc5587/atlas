# Atlas Rebuild Plan

## Product goal

Build a reproducible monitor that helps a researcher distinguish AI
infrastructure demand from infrastructure that can actually be delivered. The
product must connect each conclusion to source observations, timestamps,
vintages, units, transformations, and uncertainty.

## Delivery sequence

1. **Research contract** — define the thesis, regions, metrics, evidence rules,
   and explicit non-goals.
2. **Domain core** — immutable graph, observations, provenance, derived metrics,
   and validation tests.
3. **First insight slice** — fixture-backed regional pressure scoring with
   component attribution, missing-data handling, and confidence labels.
4. **Data layer** — isolated adapters for EIA, SEC EDGAR, FRED, and published
   scenario datasets; raw responses are cached and checksummed.
5. **Analytical layer** — time-series normalisation, seasonal baselines,
   company capex extraction, regional aggregation, sensitivity analysis, and
   backtests of signal stability.
6. **Research layer** — generated evidence tables and human-readable insight
   cards that explain what changed, why it matters, and what could falsify it.
7. **Web layer** — static, inspectable map and dashboard with source drill-down,
   not a black-box scorecard.
8. **Operations** — clean-checkout setup, refresh manifests, CI, data-quality
   reports, and documented release snapshots.

## Quality gates

- Every metric has a definition, unit, frequency, source, vintage, and owner.
- Derived values preserve their input IDs and transformation version.
- Unit tests use deterministic fixtures; live APIs are never required for tests.
- Scores expose components and confidence rather than presenting false precision.
- Missing observations reduce confidence or suppress a conclusion; they never
  silently become zero.
- Historical revisions are retained as vintages where the source allows it.
- Research claims include a counter-signal or caveat.
- Generated datasets are reproducible from a refresh manifest and are not
  committed by default.

## Current checkpoint

The graph model and validation tests are complete. The next implementation
slice adds typed observations and a transparent regional bottleneck score.
