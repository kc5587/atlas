"""Descriptive hindcasts and sensitivity checks for Atlas v1.1."""

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from math import sqrt

from atlas.analysis.demand import DemandPressureConfig, demand_pressure
from atlas.analysis.price import PriceStressConfig, price_stress
from atlas.analysis.supply import SupplyTightnessConfig, supply_tightness
from atlas.evidence import Observation
from atlas.scoring import (
    COMPONENT_WEIGHTS,
    BottleneckScore,
    ComponentSignal,
    score_region,
)


@dataclass(frozen=True, slots=True)
class EvaluationConfig:
    """Fixed, transparent parameters for historical evaluation."""

    demand_config: DemandPressureConfig = field(default_factory=DemandPressureConfig)
    supply_config: SupplyTightnessConfig = field(
        default_factory=SupplyTightnessConfig
    )
    price_config: PriceStressConfig = field(default_factory=PriceStressConfig)
    minimum_history_days: int = 365
    weights: Mapping[str, float] = field(
        default_factory=lambda: dict(COMPONENT_WEIGHTS)
    )

    def __post_init__(self) -> None:
        if self.minimum_history_days <= 0:
            raise ValueError("minimum_history_days must be positive")


def monthly_as_of_dates(
    observations: tuple[Observation, ...], start: date, end: date
) -> tuple[date, ...]:
    """Choose the last observed demand day in each calendar month."""

    available = frozenset(
        _day(observation)
        for observation in observations
        if observation.metric_id == "demand"
    )
    dates: list[date] = []
    cursor = start.replace(day=1)
    while cursor <= end:
        next_month = _next_month(cursor)
        month_end = min(end, next_month - timedelta(days=1))
        candidates = tuple(day for day in available if cursor <= day <= month_end)
        if candidates:
            dates.append(max(candidates))
        cursor = next_month
    return tuple(dates)


def run_backtest(
    observations: tuple[Observation, ...],
    region_ids: tuple[str, ...],
    as_of_dates: Sequence[date],
    horizons: tuple[int, ...] = (30, 90),
    config: EvaluationConfig = EvaluationConfig(),
) -> dict[str, object]:
    """Compare month-end scores with subsequently realised pressure."""

    rows: list[dict[str, object]] = []
    for region_id in region_ids:
        for as_of in as_of_dates:
            if not _has_history(observations, as_of, config.minimum_history_days):
                continue
            signal = _score_at(observations, region_id, as_of, config)
            if signal is None:
                continue
            for horizon in horizons:
                future_date = as_of + timedelta(days=horizon)
                future = _score_at(observations, region_id, future_date, config)
                if future is None:
                    continue
                rows.append(
                    {
                        "region_id": region_id,
                        "as_of": as_of.isoformat(),
                        "horizon_days": horizon,
                        "signal_pressure": round(signal.pressure, 4),
                        "future_pressure": round(future.pressure, 4),
                        "future_delta": round(future.pressure - signal.pressure, 4),
                        "signal_confidence": round(signal.confidence, 4),
                    }
                )
    return {
        "schema_version": 1,
        "method": "as_of_score_vs_future_realised_composite",
        "lookahead_safe": True,
        "rows": rows,
        "summaries": [_summarise(rows, horizon) for horizon in horizons],
    }


def build_score_history(
    observations: tuple[Observation, ...],
    region_ids: tuple[str, ...],
    as_of_dates: Sequence[date],
    config: EvaluationConfig = EvaluationConfig(),
) -> list[dict[str, object]]:
    """Return monthly score and component history for report visualisation."""

    history: list[dict[str, object]] = []
    for region_id in region_ids:
        points: list[dict[str, object]] = []
        for as_of in as_of_dates:
            score = _score_at(observations, region_id, as_of, config)
            if score is None:
                continue
            points.append(
                {
                    "as_of": as_of.isoformat(),
                    "pressure": round(score.pressure, 4),
                    "confidence": round(score.confidence, 4),
                    "components": {
                        component.name: None
                        if component.value is None
                        else round(component.value, 4)
                        for component in score.components
                    },
                }
            )
        history.append({"region_id": region_id, "points": points})
    return history


def run_sensitivity(
    observations: tuple[Observation, ...],
    region_ids: tuple[str, ...],
    as_of: date,
    demand_windows: tuple[int, ...] = (14, 28, 56),
    price_windows: tuple[int, ...] = (90, 365),
    weight_sets: Mapping[str, Mapping[str, float]] | None = None,
) -> dict[str, object]:
    """Measure score range and rank stability across fixed alternatives."""

    weights = weight_sets or _default_weight_sets()
    scenarios: list[dict[str, object]] = []
    for demand_days in demand_windows:
        for price_days in price_windows:
            for weight_name, weight_values in weights.items():
                config = EvaluationConfig(
                    demand_config=DemandPressureConfig(
                        baseline_days=demand_days,
                        min_baseline_days=min(7, demand_days),
                    ),
                    price_config=PriceStressConfig(
                        baseline_days=price_days,
                        min_baseline_days=min(30, price_days),
                    ),
                    minimum_history_days=min(demand_days, price_days),
                    weights=weight_values,
                )
                scores = {
                    region_id: _score_at(observations, region_id, as_of, config)
                    for region_id in region_ids
                }
                scenarios.append(
                    {
                        "demand_baseline_days": demand_days,
                        "price_baseline_days": price_days,
                        "weight_set": weight_name,
                        "scores": {
                            region_id: None if score is None else round(score.pressure, 4)
                            for region_id, score in scores.items()
                        },
                    }
                )
    return {
        "schema_version": 1,
        "as_of": as_of.isoformat(),
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
        "region_summary": _sensitivity_summary(scenarios, region_ids),
    }


