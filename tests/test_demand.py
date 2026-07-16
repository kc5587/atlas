from datetime import date, datetime, timedelta, timezone

import pytest

from atlas.analysis.demand import DemandPressureConfig, demand_pressure
from atlas.evidence import EvidenceKind, Observation, SourceRef


SOURCE = SourceRef(
    id="fixture:eia",
    url="https://www.eia.gov/electricity/gridmonitor/about",
    publisher="U.S. Energy Information Administration",
)


def observation(day: date, value: float, index: int) -> Observation:
    timestamp = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    return Observation(
        id=f"demand-{index}",
        metric_id="demand",
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


def test_demand_pressure_is_derived_from_a_trailing_baseline() -> None:
    start = date(2026, 6, 1)
    observations = tuple(
        observation(start + timedelta(days=index), 100.0, index)
        for index in range(7)
    ) + (observation(start + timedelta(days=7), 120.0, 7),)

    signal = demand_pressure(
        observations,
        as_of=start + timedelta(days=7),
        config=DemandPressureConfig(baseline_days=7, full_pressure_growth_pct=20.0),
    )

    assert signal.value == pytest.approx(100.0)
    assert signal.confidence == pytest.approx(1.0)
    assert signal.observation_ids[-1] == "demand-7"


def test_short_history_reduces_confidence_but_not_pressure() -> None:
    start = date(2026, 6, 1)
    observations = (
        observation(start, 100.0, 0),
        observation(start + timedelta(days=1), 110.0, 1),
    )

    signal = demand_pressure(
        observations,
        as_of=start + timedelta(days=1),
        config=DemandPressureConfig(baseline_days=7, min_baseline_days=1),
    )

    assert signal.value == pytest.approx(50.0)
    assert signal.confidence == pytest.approx(1 / 7)


def test_missing_current_day_fails_explicitly() -> None:
    with pytest.raises(ValueError, match="no demand observation"):
        demand_pressure(
            (observation(date(2026, 6, 1), 100.0, 0),),
            as_of=date(2026, 6, 2),
        )
