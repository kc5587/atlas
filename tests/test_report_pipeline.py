from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from atlas.evidence import EvidenceKind, Observation, SourceRef
from atlas.report_pipeline import build_report_from_observations


SOURCE = SourceRef(
    id="fixture:test",
    url="https://example.com/source",
    publisher="Test Publisher",
)


def observation(metric_id: str, day: date, value: float, index: int) -> Observation:
    timestamp = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    return Observation(
        id=f"{metric_id}-{index}",
        metric_id=metric_id,
        entity_id="ERCO",
        period_start=timestamp,
        period_end=timestamp,
        value=value,
        unit="MW",
        source=SOURCE,
        retrieved_at=day,
        vintage=day.isoformat(),
        kind=EvidenceKind.OBSERVED,
    )


def test_report_pipeline_scores_regions_and_marks_unavailable_regions() -> None:
    start = date(2026, 6, 1)
    demand = tuple(
        observation("demand", start + timedelta(days=index), 100.0, index)
        for index in range(7)
    ) + (observation("demand", start + timedelta(days=7), 110.0, 7),)
    generation = (observation("net_generation", start + timedelta(days=7), 105.0, 7),)
    prices = tuple(
        observation("wholesale_price", start + timedelta(days=index), value, index)
        for index, value in enumerate((10, 20, 30, 40, 50, 60, 70, 80))
    )

    report = build_report_from_observations(
        observations=demand + generation + prices,
        capex_observations=(),
        region_ids=("ERCO", "PJM"),
        company_labels={},
        as_of=start + timedelta(days=7),
        generated_at=date(2026, 7, 3),
    )

    assert report["regions"][0]["region_id"] == "ERCO"
    assert report["regions"][0]["confidence"] == 0.1
    assert report["unavailable_regions"][0]["region_id"] == "PJM"