def _score_at(
    observations: tuple[Observation, ...],
    region_id: str,
    as_of: date,
    config: EvaluationConfig,
) -> BottleneckScore | None:
    regional = tuple(
        observation
        for observation in observations
        if observation.entity_id == region_id and _day(observation) <= as_of
    )
    demand = tuple(item for item in regional if item.metric_id == "demand")
    generation = tuple(item for item in regional if item.metric_id == "net_generation")
    prices = tuple(item for item in regional if item.metric_id == "wholesale_price")
    signals = (
        _try_signal(lambda: demand_pressure(demand, as_of, config.demand_config), "demand_pressure"),
        _try_signal(lambda: supply_tightness(demand, generation, as_of, config.supply_config), "supply_tightness"),
        _try_signal(lambda: price_stress(prices, as_of, config.price_config), "price_stress"),
        ComponentSignal("execution_friction", None, 0.0, ()),
    )
    if not any(signal.value is not None for signal in signals):
        return None
    return score_region(region_id, as_of, signals, config.weights)


def _try_signal(
    factory: Callable[[], ComponentSignal], name: str
) -> ComponentSignal:
    try:
        return factory()
    except ValueError:
        return ComponentSignal(name, None, 0.0, ())


def _has_history(
    observations: tuple[Observation, ...], as_of: date, minimum_days: int
) -> bool:
    days = tuple(sorted({_day(item) for item in observations if _day(item) < as_of}))
    return len(days) >= minimum_days


def _summarise(rows: list[dict[str, object]], horizon: int) -> dict[str, object]:
    selected = [row for row in rows if row["horizon_days"] == horizon]
    signal = [float(row["signal_pressure"]) for row in selected]
    future = [float(row["future_pressure"]) for row in selected]
    return {
        "horizon_days": horizon,
        "observations": len(selected),
        "spearman_rank_correlation": round(_spearman(signal, future), 4)
        if len(selected) > 1
        else None,
        "mean_future_delta": round(
            sum(float(row["future_delta"]) for row in selected) / len(selected), 4
        )
        if selected
        else None,
    }


def _sensitivity_summary(
    scenarios: list[dict[str, object]], region_ids: tuple[str, ...]
) -> list[dict[str, object]]:
    output: list[dict[str, object]] = []
    for region_id in region_ids:
        values = tuple(
            float(scores[region_id])
            for scenario in scenarios
            if (scores := scenario["scores"]) and scores[region_id] is not None
        )
        output.append(
            {
                "region_id": region_id,
                "scenario_count": len(values),
                "min_pressure": round(min(values), 4) if values else None,
                "max_pressure": round(max(values), 4) if values else None,
                "mean_pressure": round(sum(values) / len(values), 4) if values else None,
                "pressure_range": round(max(values) - min(values), 4) if values else None,
            }
        )
    return output


def _default_weight_sets() -> dict[str, Mapping[str, float]]:
    return {
        "baseline": dict(COMPONENT_WEIGHTS),
        "demand_heavy": {
            "demand_pressure": 0.50,
            "supply_tightness": 0.25,
            "price_stress": 0.25,
            "execution_friction": 0.0,
        },
        "market_heavy": {
            "demand_pressure": 0.25,
            "supply_tightness": 0.20,
            "price_stress": 0.55,
            "execution_friction": 0.0,
        },
    }


def _spearman(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or len(left) < 2:
        return 0.0
    return _pearson(_ranks(left), _ranks(right))


def _ranks(values: list[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(ordered):
        end = index
        while end + 1 < len(ordered) and ordered[end + 1][1] == ordered[index][1]:
            end += 1
        rank = (index + end + 2) / 2.0
        for position in range(index, end + 1):
            ranks[ordered[position][0]] = rank
        index = end + 1
    return ranks


def _pearson(left: list[float], right: list[float]) -> float:
    left_mean = sum(left) / len(left)
    right_mean = sum(right) / len(right)
    numerator = sum((x - left_mean) * (y - right_mean) for x, y in zip(left, right))
    left_scale = sqrt(sum((x - left_mean) ** 2 for x in left))
    right_scale = sqrt(sum((y - right_mean) ** 2 for y in right))
    return 0.0 if left_scale == 0 or right_scale == 0 else numerator / left_scale / right_scale


def _day(observation: Observation) -> date:
    period = observation.period_start
    return period.date() if isinstance(period, datetime) else period


def _next_month(value: date) -> date:
    return date(value.year + (value.month == 12), 1 if value.month == 12 else value.month + 1, 1)
