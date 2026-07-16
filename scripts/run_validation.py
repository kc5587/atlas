"""Run the finite v1.1 validation bundle and publish report artifacts."""

import argparse
import json
from datetime import date
from pathlib import Path

from atlas.analysis.evaluation import (
    EvaluationConfig,
    build_score_history,
    monthly_as_of_dates,
    run_backtest,
    run_sensitivity,
)
from atlas.analysis.validation import validate_observations
from atlas.refresh import DEFAULT_COMPANIES, DEFAULT_REGIONS
from atlas.report_pipeline import build_report_from_snapshot
from atlas.reporting import render_report_html
from atlas.snapshot import read_observations, write_json_document, write_text_document


PRICE_REGIONS = ("PJM", "MISO", "CISO", "SWPP", "NYIS", "ISNE")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--start", type=date.fromisoformat, default=date(2022, 1, 1))
    parser.add_argument("--end", type=date.fromisoformat, default=date(2025, 12, 31))
    parser.add_argument("--benchmark-json", type=Path, default=None)
    args = parser.parse_args()
    observations = read_observations(
        args.snapshot_dir / "curated/eia_observations.json"
    )
    as_of_dates = monthly_as_of_dates(observations, args.start, args.end)
    config = EvaluationConfig(minimum_history_days=365)
    validation = validate_observations(
        observations,
        DEFAULT_REGIONS,
        args.start,
        args.end,
        required_price_regions=PRICE_REGIONS,
    )
    backtest = run_backtest(
        observations, DEFAULT_REGIONS, as_of_dates, (30, 90), config
    )
    sensitivity = run_sensitivity(
        observations,
        DEFAULT_REGIONS,
        max(as_of_dates),
    ) if as_of_dates else {"schema_version": 1, "region_summary": []}
    history = build_score_history(observations, DEFAULT_REGIONS, as_of_dates, config)
    benchmark = _load_benchmark(args.benchmark_json)
    analysis = {
        "validation": validation,
        "backtest": backtest,
        "sensitivity": sensitivity,
        "history": history,
        "interconnection_benchmark": benchmark,
    }
    labels = {
        f"cik:{cik.zfill(10)}": company for company, cik in DEFAULT_COMPANIES.items()
    }
    report = build_report_from_snapshot(
        args.snapshot_dir, DEFAULT_REGIONS, labels, analysis=analysis
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json_document(args.output_dir / "validation.json", validation)
    write_json_document(args.output_dir / "backtest.json", backtest)
    write_json_document(args.output_dir / "sensitivity.json", sensitivity)
    write_json_document(args.output_dir / "report.json", report)
    write_text_document(args.output_dir / "report.html", render_report_html(report))
    print(args.output_dir / "report.html")


def _load_benchmark(path: Path | None) -> dict[str, object]:
    if path is None:
        return {"schema_version": 1, "regions": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return {
        "schema_version": payload.get("schema_version", 1),
        "dataset_as_of": payload.get("dataset_as_of"),
        "source": payload.get("source"),
        "regions": payload.get("benchmark", []),
    }


if __name__ == "__main__":
    main()
