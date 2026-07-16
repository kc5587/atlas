from datetime import date

from atlas.analysis.insights import load_signal_fixture, rank_regions
from atlas.reporting import build_export


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
