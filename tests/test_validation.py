from datetime import date, datetime, timedelta, timezone

from atlas.analysis.validation import validate_observations
from atlas.evidence import EvidenceKind, Observation, SourceRef


SOURCE = SourceRef("test", "https://example.com", "Test")


def _observation(metric: str, region: str, day: date, index: int) -> Observation:
    timestamp = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    return Observation(
        id=f"{metric}:{region}:{index}",
        metric_id=metric,
        entity_id=region,
        period_start=timestamp,
        period_end=timestamp,
        value=1.0,
        unit="MW",
        source=SOURCE,
        retrieved_at=day,
        vintage=day.isoformat(),
        kind=EvidenceKind.OBSERVED,
    )


def test_validation_allows_documented_missing_ercot_price() -> None:
    start = date(2022, 1, 1)
    observations = tuple(
        item
        for index in range(365)
        for metric in ("demand", "net_generation")
        for item in (_observation(metric, "ERCO", start + timedelta(days=index), index),)
    )
    result = validate_observations(
        observations,
        ("ERCO",),
        start,
        date(2022, 12, 31),
        required_price_regions=(),
    )

    assert result["passed"] is True
    assert result["coverage"][0]["metric_days"]["wholesale_price"] == 0
