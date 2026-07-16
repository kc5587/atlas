from datetime import date, datetime, timedelta, timezone

import pytest

from atlas.analysis.price import PriceStressConfig, price_stress
from atlas.evidence import EvidenceKind, Observation, SourceRef


SOURCE = SourceRef(
    id="fixture:eia",
    url="https://www.eia.gov/electricity/wholesale/",
    publisher="U.S. Energy Information Administration",
)


def observation(day: date, value: float, index: int) -> Observation:
    timestamp = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    return Observation(
        id=f"price-{index}",
        metric_id="wholesale_price",
        entity_id="ERCO",
        period_start=timestamp,
        period_end=timestamp,
        value=value,
        unit="USD_per_MWh",
        source=SOURCE,
        retrieved_at=day,
        vintage=day.isoformat(),
        kind=EvidenceKind.OBSERVED,
    )


def test_price_stress_is_a_historical_percentile() -> None:
    start = date(2026, 6, 1)
    history = tuple(
        observation(start + timedelta(days=index), value, index)
        for index, value in enumerate((10.0, 20.0, 30.0, 40.0))
    )
    current = observation(start + timedelta(days=4), 35.0, 4)

    signal = price_stress(
        history + (current,),
        as_of=start + timedelta(days=4),
        config=PriceStressConfig(baseline_days=4, min_baseline_days=4),
    )

    assert signal.value == pytest.approx(75.0)
    assert signal.confidence == pytest.approx(1.0)


def test_price_stress_requires_history() -> None:
    with pytest.raises(ValueError, match="not enough price history"):
        price_stress(
            (observation(date(2026, 6, 1), 25.0, 0),),
            as_of=date(2026, 6, 1),
        )
