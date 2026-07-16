"""Convert Berkeley Lab's Queued Up workbook to a regional benchmark JSON."""

import argparse
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from atlas.analysis.interconnection import QueueProject, aggregate_queue_projects


REGION_MAP = {
    "ERCOT": "ERCO",
    "PJM": "PJM",
    "MISO": "MISO",
    "CAISO": "CISO",
    "SPP": "SWPP",
    "NYISO": "NYIS",
    "ISO-NE": "ISNE",
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    frame = pd.read_excel(args.input, sheet_name="03. Complete Queue Data", header=1)
    projects = tuple(_project(row) for _, row in frame.iterrows() if _usable(row))
    benchmark = aggregate_queue_projects(projects)
    payload = {
        "schema_version": 1,
        "source": "https://emp.lbl.gov/publications/queued-2025-edition-characteristics",
        "dataset_as_of": "2024-12-31",
        "project_count_mapped": len(projects),
        "benchmark": list(benchmark),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"{args.output} projects={len(projects)} regions={len(benchmark)}")


def _usable(row: pd.Series) -> bool:
    raw_request = row.get("q_date")
    return (
        str(row.get("region", "")) in REGION_MAP
        and pd.notna(raw_request)
        and _excel_date(raw_request).year >= 1990
    )


def _project(row: pd.Series) -> QueueProject:
    region = REGION_MAP[str(row["region"])]
    request_date = _excel_date(row["q_date"])
    raw_operation = row.get("on_date")
    operation_date = (
        _excel_date(raw_operation)
        if pd.notna(raw_operation) and float(raw_operation) > 1000
        else None
    )
    capacity = abs(sum(
        float(row[column]) for column in ("mw1", "mw2", "mw3") if pd.notna(row.get(column))
    ))
    return QueueProject(
        region_id=region,
        status=str(row["q_status"]).strip().lower(),
        request_date=request_date,
        operation_date=operation_date,
        capacity_mw=capacity,
    )


def _excel_date(value: object) -> date:
    return (datetime(1899, 12, 30) + timedelta(days=float(value))).date()


if __name__ == "__main__":
    main()
