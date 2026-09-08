"""Generate a deterministic, sanitised report from illustrative signals."""

import argparse
from pathlib import Path
from xml.sax.saxutils import escape

from atlas.analysis.insights import load_signal_fixture, rank_regions
from atlas.reporting import build_export, render_report_html
from atlas.scoring import BottleneckScore
from atlas.snapshot import write_json_document, write_text_document

DEFAULT_FIXTURE = Path("data/fixtures/regional_signals.json")


def write_fixture_report(fixture: Path, output_dir: Path) -> Path:
    """Write a public example report without live credentials or source data."""

    snapshots = load_signal_fixture(fixture)
    scores = rank_regions(snapshots)
    generated_at = max(snapshot.as_of for snapshot in snapshots)
    report = build_export(
        scores=scores,
        generated_at=generated_at,
        dataset_status="illustrative_fixture",
    )
    write_json_document(output_dir / "report.json", report)
    report_path = output_dir / "report.html"
    write_text_document(report_path, render_report_html(report))
    write_text_document(output_dir / "report-preview.svg", _render_preview(scores))
    return report_path


def _render_preview(scores: tuple[BottleneckScore, ...]) -> str:
    """Render a compact GitHub-safe preview of the illustrative ranking."""

    rows = []
    for index, score in enumerate(scores):
        y = 170 + index * 90
        width = round(score.pressure * 7.2, 1)
        label = escape(score.region_id.upper())
        rows.append(
            f'<text x="70" y="{y}" class="region">{label}</text>'
            f'<rect x="210" y="{y - 28}" width="720" height="34" rx="8" '
            f'class="track"/><rect x="210" y="{y - 28}" width="{width}" '
            f'height="34" rx="8" class="bar"/>'
            f'<text x="960" y="{y}" class="score">{score.pressure:.1f}</text>'
        )
    height = 220 + max(len(scores) - 1, 0) * 90
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="1100" height="{height}" viewBox="0 0 1100 {height}">
<style>
  .bg {{ fill: #0b1020; }} .title {{ fill: #f8fafc; font: 700 34px Arial, sans-serif; }}
  .sub {{ fill: #94a3b8; font: 18px Arial, sans-serif; }}
  .region, .score {{ fill: #e2e8f0; font: 700 22px Arial, sans-serif; }}
  .track {{ fill: #1e293b; }} .bar {{ fill: #38bdf8; }}
</style>
<rect width="1100" height="{height}" rx="18" class="bg"/>
<text x="70" y="62" class="title">Atlas regional pressure preview</text>
<text x="70" y="98" class="sub">Illustrative fixture data · deterministic offline example · not a forecast</text>
{"".join(rows)}
</svg>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(write_fixture_report(args.fixture, args.output_dir))


if __name__ == "__main__":
    main()
