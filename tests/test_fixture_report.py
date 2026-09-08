import json
from pathlib import Path

from scripts.generate_fixture_report import write_fixture_report


def test_fixture_report_is_deterministic_and_clearly_labelled(
    tmp_path: Path,
) -> None:
    report_path = write_fixture_report(
        Path("data/fixtures/regional_signals.json"), tmp_path
    )

    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    html = report_path.read_text(encoding="utf-8")
    preview = (tmp_path / "report-preview.svg").read_text(encoding="utf-8")

    assert report["dataset_status"] == "illustrative_fixture"
    assert report["generated_at"] == "2026-07-02"
    assert report["regions"][0]["region_id"] == "ercot"
    assert "Illustrative Fixture" in html
    assert "Illustrative fixture data" in preview
    assert "ERCOT" in preview
    assert "73.9" in preview


def test_committed_example_matches_the_fixture_generator(tmp_path: Path) -> None:
    write_fixture_report(Path("data/fixtures/regional_signals.json"), tmp_path)

    for filename in ("report.json", "report.html", "report-preview.svg"):
        generated = (tmp_path / filename).read_text(encoding="utf-8")
        committed = (Path("examples") / filename).read_text(encoding="utf-8")
        assert generated == committed
