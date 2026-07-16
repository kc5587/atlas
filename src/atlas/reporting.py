"""Stable, JSON-compatible analytical output for reports and the web layer."""

from datetime import date, datetime
from typing import Any

from atlas.scoring import BottleneckScore


def build_export(
    scores: tuple[BottleneckScore, ...],
    generated_at: date | datetime,
    dataset_status: str,
) -> dict[str, Any]:
    """Return a versioned export with no references to mutable domain objects."""

    if not dataset_status.strip():
        raise ValueError("dataset_status is required")
    return {
        "schema_version": 1,
        "generated_at": generated_at.isoformat(),
        "dataset_status": dataset_status,
        "regions": [_serialize_score(score) for score in scores],
    }


def _serialize_score(score: BottleneckScore) -> dict[str, Any]:
    return {
        "region_id": score.region_id,
        "as_of": score.as_of.isoformat(),
        "pressure": round(score.pressure, 4),
        "confidence": round(score.confidence, 4),
        "missing_components": list(score.missing_components),
        "components": [
            {
                "name": component.name,
                "value": component.value,
                "weight": component.weight,
                "contribution": round(component.contribution, 4),
                "confidence": component.confidence,
                "observation_ids": list(component.observation_ids),
            }
            for component in score.components
        ],
    }
