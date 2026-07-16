"""Parsing for EIA balancing-authority hourly operating data."""

import json
from collections.abc import Mapping
from datetime import date, datetime, timezone
from pathlib import Path

from atlas.evidence import EvidenceKind, Observation, SourceRef, Temporal


class EIADataError(ValueError):
    """Raised when an EIA response cannot satisfy the Atlas data contract."""


def parse_hourly_demand(
    payload_or_path: Mapping[str, object] | Path,
    source: SourceRef,
    retrieved_at: Temporal,
) -> tuple[Observation, ...]:
    """Convert demand rows into timestamped observations, ignoring other series."""

    payload = _load_payload(payload_or_path)
    response = _mapping(payload.get("response"))
    raw_rows = response.get("data")
    if not isinstance(raw_rows, list):
        raise EIADataError("response data must be a list")

    observations: list[Observation] = []
    for raw_row in raw_rows:
        row = _mapping(raw_row)
        series_name = str(row.get("type-name", row.get("type", ""))).lower()
        if series_name not in {"demand", "d"}:
            continue
        observations.append(_parse_demand_row(row, source, retrieved_at))

    if not observations:
        raise EIADataError("no hourly demand rows")
    return tuple(observations)


def _load_payload(payload_or_path: Mapping[str, object] | Path) -> Mapping[str, object]:
    if isinstance(payload_or_path, Path):
        try:
            return _mapping(json.loads(payload_or_path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as error:
            raise EIADataError(f"could not read EIA payload: {payload_or_path}") from error
    return payload_or_path


def _parse_demand_row(
    row: Mapping[str, object], source: SourceRef, retrieved_at: Temporal
) -> Observation:
    try:
        period = _parse_timestamp(row["period"])
        respondent = str(row["respondent"])
        value = float(row["value"])
    except (KeyError, TypeError, ValueError) as error:
        raise EIADataError("invalid demand value or timestamp") from error
    if not respondent.strip():
        raise EIADataError("demand row has no respondent")
    return Observation(
        id=f"eia:demand:{respondent}:{period.isoformat()}",
        metric_id="demand",
        entity_id=respondent,
        period_start=period,
        period_end=period,
        value=value,
        unit=str(row.get("value-units", "MW")),
        source=source,
        retrieved_at=retrieved_at,
        vintage=_vintage(retrieved_at),
        kind=EvidenceKind.OBSERVED,
        quality_flags=("eia_hourly_operating_data",),
    )


def _parse_timestamp(raw_period: object) -> datetime:
    if not isinstance(raw_period, str):
        raise ValueError("period must be a string")
    normalized = raw_period.replace("Z", "+00:00")
    parsed = datetime.fromisoformat(normalized)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _vintage(retrieved_at: Temporal) -> str:
    return retrieved_at.isoformat()


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise EIADataError("EIA payload contains an invalid object")
    return value
