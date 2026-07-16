"""Parser for NYISO archived day-ahead zonal LBMP archives."""

import csv
import io
import zipfile
from collections import defaultdict
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

from atlas.evidence import EvidenceKind, Observation, SourceRef, Temporal


class NYISODataError(ValueError):
    """Raised when a NYISO archive cannot satisfy the Atlas data contract."""


NYISO_SOURCE = SourceRef(
    id="nyiso:dam-lbmp",
    url="https://mis.nyiso.com/public/P-2Alist.htm",
    publisher="New York Independent System Operator",
)

NYISO_ZONES = frozenset(
    {"CAPITL", "CENTRL", "DUNWOD", "GENESE", "HUD VL", "LONGIL", "MHK VL",
     "MILLWD", "N.Y.C.", "NORTH", "WEST"}
)


def parse_nyiso_lbmp_zip(
    path: Path,
    source: SourceRef,
    retrieved_at: Temporal,
) -> tuple[Observation, ...]:
    """Average observed NYISO load-zone LBMPs by local hourly timestamp."""

    grouped: defaultdict[datetime, list[float]] = defaultdict(list)
    try:
        with zipfile.ZipFile(path) as archive:
            names = tuple(name for name in archive.namelist() if name.endswith("_zone.csv"))
            for name in names:
                with archive.open(name) as raw_handle:
                    text = io.TextIOWrapper(raw_handle, encoding="utf-8-sig")
                    for row in csv.DictReader(text):
                        _collect_row(row, grouped)
    except (OSError, zipfile.BadZipFile, UnicodeError) as error:
        raise NYISODataError(f"could not read NYISO archive: {path}") from error
    if not grouped:
        raise NYISODataError("NYISO archive has no supported zonal LBMP rows")
    return tuple(
        _observation(period, values, source, retrieved_at)
        for period, values in sorted(grouped.items())
    )


def _collect_row(
    row: Mapping[str, str | None], grouped: defaultdict[datetime, list[float]]
) -> None:
    zone = (row.get("Name") or "").strip()
    raw_timestamp = (row.get("Time Stamp") or "").strip()
    raw_price = (row.get("LBMP ($/MWHr)") or "").strip()
    if zone not in NYISO_ZONES or not raw_timestamp or not raw_price:
        return
    try:
        timestamp = datetime.strptime(raw_timestamp, "%m/%d/%Y %H:%M")
        price = float(raw_price)
    except ValueError as error:
        raise NYISODataError("invalid NYISO timestamp or LBMP") from error
    grouped[timestamp].append(price)


def _observation(
    period: datetime,
    values: list[float],
    source: SourceRef,
    retrieved_at: Temporal,
) -> Observation:
    return Observation(
        id=f"nyiso:wholesale:NYIS:{period.isoformat()}",
        metric_id="wholesale_price",
        entity_id="NYIS",
        period_start=period,
        period_end=period,
        value=sum(values) / len(values),
        unit="USD_per_MWh",
        source=source,
        retrieved_at=retrieved_at,
        vintage=period.strftime("%Y-%m"),
        kind=EvidenceKind.INFERRED,
        quality_flags=("nyiso_zone_mean_unweighted", "nyiso_local_time"),
    )
