# Atlas: AI Infrastructure Bottleneck Monitor

Atlas is a provenance-first research product for answering:

> Where are the physical and financial constraints that can prevent AI
> infrastructure from scaling as expected?

It combines electricity-system data, company disclosures, public energy
statistics, and scenario research into regional pressure indicators and
evidence-backed research notes. It is descriptive and exploratory; it is not a
trading system, a price forecaster, or investment advice.

## Current status

The finite v1.1 validation release is complete. The repository contains the
typed analytical core, sustained EIA-930 bulk refresh, EIA/ICE and NYISO price
adapters, checksummed snapshots, lookahead-safe backtesting, sensitivity
analysis, interconnection benchmarking, static visual report, deterministic
fixtures, and CI gates.

See [docs/REBUILD_PLAN.md](docs/REBUILD_PLAN.md) for the delivery plan and
[docs/PROJECT_SPEC.md](docs/PROJECT_SPEC.md) for the research design.

The fixed destination for this rebuild is [docs/V1_1_RELEASE_SPEC.md](docs/V1_1_RELEASE_SPEC.md).
It defines the v1.1 coverage, deliverables, acceptance criteria, and stopping
rule. Further product ideas belong in a separately scoped v1.2 effort.

## Commands

```bash
make setup
make test
make fixture-report   # offline reproducibility check
make refresh          # requires EIA_API_KEY and SEC_USER_AGENT
make report

# fixed historical release workflow (download sources separately)
PYTHONPATH=src python3 scripts/run_validation.py \
  --snapshot-dir /path/to/snapshot \
  --output-dir /path/to/report \
  --benchmark-json /path/to/atlas-queue-benchmark.json
```

The live refresh writes a checksummed snapshot under `data/snapshots/`; raw
responses and generated reports are intentionally ignored by Git.
