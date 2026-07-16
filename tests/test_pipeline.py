from datetime import date, datetime, timedelta, timezone

import pytest

from atlas.analysis.pipeline import score_from_observations
from atlas.analysis.demand import DemandPressureConfig
from atlas.analysis.price import PriceStressConfig
from atlas.analysis.supply import SupplyTightnessConfig
from atlas.evidence import EvidenceKind, Observation, SourceRef


SOURCE = SourceRef(
    id="fixture:eia",
    url="https://www.eia.gov/electricity/gridmonitor/about",
    publisher="U.S. Energy Information Administration",
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
        unit="MW" if metric_id != "wholesale_price" else "USD_per_MWh",
        source=SOURCE,
        retrieved_at=day,
        vintage=day.isoformat(),
        kind=EvidenceKind.OBSERVED,
    )


def test_pipeline_composes_raw_signals_and_preserves_missing_execution_data() -> None:
    start = date(2026, 6, 1)
    demand = tuple(
        observation("demand", start + timedelta(days=index), 100.0, index)
        for index in range(7)
    ) + (observation("demand", start + timedelta(days=7), 110.0, 7),)
    generation = tuple(
        observation("net_generation", start + timedelta(days=index), 105.0, index)
        for index in range(7, 8)
    )
    prices = tuple(
        observation("wholesale_price", start + timedelta(days=index), value, index)
        for index, value in enumerate(
            (10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0)
        )
    )

    score = score_from_observations(
        region_id="ercot",
        as_of=start + timedelta(days=7),
        demand=demand,
        generation=generation,
        prices=prices,
        demand_config=DemandPressureConfig(baseline_days=7),
        supply_config=SupplyTightnessConfig(expected_hours_per_day=1),
        price_config=PriceStressConfig(baseline_days=7, min_baseline_days=7),
    )

    assert score.pressure == pytest.approx(79.4117647059)
    assert score.missing_components == ("execution_friction",)
    assert score.confidence < 1.0
