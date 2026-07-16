"""Parsing for EIA balancing-authority hourly operating data."""

import json
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable, Protocol
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from atlas.evidence import EvidenceKind, Observation, SourceRef, Temporal


class EIADataError(ValueError):
    """Raised when an EIA response cannot satisfy the Atlas data contract."""


class EIAFetchError(RuntimeError):
    """Raised when the EIA endpoint cannot be reached or decoded."""


class HTTPResponse(Protocol):
    """Minimal response surface required by the client."""

    def __enter__(self) -> "HTTPResponse": ...

    def __exit__(self, *_: object) -> None: ...

    def read(self) -> bytes: ...


Opener = Callable[..., HTTPResponse]
EIA_HOURLY_URL = "https://api.eia.gov/v2/electricity/rto/region-data/data/"
EIA_SOURCE = SourceRef(
    id="eia:grid-monitor",
    url="https://www.eia.gov/electricity/gridmonitor/about",
    publisher="U.S. Energy Information Administration",
)


@dataclass(frozen=True, slots=True)
class EIAHourlyQuery:
    """A bounded query for balancing-authority hourly operating data."""

    regions: tuple[str, ...]
    start: date
    end: date
    api_key: str | None = None

    def __post_init__(self) -> None:
        if not self.regions or any(not region.strip() for region in self.regions):
            raise ValueError("at least one non-empty EIA region is required")
        if self.start > self.end:
            raise ValueError("EIA query start must not be after end")


def build_hourly_query_url(query: EIAHourlyQuery) -> str:
    """Build a bounded URL without logging or embedding credentials elsewhere."""

    params: list[tuple[str, str]] = [
        ("data[]", "value"),
        ("frequency", "hourly"),
        ("start", query.start.isoformat()),
        ("end", query.end.isoformat()),
    ]
    params.extend(("facets[respondent][]", region) for region in query.regions)
    if query.api_key:
        params.append(("api_key", query.api_key))
    return f"{EIA_HOURLY_URL}?{urlencode(params)}"


class EIAClient:
    """Fetch EIA data through an injectable, timeout-bounded transport."""

    def __init__(
        self,
        api_key: str | None = None,
        timeout_seconds: float = 30.0,
        opener: Opener = urlopen,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._opener = opener

    def fetch_hourly_demand(self, query: EIAHourlyQuery) -> tuple[Observation, ...]:
        """Fetch, decode, and validate hourly demand observations."""

        payload = self.fetch_hourly_payload(query)
        return parse_hourly_demand(payload, EIA_SOURCE, datetime.now(timezone.utc))

    def fetch_hourly_operating(
        self, query: EIAHourlyQuery
    ) -> tuple[Observation, ...]:
        """Fetch demand and net-generation rows from one source response."""

        payload = self.fetch_hourly_payload(query)
        retrieved_at = datetime.now(timezone.utc)
        return parse_hourly_demand(
            payload, EIA_SOURCE, retrieved_at
        ) + parse_hourly_generation(payload, EIA_SOURCE, retrieved_at)

    def fetch_hourly_payload(self, query: EIAHourlyQuery) -> Mapping[str, object]:
        """Fetch a raw EIA response for caching and independent parsing."""

        effective_query = query
        if query.api_key is None and self._api_key is not None:
            effective_query = replace(query, api_key=self._api_key)
        request = Request(
            build_hourly_query_url(effective_query),
            headers={"User-Agent": "Atlas/0.1 (+https://github.com/kc5587/atlas)"},
        )
        try:
            with self._opener(request, timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read())
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            raise EIAFetchError("could not fetch EIA data") from error
        if not isinstance(payload, Mapping):
            raise EIADataError("EIA response must be an object")
        return payload


def parse_hourly_demand(
    payload_or_path: Mapping[str, object] | Path,
    source: SourceRef,
    retrieved_at: Temporal,
) -> tuple[Observation, ...]:
    """Convert demand rows into timestamped observations."""

    return _parse_hourly_metric(
        payload_or_path,
        source,
        retrieved_at,
        metric_id="demand",
        accepted_series={"demand", "d"},
    )


def parse_hourly_generation(
    payload_or_path: Mapping[str, object] | Path,
    source: SourceRef,
    retrieved_at: Temporal,
) -> tuple[Observation, ...]:
    """Convert net-generation rows into timestamped observations."""

    return _parse_hourly_metric(
        payload_or_path,
        source,
        retrieved_at,
        metric_id="net_generation",
        accepted_series={"net generation", "ng"},
    )


def _parse_hourly_metric(
    payload_or_path: Mapping[str, object] | Path,
    source: SourceRef,
    retrieved_at: Temporal,
    metric_id: str,
    accepted_series: set[str],
) -> tuple[Observation, ...]:
    """Extract one EIA operating series while ignoring other row types."""

    payload = _load_payload(payload_or_path)
    response = _mapping(payload.get("response"))
    raw_rows = response.get("data")
    if not isinstance(raw_rows, list):
        raise EIADataError("response data must be a list")

    observations: list[Observation] = []
    for raw_row in raw_rows:
        row = _mapping(raw_row)
        series_name = str(row.get("type-name", row.get("type", ""))).lower()
        if series_name not in accepted_series:
            continue
        observations.append(_parse_metric_row(row, source, retrieved_at, metric_id))

    if not observations:
        raise EIADataError(f"no hourly {metric_id} rows")
    return tuple(observations)


def _load_payload(payload_or_path: Mapping[str, object] | Path) -> Mapping[str, object]:
    if isinstance(payload_or_path, Path):
        try:
            return _mapping(json.loads(payload_or_path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as error:
            raise EIADataError(f"could not read EIA payload: {payload_or_path}") from error
    return payload_or_path


def _parse_metric_row(
    row: Mapping[str, object],
    source: SourceRef,
    retrieved_at: Temporal,
    metric_id: str,
) -> Observation:
    try:
        period = _parse_timestamp(row["period"])
        respondent = str(row["respondent"])
        value = float(row["value"])
    except (KeyError, TypeError, ValueError) as error:
        raise EIADataError(f"invalid {metric_id} value or timestamp") from error
    if not respondent.strip():
        raise EIADataError(f"{metric_id} row has no respondent")
    return Observation(
        id=f"eia:{metric_id}:{respondent}:{period.isoformat()}",
        metric_id=metric_id,
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
