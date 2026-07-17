from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from atlas.evidence import EvidenceKind, Observation, SourceRef
from atlas.report_pipeline import (
    build_report_from_observations,
    build_report_from_snapshot,
)
from atlas.snapshot import write_observations


SOURCE = SourceRef(
    id="fixture:test",
    url="https://example.com/source",
    publisher="Test Publisher",
)


def observation(
    metric_id: str,
    day: date,
    value: float,
    index: int,
    entity_id: str = "ERCO",
    hour: int = 0,
) -> Observation:
    timestamp = datetime(
        day.year, day.month, day.day, hour, tzinfo=timezone.utc
    )
    return Observation(
        id=f"{metric_id}-{index}",
        metric_id=metric_id,
        entity_id=entity_id,
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


def test_snapshot_report_uses_latest_complete_common_day(tmp_path: Path) -> None:
    start = date(2026, 6, 1)
    observations = []
    for day_index in range(8):
        day = start + timedelta(days=day_index)
        for hour in range(24):
            observations.extend(
                (
                    observation("demand", day, 100.0, len(observations), hour=hour),
                    observation(
                        "net_generation",
                        day,
                        120.0,
                        len(observations) + 1,
                        hour=hour,
                    ),
                )
            )
    partial_day = start + timedelta(days=8)
    observations.extend(
        (
            observation("demand", partial_day, 80.0, len(observations)),
            observation(
                "net_generation", partial_day, 100.0, len(observations) + 1
            ),
        )
    )
    snapshot = tmp_path / "snapshot"
    write_observations(snapshot / "curated/eia_observations.json", tuple(observations))
    write_observations(snapshot / "curated/sec_capex.json", ())
    (snapshot / "manifest.json").write_text(
        '{"generated_at": "2026-07-03T00:00:00+00:00"}', encoding="utf-8"
    )

    report = build_report_from_snapshot(snapshot, ("ERCO",), {})

    assert report["regions"][0]["as_of"] == "2026-06-08"


def test_snapshot_report_rejects_snapshots_without_complete_common_day(
    tmp_path: Path,
) -> None:
    snapshot = tmp_path / "snapshot"
    write_observations(
        snapshot / "curated/eia_observations.json",
        (observation("demand", date(2026, 6, 1), 100.0, 0),),
    )
    write_observations(snapshot / "curated/sec_capex.json", ())
    (snapshot / "manifest.json").write_text(
        '{"generated_at": "2026-07-03T00:00:00+00:00"}', encoding="utf-8"
    )

    with pytest.raises(ValueError, match="complete common operating day"):
        build_report_from_snapshot(snapshot, ("ERCO",), {})
