"""Transparent regional bottleneck scoring."""

from dataclasses import dataclass
from datetime import date
from math import isfinite
from collections.abc import Mapping


COMPONENT_WEIGHTS = {
    "demand_pressure": 0.35,
    "supply_tightness": 0.30,
    "price_stress": 0.20,
    "execution_friction": 0.15,
}


@dataclass(frozen=True, slots=True)
class ComponentSignal:
    """A normalised component and the confidence in its evidence."""

    name: str
    value: float | None
    confidence: float
    observation_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.name not in COMPONENT_WEIGHTS:
            raise ValueError(f"unknown component: {self.name}")
        if (
            isinstance(self.confidence, bool)
            or not isinstance(self.confidence, (int, float))
            or not 0.0 <= self.confidence <= 1.0
            or not isfinite(self.confidence)
        ):
            raise ValueError("confidence must be between 0 and 1")
        if self.value is not None and (
            isinstance(self.value, bool)
            or not isinstance(self.value, (int, float))
            or not isfinite(self.value)
            or not 0.0 <= self.value <= 100.0
        ):
            raise ValueError("component value must be between 0 and 100")


@dataclass(frozen=True, slots=True)
class ComponentContribution:
    """A score component with its raw contribution to the composite."""

    name: str
    value: float | None
    weight: float
    contribution: float
    confidence: float
    observation_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BottleneckScore:
    """A descriptive score with enough detail to audit its construction."""

    region_id: str
    as_of: date
    pressure: float
    confidence: float
    components: tuple[ComponentContribution, ...]
    missing_components: tuple[str, ...]


def score_region(
    region_id: str,
    as_of: date,
    signals: tuple[ComponentSignal, ...],
    weights: Mapping[str, float] | None = None,
) -> BottleneckScore:
    """Combine available components without treating missing data as zero."""

    if not region_id.strip():
        raise ValueError("region_id is required")
    by_name: dict[str, ComponentSignal] = {}
    for signal in signals:
        if signal.name in by_name:
            raise ValueError(f"duplicate component: {signal.name}")
        by_name[signal.name] = signal

    effective_weights = _validated_weights(weights)
    all_weight = sum(effective_weights.values())
    available_weight = 0.0
    weighted_value = 0.0
    weighted_confidence = 0.0
    contributions: list[ComponentContribution] = []
    missing: list[str] = []

    for name, weight in effective_weights.items():
        signal = by_name.get(name)
        if signal is None or signal.value is None:
            missing.append(name)
            contributions.append(
                ComponentContribution(name, None, weight, 0.0, 0.0, ())
            )
            continue
        available_weight += weight
        weighted_value += weight * signal.value
        weighted_confidence += weight * signal.confidence
        contributions.append(
            ComponentContribution(
                name=name,
                value=signal.value,
                weight=weight,
                contribution=weight * signal.value,
                confidence=signal.confidence,
                observation_ids=signal.observation_ids,
            )
        )

    if available_weight == 0.0:
        raise ValueError("at least one component value is required")

    return BottleneckScore(
        region_id=region_id,
        as_of=as_of,
        pressure=weighted_value / available_weight,
        confidence=weighted_confidence / all_weight,
        components=tuple(contributions),
        missing_components=tuple(missing),
    )


def _validated_weights(weights: Mapping[str, float] | None) -> dict[str, float]:
    effective = dict(COMPONENT_WEIGHTS if weights is None else weights)
    if set(effective) != set(COMPONENT_WEIGHTS):
        raise ValueError("weights must define every score component")
    if any(
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or value < 0
        for value in effective.values()
    ):
        raise ValueError("weights must be finite and non-negative")
    if sum(effective.values()) <= 0:
        raise ValueError("weights must have positive total")
    return effective
