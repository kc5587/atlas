"""Historical-percentile price-stress transforms."""

from dataclasses import dataclass
from datetime import date, datetime

from atlas.evidence import Observation
from atlas.scoring import ComponentSignal


@dataclass(frozen=True, slots=True)
class PriceStressConfig:
    """Parameters for the historical daily-price percentile."""

    baseline_days: int = 365
    min_baseline_days: int = 30

    def __post_init__(self) -> None:
        if self.baseline_days <= 0 or self.min_baseline_days <= 0:
            raise ValueError("price history lengths must be positive")
        if self.min_baseline_days > self.baseline_days:
            raise ValueError("min_baseline_days cannot exceed baseline_days")


def price_stress(
    observations: tuple[Observation, ...],
    as_of: date,
    config: PriceStressConfig = PriceStressConfig(),
) -> ComponentSignal:
    """Rank the current daily peak price against a trailing history."""

    daily_peaks = _daily_peaks(observations)
    current = daily_peaks.get(as_of)
    if current is None:
        raise ValueError(f"no price observation for {as_of.isoformat()}")
    baseline = tuple(
        value for day, value in sorted(daily_peaks.items()) if day < as_of
    )[-config.baseline_days :]
    if len(baseline) < config.min_baseline_days:
        raise ValueError("not enough price history")
    percentile = sum(value <= current for value in baseline) / len(baseline) * 100.0
    confidence = min(1.0, len(baseline) / config.baseline_days)
    ids = tuple(
        observation.id
        for observation in observations
        if _observation_day(observation) <= as_of
    )
    return ComponentSignal(
        name="price_stress",
        value=percentile,
        confidence=confidence,
        observation_ids=ids,
    )


def _daily_peaks(observations: tuple[Observation, ...]) -> dict[date, float]:
    peaks: dict[date, float] = {}
    for observation in observations:
        if observation.metric_id != "wholesale_price":
            continue
        day = _observation_day(observation)
        peaks[day] = max(peaks.get(day, float("-inf")), observation.value)
    return peaks


def _observation_day(observation: Observation) -> date:
    period = observation.period_start
    return period.date() if isinstance(period, datetime) else period
