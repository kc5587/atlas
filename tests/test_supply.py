from datetime import date, datetime, timezone

import pytest

from atlas.analysis.supply import SupplyTightnessConfig, supply_tightness
from atlas.evidence import EvidenceKind, Observation, SourceRef


SOURCE = SourceRef(
    id="fixture:eia",
    url="https://www.eia.gov/electricity/gridmonitor/about",
    publisher="U.S. Energy Information Administration",
)


def observation(metric_id: str, hour: int, value: float, index: int) -> Observation:
    timestamp = datetime(2026, 7, 2, hour, tzinfo=timezone.utc)
    return Observation(
        id=f"{metric_id}-{index}",
        metric_id=metric_id,
        entity_id="ERCO",
        period_start=timestamp,
        period_end=timestamp,
        value=value,
        unit="MW",
        source=SOURCE,
        retrieved_at=date(2026, 7, 3),
        vintage="2026-07-03",
        kind=EvidenceKind.OBSERVED,
    )


def test_supply_tightness_uses_worst_aligned_hour() -> None:
    demand = tuple(observation("demand", hour, 100.0, hour) for hour in range(4))
    generation = tuple(
        observation("net_generation", hour, value, hour)
        for hour, value in enumerate((115.0, 110.0, 105.0, 80.0))
    )

    signal = supply_tightness(
        demand,
        generation,
        as_of=date(2026, 7, 2),
        config=SupplyTightnessConfig(expected_hours_per_day=4),
    )

    assert signal.value == pytest.approx(100.0)
    assert signal.confidence == pytest.approx(1.0)
    assert signal.observation_ids[-1] == "net_generation-3"


def test_supply_tightness_reduces_confidence_for_partial_overlap() -> None:
    demand = tuple(observation("demand", hour, 100.0, hour) for hour in range(4))
    generation = (observation("net_generation", 0, 110.0, 0),)

    signal = supply_tightness(
        demand,
        generation,
        as_of=date(2026, 7, 2),
        config=SupplyTightnessConfig(expected_hours_per_day=4),
    )

    assert signal.value == pytest.approx(50.0)
    assert signal.confidence == pytest.approx(0.25)


def test_supply_tightness_requires_overlap() -> None:
    with pytest.raises(ValueError, match="no aligned supply and demand"):
        supply_tightness(
            (observation("demand", 0, 100.0, 0),),
            (),
            as_of=date(2026, 7, 2),
        )
