"""Supply-tightness proxy derived from aligned EIA operating observations."""

from dataclasses import dataclass
from datetime import date, datetime

from atlas.evidence import Observation
from atlas.scoring import ComponentSignal


@dataclass(frozen=True, slots=True)
class SupplyTightnessConfig:
    """Parameters for a net-generation headroom proxy."""

    expected_hours_per_day: int = 24
    full_headroom_pct: float = 20.0

    def __post_init__(self) -> None:
        if self.expected_hours_per_day <= 0:
            raise ValueError("expected_hours_per_day must be positive")
        if self.full_headroom_pct <= 0:
            raise ValueError("full_headroom_pct must be positive")


def supply_tightness(
    demand: tuple[Observation, ...],
    generation: tuple[Observation, ...],
    as_of: date,
    config: SupplyTightnessConfig = SupplyTightnessConfig(),
) -> ComponentSignal:
    """Use the worst same-hour net-generation headroom as a tightness proxy."""

    demand_by_period = _observations_for_day(demand, "demand", as_of)
    generation_by_period = _observations_for_day(generation, "net_generation", as_of)
    overlap = frozenset(demand_by_period.keys() & generation_by_period.keys())
    if not overlap:
        raise ValueError("no aligned supply and demand observations")
    headroom = tuple(
        (generation_by_period[period].value - demand_by_period[period].value)
        / demand_by_period[period].value
        * 100.0
        for period in overlap
        if demand_by_period[period].value > 0
    )
    if not headroom:
        raise ValueError("demand must be positive for supply analysis")
    worst_headroom = min(headroom)
    tightness = _clamp(100.0 - worst_headroom / config.full_headroom_pct * 100.0)
    confidence = min(1.0, len(overlap) / config.expected_hours_per_day)
    ids = tuple(
        observation.id
        for observation in (*demand, *generation)
        if _observation_day(observation) == as_of
        and observation.period_start in overlap
    )
    return ComponentSignal(
        name="supply_tightness",
        value=tightness,
        confidence=confidence,
        observation_ids=ids,
    )


def _observations_for_day(
    observations: tuple[Observation, ...], metric_id: str, as_of: date
) -> dict[object, Observation]:
    return {
        observation.period_start: observation
        for observation in observations
        if observation.metric_id == metric_id and _observation_day(observation) == as_of
    }


def _observation_day(observation: Observation) -> date:
    period = observation.period_start
    return period.date() if isinstance(period, datetime) else period


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))
