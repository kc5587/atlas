"""Parser for EIA's published daily wholesale-price spreadsheet exports."""

import csv
import re
from collections.abc import Mapping
from datetime import date, datetime
from pathlib import Path

from atlas.evidence import EvidenceKind, Observation, SourceRef, Temporal


class WholesaleDataError(ValueError):
    """Raised when a wholesale export has no usable Atlas rows."""


WHOLESALE_SOURCE = SourceRef(
    id="eia:wholesale",
    url="https://www.eia.gov/electricity/wholesale/",
    publisher="U.S. Energy Information Administration",
)


HUB_TO_REGION = {
    "ERCOT North": "ERCO",
    "PJM West": "PJM",
    "Indiana Hub": "MISO",
    "NP-15": "CISO",
    "SP-15": "CISO",
    "Mass Hub": "ISNE",
    "Palo Verde": "SWPP",
}

HUB_ALIASES = {
    "ERCOT North 345KV Peak": "ERCO",
    "Indiana Hub RT Peak": "MISO",
    "PJM WH Real Time Peak": "PJM",
    "NP15 EZ Gen DA LMP Peak": "CISO",
    "SP15 Gen DA LMP Peak": "CISO",
    "SP15 EZ Gen DA LMP Peak": "CISO",
    "Nepool MH DA LMP Peak": "ISNE",
    "Mass Hub": "ISNE",
    "Palo Verde Peak": "SWPP",
}


def parse_wholesale_csv(
    path: Path,
    source: SourceRef,
    retrieved_at: Temporal,
) -> tuple[Observation, ...]:
    """Parse daily high prices and map supported hubs to v1 regions."""

    try:
        with path.open(newline="", encoding="utf-8-sig") as handle:
            rows = tuple(csv.DictReader(handle))
    except (OSError, csv.Error) as error:
        raise WholesaleDataError(f"could not read wholesale CSV: {path}") from error
    observations: list[Observation] = []
    for row in rows:
        observation = _parse_row(row, source, retrieved_at)
        if observation is not None:
            observations.append(observation)
    if not observations:
        raise WholesaleDataError("no supported wholesale rows")
    return tuple(observations)


def _parse_row(
    row: Mapping[str, str | None], source: SourceRef, retrieved_at: Temporal
) -> Observation | None:
    hub = _first(row, "Hub", "Price Hub", "Price hub", "Location")
    region = _region_for_hub(hub)
    if region is None:
        return None
    date_value = _first(
        row,
        "Date",
        "Delivery Date",
        "Delivery Start Date",
        "Delivery start date",
    )
    price_value = _first(row, "High Price", "High", "High price $/MWh")
    if not date_value or not price_value or price_value in {"-", "NA", "N/A"}:
        return None
    try:
        period = _parse_date(date_value)
        value = float(price_value.replace(",", "").replace("$", ""))
    except ValueError as error:
        raise WholesaleDataError("invalid wholesale date or price") from error
    return Observation(
        id=(
            f"eia:wholesale:{region}:{_slug(hub)}:{period.isoformat()}"
        ),
        metric_id="wholesale_price",
        entity_id=region,
        period_start=period,
        period_end=period,
        value=value,
        unit="USD_per_MWh",
        source=source,
        retrieved_at=retrieved_at,
        vintage=retrieved_at.isoformat(),
        kind=EvidenceKind.OBSERVED,
        quality_flags=("eia_wholesale_high_price", hub),
    )


def _first(row: Mapping[str, str | None], *keys: str) -> str | None:
    for key in keys:
        value = row.get(key)
        if value and value.strip():
            return value.strip()
    return None


def _region_for_hub(hub: str | None) -> str | None:
    if not hub:
        return None
    normalized = hub.strip()
    if normalized in HUB_TO_REGION:
        return HUB_TO_REGION[normalized]
    for alias, region in HUB_ALIASES.items():
        if normalized.startswith(alias):
            return region
    return None


def _parse_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            return datetime.strptime(value, "%m/%d/%Y").date()


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
