"""Parser for EIA-930 bulk balance files."""

import csv
from datetime import datetime, timezone
from pathlib import Path

from atlas.evidence import EvidenceKind, Observation, SourceRef, Temporal


class EIA930DataError(ValueError):
    """Raised when an EIA-930 balance file has no usable rows."""


EIA930_SOURCE = SourceRef(
    id="eia:grid-monitor-bulk",
    url="https://www.eia.gov/electricity/gridmonitor/",
    publisher="U.S. Energy Information Administration",
)


def parse_eia930_files(
    paths: tuple[Path, ...],
    regions: tuple[str, ...],
    retrieved_at: Temporal,
) -> tuple[Observation, ...]:
    """Parse demand and net-generation rows from official six-month files."""

    allowed = frozenset(regions)
    observations: list[Observation] = []
    for path in paths:
        observations.extend(_parse_file(path, allowed, retrieved_at))
    if not observations:
        raise EIA930DataError("EIA-930 files have no supported operating rows")
    return tuple(observations)


def _parse_file(
    path: Path, regions: frozenset[str], retrieved_at: Temporal
) -> tuple[Observation, ...]:
    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            reader = csv.DictReader(handle)
            rows = tuple(_parse_row(row, regions, retrieved_at) for row in reader)
    except (OSError, csv.Error, UnicodeError) as error:
        raise EIA930DataError(f"could not read EIA-930 file: {path}") from error
    return tuple(
        observation
        for parsed in rows
        if parsed is not None
        for observation in parsed
    )


def _parse_row(
    row: dict[str, str | None], regions: frozenset[str], retrieved_at: Temporal
) -> tuple[Observation, ...] | None:
    region = (row.get("Balancing Authority") or "").strip()
    if region not in regions:
        return None
    raw_period = (row.get("UTC Time at End of Hour") or "").strip()
    if not raw_period:
        return None
    try:
        period = datetime.strptime(raw_period, "%m/%d/%Y %I:%M:%S %p").replace(
            tzinfo=timezone.utc
        )
    except ValueError as error:
        raise EIA930DataError("invalid EIA-930 UTC timestamp") from error
    observations: list[Observation] = []
    for metric_id, column in (
        ("demand", "Demand (MW)"),
        ("net_generation", "Net Generation (MW)"),
    ):
        raw_value = (row.get(column) or "").strip()
        if not raw_value:
            continue
        try:
            value = float(raw_value)
        except ValueError as error:
            raise EIA930DataError(f"invalid EIA-930 {metric_id} value") from error
        observations.append(
            Observation(
                id=f"eia930:{metric_id}:{region}:{period.isoformat()}",
                metric_id=metric_id,
                entity_id=region,
                period_start=period,
                period_end=period,
                value=value,
                unit="MW",
                source=EIA930_SOURCE,
                retrieved_at=retrieved_at,
                vintage=period.strftime("%Y-%m"),
                kind=EvidenceKind.OBSERVED,
                quality_flags=("eia930_bulk_balance",),
            )
        )
    return tuple(observations)
