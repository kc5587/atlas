"""Regional ranking and evidence-aware insight generation."""

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from atlas.scoring import BottleneckScore, ComponentSignal, score_region


@dataclass(frozen=True, slots=True)
class RegionalSnapshot:
    """A region's normalised component signals at one point in time."""

    region_id: str
    as_of: date
    signals: tuple[ComponentSignal, ...]

    @property
    def score(self) -> BottleneckScore:
        """Calculate a score without modifying the underlying observations."""

        return score_region(self.region_id, self.as_of, self.signals)


@dataclass(frozen=True, slots=True)
class InsightCard:
    """A compact research interpretation that remains linked to a score."""

    region_id: str
    title: str
    finding: str
    caveat: str
    score: BottleneckScore


def load_signal_fixture(path: Path | str) -> tuple[RegionalSnapshot, ...]:
    """Load deterministic, schema-checked regional signals for development."""

    fixture_path = Path(path)
    try:
        payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"could not read signal fixture: {fixture_path}") from error

    regions = payload.get("regions") if isinstance(payload, dict) else None
    if not isinstance(regions, list):
        raise ValueError("signal fixture must contain a regions list")
    return tuple(_parse_region(item) for item in regions)


def rank_regions(snapshots: tuple[RegionalSnapshot, ...]) -> tuple[BottleneckScore, ...]:
    """Rank regions by pressure, breaking ties deterministically by ID."""

    scores = tuple(snapshot.score for snapshot in snapshots)
    return tuple(sorted(scores, key=lambda score: (-score.pressure, score.region_id)))


def build_insight(score: BottleneckScore) -> InsightCard:
    """Explain the score using contributions and explicit coverage caveats."""

    band = _pressure_band(score.pressure)
    ranked = sorted(
        (component for component in score.components if component.value is not None),
        key=lambda component: (-component.contribution, component.name),
    )
    leaders = " and ".join(_display_name(component.name) for component in ranked[:2])
    finding = f"{leaders} are the leading pressure contributors."
    caveat = _caveat_for(score)
    return InsightCard(
        region_id=score.region_id,
        title=f"{score.region_id.upper()}: {band} infrastructure pressure",
        finding=finding,
        caveat=caveat,
        score=score,
    )


def _parse_region(item: Any) -> RegionalSnapshot:
    if not isinstance(item, dict):
        raise ValueError("each region entry must be an object")
    try:
        region_id = item["region_id"]
        as_of = date.fromisoformat(item["as_of"])
        raw_signals = item["signals"]
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("region requires region_id, ISO as_of, and signals") from error
    if not isinstance(region_id, str) or not region_id.strip():
        raise ValueError("region_id is required")
    if not isinstance(raw_signals, dict):
        raise ValueError(f"signals must be an object for {region_id}")
    signals = tuple(_parse_signal(name, raw) for name, raw in raw_signals.items())
    return RegionalSnapshot(region_id, as_of, signals)


def _parse_signal(name: Any, raw: Any) -> ComponentSignal:
    if not isinstance(name, str):
        raise ValueError("component name must be a string")
    if not isinstance(raw, dict):
        raise ValueError(f"signal must be an object for {name}")
    try:
        value = raw["value"]
        confidence = raw["confidence"]
        observation_ids = tuple(raw.get("observation_ids", ()))
        return ComponentSignal(name, value, confidence, observation_ids)
    except (KeyError, TypeError, ValueError) as error:
        if "unknown component" in str(error):
            raise
        raise ValueError(f"invalid signal for {name}") from error


def _pressure_band(pressure: float) -> str:
    if pressure >= 70:
        return "high"
    if pressure >= 45:
        return "moderate"
    return "low"


def _display_name(name: str) -> str:
    return name.replace("_", " ")


def _caveat_for(score: BottleneckScore) -> str:
    if score.missing_components:
        missing = ", ".join(_display_name(name) for name in score.missing_components)
        return f"{missing} is missing; confidence is {score.confidence:.0%}."
    return f"All components are present; confidence is {score.confidence:.0%}."
