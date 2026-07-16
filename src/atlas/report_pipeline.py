"""Build the fixed v1 report from one curated observation set."""

from datetime import date, datetime
from collections.abc import Mapping
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
    demand_dates = [
        observation.period_start.date()
        if isinstance(observation.period_start, datetime)
        else observation.period_start
        for observation in eia_observations
        if observation.metric_id == "demand"
    ]
    if not demand_dates:
        raise ValueError("snapshot contains no demand observations")
    return build_report_from_observations(
        observations=eia_observations,
        capex_observations=capex_observations,
        region_ids=region_ids,
        company_labels=company_labels,
        as_of=max(demand_dates),
        generated_at=datetime.fromisoformat(manifest["generated_at"]),
        analysis=analysis,
    )


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
