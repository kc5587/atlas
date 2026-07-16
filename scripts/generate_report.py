"""Generate the v1 JSON and static HTML report from a snapshot."""

import argparse
from pathlib import Path

from atlas.refresh import DEFAULT_COMPANIES, DEFAULT_REGIONS
from atlas.report_pipeline import build_report_from_snapshot
from atlas.reporting import render_report_html
from atlas.snapshot import write_json_document, write_text_document


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-dir", type=Path, default=None)
    parser.add_argument("--snapshots-root", type=Path, default=Path("data/snapshots"))
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()
    snapshot_dir = args.snapshot_dir or _latest_snapshot(args.snapshots_root)
    output_dir = args.output_dir or snapshot_dir
    labels = {
        f"cik:{cik.zfill(10)}": company for company, cik in DEFAULT_COMPANIES.items()
    }
    report = build_report_from_snapshot(snapshot_dir, DEFAULT_REGIONS, labels)
    write_json_document(output_dir / "report.json", report)
    write_text_document(output_dir / "report.html", render_report_html(report))
    print(output_dir / "report.html")


def _latest_snapshot(root: Path) -> Path:
    candidates = tuple(
        path
        for path in root.iterdir()
        if path.is_dir() and (path / "manifest.json").exists()
    )
    if not candidates:
        raise SystemExit(f"no complete snapshots found under {root}")
    return max(candidates, key=lambda path: path.name)


if __name__ == "__main__":
    main()
