"""Release-gate checks for a sustained historical Atlas dataset."""

from collections import Counter
from collections.abc import Iterable
from datetime import date, datetime

from atlas.evidence import Observation


def validate_observations(
    observations: tuple[Observation, ...],
    region_ids: tuple[str, ...],
    start: date,
    end: date,
    minimum_metric_days: int = 365,
    minimum_price_days: int = 90,
    required_price_regions: tuple[str, ...] | None = None,
) -> dict[str, object]:
    """Return deterministic coverage, duplicate, and date-range checks."""

    if start > end or minimum_metric_days <= 0 or minimum_price_days <= 0:
        raise ValueError("invalid validation window or minimum metric days")
    structural = tuple(item for item in observations if item.metric_id != "wholesale_price")
    duplicate_ids = _duplicates(item.id for item in structural)
    duplicate_keys = _duplicates(
        _observation_key(item) for item in structural
    )
    coverage = [_region_coverage(observations, region_id, start, end) for region_id in region_ids]
    violations: list[str] = []
    if duplicate_ids:
        violations.append("duplicate_observation_ids")
    if duplicate_keys:
        violations.append("duplicate_observation_keys")
    if required_price_regions is None:
        required_price_regions = region_ids
    for row in coverage:
        required_metrics = ("demand", "net_generation")
        if row["region_id"] in required_price_regions:
            required_metrics += ("wholesale_price",)
        for metric_id in required_metrics:
            threshold = (
                minimum_price_days
                if metric_id == "wholesale_price"
                else minimum_metric_days
            )
            if row["metric_days"][metric_id] < threshold:
                violations.append(f"{row['region_id']}:{metric_id}:insufficient_history")
    return {
        "schema_version": 1,
        "window": {"start": start.isoformat(), "end": end.isoformat()},
        "observation_count": len(observations),
        "duplicate_observation_ids": duplicate_ids,
        "duplicate_observation_keys": duplicate_keys,
        "coverage": coverage,
        "required_price_regions": list(required_price_regions),
        "passed": not violations,
        "violations": violations,
    }


def _region_coverage(
    observations: tuple[Observation, ...],
    region_id: str,
    start: date,
    end: date,
) -> dict[str, object]:
    metric_days = {
        metric_id: len(
            {
                _day(item)
                for item in observations
                if item.entity_id == region_id
                and item.metric_id == metric_id
                and start <= _day(item) <= end
            }
        )
        for metric_id in ("demand", "net_generation", "wholesale_price")
    }
    dates = tuple(
        _day(item)
        for item in observations
        if item.entity_id == region_id and start <= _day(item) <= end
    )
    return {
        "region_id": region_id,
        "first_date": min(dates).isoformat() if dates else None,
        "last_date": max(dates).isoformat() if dates else None,
        "metric_days": metric_days,
    }


def _observation_key(item: Observation) -> tuple[str, str, str]:
    return item.metric_id, item.entity_id, item.period_start.isoformat()


def _duplicates(values: Iterable[object]) -> list[object]:
    counts = Counter(values)
    return sorted(value for value, count in counts.items() if count > 1)


def _day(item: Observation) -> date:
    period = item.period_start
    return period.date() if isinstance(period, datetime) else period
