# Atlas Project Specification

## 1. Research thesis

AI infrastructure is moving from a software narrative into a physical
deployment problem. The useful question is no longer only which companies sit
in the value chain; it is whether power, grid access, equipment, capital, and
operational efficiency can keep pace with announced demand.

The IEA reported that data-centre electricity use grew 17% in 2025 and that
AI-focused demand grew faster, while grid connections and equipment supply were
already creating bottlenecks. Its 2025 base case projected global data-centre
electricity demand to reach about 945 TWh by 2030. The 2025 LBNL update estimated
that US data centres could reach 11.8% of national electricity use by 2030, with
a scenario range of 9.5% to 15.3%.

These are scenarios and estimates, not observations. Atlas will keep that
distinction explicit.

## 2. Research questions

1. Which regions show the strongest evidence of near-term electricity pressure?
2. Is pressure driven by demand growth, supply tightness, price stress, or
   execution friction?
3. Are hyperscaler capex commitments accelerating faster than local power and
   grid capacity indicators?
4. Where are efficiency gains offsetting demand growth, and where are they not?
5. Which conclusions survive reasonable changes to lookback windows, weights,
   and missing-data assumptions?
6. What evidence would falsify the current interpretation?

## 3. MVP coverage

The first live release will focus on US electric-system regions represented by
public balancing-authority data: ERCOT, PJM, MISO, CAISO, SPP, NYISO, ISO-NE,
and the Southeast. Global context will be represented by IEA scenarios until
comparable regional observations exist.

Initial company coverage will be limited to major public infrastructure buyers
with filings available through EDGAR. Private-company estimates and press
reports are out of scope for the first release.

## 4. Evidence model

An observation is the smallest auditable fact:

```text
metric_id, entity_id, period_start, period_end, value, unit,
source_id, source_url, retrieved_at, source_vintage, quality_flags
```

Every derived metric additionally stores:

```text
formula_id, input_observation_ids, transformation_version, assumptions
```

The product distinguishes:

- **Observed** — directly reported by a source.
- **Estimated** — produced by a published methodology or explicit model.
- **Inferred** — an Atlas interpretation, always shown with its inputs.

## 5. Metrics

### Demand pressure

- Current demand versus a seasonal trailing baseline.
- Growth rate over 30, 90, and 365 days where frequency permits.
- Peak-demand anomaly and load-factor change.

### Supply tightness

- Net generation and imports relative to demand.
- Generation mix and dispatchable capacity context.
- Peak-period headroom proxy, clearly labelled as a proxy rather than a formal
  reserve margin.

### Price stress

- Wholesale price range and high-price frequency where available.
- Industrial retail electricity price and change over time.
- Natural-gas price context for regions with gas-backed marginal generation.

### Execution friction

- Publicly documented project, queue, or grid-connection status where available.
- Equipment and connection constraints from authoritative reports.
- Confidence is lower when a region has only scenario-level evidence.

### Capital commitment

- Company capex and property/equipment growth from filed financial statements.
- Data-centre and AI infrastructure mentions from filing text as a tagged,
  reviewable evidence stream—not as an opaque NLP score.

## 6. Index design

The regional bottleneck pressure index is a 0–100 descriptive composite. It is
not a probability of failure and not a price signal.

The first version will expose four components:

```text
pressure = demand_pressure + supply_tightness + price_stress + execution_friction
```

Each component is normalised against the region’s own historical distribution,
not ranked blindly across incomparable regions. The report will show the raw
values, percentile transforms, weights, missingness, and sensitivity range.

Confidence is based on source quality, recency, coverage, and agreement across
indicators. Missing data lowers confidence; it does not lower pressure.

## 7. Source plan

- [EIA Open Data API](https://www.eia.gov/opendata/index.php/api): hourly
  demand, generation, interchange, capability, and state-level electricity
  series.
- [EIA Grid Monitor](https://www.eia.gov/electricity/gridmonitor/about):
  balancing-authority definitions and historical operating data.
- [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces):
  company facts, submissions, and filing metadata.
- [FRED](https://fred.stlouisfed.org/): macro and energy-price context.
- [LBNL 2025 US Data Center Energy Usage Report](https://eta-publications.lbl.gov/publications/united-states-data-center-energy-2025):
  published demand scenarios and methodology context.
- [IEA Energy and AI](https://www.iea.org/reports/energy-and-ai/): global
  scenarios, technology context, and cross-checks.

## 8. Insight standard

An insight card must answer four questions:

1. **What changed?** Show the observation and comparison window.
2. **Why might it matter?** Connect it to the infrastructure thesis.
3. **How strong is the evidence?** Show sources, freshness, coverage, and
   component contribution.
4. **What could be wrong?** State the main alternative explanation or missing
   measurement.

Example: “ERCOT pressure rose because peak demand moved above its seasonal
baseline while dispatchable headroom proxy narrowed; confidence is medium
because interconnection execution data is incomplete. The result is sensitive
to the peak-window definition and should not be interpreted as a forecast of
shortage.”

## 9. Explicit non-goals

- No trading recommendations or automated portfolio decisions.
- No claim that a composite score predicts outages, earnings, or prices.
- No scraping of unverified news or analyst commentary in the core dataset.
- No pretending that company disclosure reveals private data-centre load.
- No global ranking until regional definitions and data quality are comparable.
