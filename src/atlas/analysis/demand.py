"""Transparent demand-pressure transforms for hourly observations."""

from dataclasses import dataclass
from datetime import date, datetime

from atlas.evidence import Observation
from atlas.scoring import ComponentSignal


@dataclass(frozen=True, slots=True)
class DemandPressureConfig:
    """Parameters for converting demand growth into a bounded pressure signal."""

    baseline_days: int = 28
    min_baseline_days: int = 7
    full_pressure_growth_pct: float = 20.0

    def __post_init__(self) -> None:
        if self.baseline_days <= 0 or self.min_baseline_days <= 0:
            raise ValueError("baseline days must be positive")
        if self.min_baseline_days > self.baseline_days:
            raise ValueError("min_baseline_days cannot exceed baseline_days")
        if self.full_pressure_growth_pct <= 0:
            raise ValueError("full_pressure_growth_pct must be positive")


def demand_pressure(
    observations: tuple[Observation, ...],
    as_of: date,
    config: DemandPressureConfig = DemandPressureConfig(),
) -> ComponentSignal:
    """Compare current daily peak demand with a trailing daily-peak baseline."""

    daily_peaks = _daily_peaks(observations)
    current = daily_peaks.get(as_of)
    if current is None:
        raise ValueError(f"no demand observation for {as_of.isoformat()}")
    baseline_values = tuple(
        value
        for day, value in sorted(daily_peaks.items())
        if day < as_of
    )[-config.baseline_days :]
    if len(baseline_values) < config.min_baseline_days:
        raise ValueError("not enough demand history for baseline")
    baseline = sum(baseline_values) / len(baseline_values)
    growth_pct = (current / baseline - 1.0) * 100.0
    pressure = _clamp(growth_pct / config.full_pressure_growth_pct * 100.0)
    confidence = min(1.0, len(baseline_values) / config.baseline_days)
    relevant_ids = tuple(
        observation.id for observation in observations if _observation_day(observation) <= as_of
    )
    return ComponentSignal(
        name="demand_pressure",
        value=pressure,
        confidence=confidence,
        observation_ids=relevant_ids,
    )


def _daily_peaks(observations: tuple[Observation, ...]) -> dict[date, float]:
    peaks: dict[date, float] = {}
    for observation in observations:
        if observation.metric_id != "demand":
            continue
        day = _observation_day(observation)
        peaks[day] = max(peaks.get(day, float("-inf")), observation.value)
    return peaks


def _observation_day(observation: Observation) -> date:
    period = observation.period_start
    return period.date() if isinstance(period, datetime) else period


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))
