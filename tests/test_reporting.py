from datetime import date

from atlas.analysis.insights import load_signal_fixture, rank_regions
from atlas.reporting import build_export, render_report_html


def test_export_is_stable_and_contains_component_attribution() -> None:
    scores = rank_regions(load_signal_fixture("data/fixtures/regional_signals.json"))

    export = build_export(
        scores=scores,
        generated_at=date(2026, 7, 3),
        dataset_status="illustrative_fixture",
    )

    assert export["schema_version"] == 1
    assert export["generated_at"] == "2026-07-03"
    assert export["dataset_status"] == "illustrative_fixture"
    assert export["regions"][0]["region_id"] == "ercot"
    assert export["regions"][0]["components"][0]["name"] == "demand_pressure"
    assert export["regions"][-1]["missing_components"] == ["execution_friction"]


def test_report_renders_history_and_validation_sections() -> None:
    report = build_export(
        scores=rank_regions(load_signal_fixture("data/fixtures/regional_signals.json")),
        generated_at=date(2026, 7, 3),
        dataset_status="complete",
    )
    report["history"] = [{
        "region_id": "ERCO",
        "points": [
            {"as_of": "2022-01-01", "pressure": 20.0, "confidence": 0.5},
            {"as_of": "2022-02-01", "pressure": 30.0, "confidence": 0.6},
        ],
    }]
    report["validation"] = {"passed": True, "observation_count": 10}

    html = render_report_html(report)

    assert "Historical pressure path" in html
    assert "<svg" in html
    assert "Historical validation" in html
    assert "Not modeled: execution_friction" in html
    assert "Execution friction is" in html
    assert "evidence-only" in html
