"""Build the fixed v1 report from one curated observation set."""

from collections import defaultdict
from collections.abc import Mapping
from datetime import date, datetime
import json
from typing import Callable
from pathlib import Path

from atlas.analysis.demand import demand_pressure
from atlas.analysis.price import price_stress
from atlas.analysis.supply import supply_tightness
from atlas.evidence import Observation
from atlas.reporting import build_report_export
from atlas.snapshot import read_observations
from atlas.scoring import BottleneckScore, ComponentSignal, score_region


EXPECTED_HOURS_PER_DAY = 24


def build_report_from_observations(
    observations: tuple[Observation, ...],
    capex_observations: tuple[Observation, ...],
    region_ids: tuple[str, ...],
    company_labels: Mapping[str, str],
    as_of: date,
    generated_at: date | datetime,
    analysis: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Create a complete report while keeping partial regions visible."""

    scores = []
    unavailable: dict[str, str] = {}
    for region_id in region_ids:
        region_observations = tuple(
            observation
            for observation in observations
            if observation.entity_id == region_id
        )
        score, reason = _score_region(region_id, region_observations, as_of)
        if score is None:
            unavailable[region_id] = reason
        else:
            scores.append(score)
    return build_report_export(
        scores=tuple(sorted(scores, key=lambda score: (-score.pressure, score.region_id))),
        unavailable_regions=unavailable,
        capex_observations=capex_observations,
        company_labels=company_labels,
        generated_at=generated_at,
        dataset_status="complete" if not unavailable else "partial",
        analysis=analysis,
    )


def build_report_from_snapshot(
    snapshot_dir: Path,
    region_ids: tuple[str, ...],
    company_labels: Mapping[str, str],
    analysis: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Load one published snapshot and build its report payload."""

    manifest = json.loads((snapshot_dir / "manifest.json").read_text(encoding="utf-8"))
    eia_observations = read_observations(
        snapshot_dir / "curated/eia_observations.json"
    )
    capex_observations = read_observations(snapshot_dir / "curated/sec_capex.json")
    as_of = _latest_complete_common_day(eia_observations, region_ids)
    return build_report_from_observations(
        observations=eia_observations,
        capex_observations=capex_observations,
        region_ids=region_ids,
        company_labels=company_labels,
        as_of=as_of,
        generated_at=datetime.fromisoformat(manifest["generated_at"]),
        analysis=analysis,
    )


def _latest_complete_common_day(
    observations: tuple[Observation, ...], region_ids: tuple[str, ...]
) -> date:
    """Return the latest UTC day with complete demand and generation coverage."""

    periods: defaultdict[tuple[str, date, str], set[object]] = defaultdict(set)
    required_metrics = ("demand", "net_generation")
    for observation in observations:
        if observation.entity_id not in region_ids:
            continue
        if observation.metric_id not in required_metrics:
            continue
        day = _observation_day(observation)
        periods[(observation.entity_id, day, observation.metric_id)].add(
            observation.period_start
        )

    candidate_days = sorted({key[1] for key in periods}, reverse=True)
    for day in candidate_days:
        if all(
            len(periods[(region_id, day, metric_id)]) >= EXPECTED_HOURS_PER_DAY
            for region_id in region_ids
            for metric_id in required_metrics
        ):
            return day
    raise ValueError("snapshot contains no complete common operating day")


def _observation_day(observation: Observation) -> date:
    period = observation.period_start
    return period.date() if isinstance(period, datetime) else period


def _score_region(
    region_id: str, observations: tuple[Observation, ...], as_of: date
) -> tuple[BottleneckScore | None, str]:
    demand = tuple(
        observation for observation in observations if observation.metric_id == "demand"
    )
    generation = tuple(
        observation
        for observation in observations
        if observation.metric_id == "net_generation"
    )
    prices = tuple(
        observation
        for observation in observations
        if observation.metric_id == "wholesale_price"
    )
    signals = (
        _try_signal(lambda: demand_pressure(demand, as_of), "demand_pressure"),
        _try_signal(
            lambda: supply_tightness(demand, generation, as_of), "supply_tightness"
        ),
        _try_signal(lambda: price_stress(prices, as_of), "price_stress"),
        ComponentSignal("execution_friction", None, 0.0, ()),
    )
    available = tuple(signal for signal in signals if signal.value is not None)
    if not available:
        return None, "no usable demand, supply, or price observations"
    return score_region(region_id, as_of, signals), ""


def _try_signal(factory: Callable[[], ComponentSignal], name: str) -> ComponentSignal:
    try:
        return factory()
    except ValueError:
        return ComponentSignal(name, None, 0.0, ())
