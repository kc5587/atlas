"""Composition of raw observations into a regional pressure score."""

from datetime import date

from atlas.analysis.demand import DemandPressureConfig, demand_pressure
from atlas.analysis.price import PriceStressConfig, price_stress
from atlas.analysis.supply import SupplyTightnessConfig, supply_tightness
from atlas.evidence import Observation
from atlas.scoring import BottleneckScore, ComponentSignal, score_region


def score_from_observations(
    region_id: str,
    as_of: date,
    demand: tuple[Observation, ...],
    generation: tuple[Observation, ...],
    prices: tuple[Observation, ...],
    demand_config: DemandPressureConfig = DemandPressureConfig(),
    supply_config: SupplyTightnessConfig = SupplyTightnessConfig(),
    price_config: PriceStressConfig = PriceStressConfig(
        baseline_days=365, min_baseline_days=4
    ),
) -> BottleneckScore:
    """Build a score from raw observations without fabricating execution data."""

    signals: tuple[ComponentSignal, ...] = (
        demand_pressure(demand, as_of, demand_config),
        supply_tightness(demand, generation, as_of, supply_config),
        price_stress(prices, as_of, price_config),
        ComponentSignal(
            name="execution_friction",
            value=None,
            confidence=0.0,
            observation_ids=(),
        ),
    )
    return score_region(region_id, as_of, signals)
