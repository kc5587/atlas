"""SEC Company Facts parsing for public-company capex observations."""

import json
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Callable, Protocol
from urllib.error import URLError
from urllib.request import Request, urlopen

from atlas.evidence import EvidenceKind, Observation, SourceRef, Temporal


class SECDataError(ValueError):
    """Raised when Company Facts lacks a supported capex fact."""


class SECFetchError(RuntimeError):
    """Raised when the SEC Company Facts endpoint cannot be reached."""


class HTTPResponse(Protocol):
    """Minimal response surface required by the SEC client."""

    def __enter__(self) -> "HTTPResponse": ...

    def __exit__(self, *_: object) -> None: ...

    def read(self) -> bytes: ...


Opener = Callable[..., HTTPResponse]
SEC_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
SEC_SOURCE = SourceRef(
    id="sec:companyfacts",
    url="https://www.sec.gov/search-filings/edgar-application-programming-interfaces",
    publisher="U.S. Securities and Exchange Commission",
)


class SECClient:
    """Fetch Company Facts with SEC-identifying headers and bounded timeouts."""

    def __init__(
        self,
        user_agent: str,
        timeout_seconds: float = 30.0,
        opener: Opener = urlopen,
    ) -> None:
        if not user_agent.strip():
            raise ValueError("SEC user_agent is required")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._user_agent = user_agent
        self._timeout_seconds = timeout_seconds
        self._opener = opener

    def fetch_company_facts(self, cik: str) -> Mapping[str, object]:
        """Fetch one company's XBRL Company Facts document."""

        normalized_cik = _normalize_cik(cik)
        request = Request(
            SEC_COMPANYFACTS_URL.format(cik=normalized_cik),
            headers={"User-Agent": self._user_agent, "Accept": "application/json"},
        )
        try:
            with self._opener(request, timeout=self._timeout_seconds) as response:
                payload = json.loads(response.read())
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as error:
            raise SECFetchError("could not fetch SEC data") from error
        return _mapping(payload)


CAPEX_CONCEPTS = (
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsToAcquirePropertyPlantAndEquipmentAndIntangibleAssets",
)


def parse_capex_observations(
    payload_or_path: Mapping[str, object] | Path,
    cik: str,
    source: SourceRef,
    retrieved_at: Temporal,
) -> tuple[Observation, ...]:
    """Extract filed capex facts, normalising cash outflows to positive spend."""

    if not cik.strip():
        raise ValueError("cik is required")
    payload = _load_payload(payload_or_path)
    concepts = _concept_facts(payload)
    for concept in CAPEX_CONCEPTS:
        if concept in concepts:
            observations = _parse_concept(
                concepts[concept], cik, concept, source, retrieved_at
            )
            if observations:
                return observations
    raise SECDataError("no supported capex fact")


def _normalize_cik(cik: str) -> str:
    if not cik.isdigit():
        raise ValueError("cik must contain only digits")
    return cik.zfill(10)


def _load_payload(payload_or_path: Mapping[str, object] | Path) -> Mapping[str, object]:
    if isinstance(payload_or_path, Path):
        try:
            return _mapping(json.loads(payload_or_path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as error:
            raise SECDataError(
                f"could not read Company Facts payload: {payload_or_path}"
            ) from error
    return payload_or_path


def _concept_facts(payload: Mapping[str, object]) -> Mapping[str, object]:
    facts = _mapping(payload.get("facts"))
    return _mapping(facts.get("us-gaap"))


def _parse_concept(
    raw_concept: object,
    cik: str,
    concept: str,
    source: SourceRef,
    retrieved_at: Temporal,
) -> tuple[Observation, ...]:
    concept_data = _mapping(raw_concept)
    units = _mapping(concept_data.get("units"))
    raw_values = units.get("USD")
    if not isinstance(raw_values, list):
        raise SECDataError("capex fact has no USD units")
    observations: list[Observation] = []
    for raw_value in raw_values:
        value = _mapping(raw_value)
        try:
            start = date.fromisoformat(str(value["start"]))
            end = date.fromisoformat(str(value["end"]))
            filed = str(value["filed"])
            accession = str(value["accn"])
            amount = abs(float(value["val"]))
        except (KeyError, TypeError, ValueError) as error:
            raise SECDataError("invalid capex fact row") from error
        observations.append(
            Observation(
                id=f"sec:capex:{cik}:{accession}:{start.isoformat()}:{end.isoformat()}",
                metric_id="capex",
                entity_id=f"cik:{cik.zfill(10)}",
                period_start=start,
                period_end=end,
                value=amount,
                unit="USD",
                source=source,
                retrieved_at=retrieved_at,
                vintage=filed,
                kind=EvidenceKind.OBSERVED,
                quality_flags=("sec_xbrl", str(value.get("form", "unknown_form"))),
            )
        )
    return tuple(sorted(observations, key=lambda observation: observation.period_end))


def _mapping(value: object) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise SECDataError("Company Facts payload contains an invalid object")
    return value
