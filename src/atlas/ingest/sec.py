"""SEC Company Facts parsing for public-company capex observations."""

import json
from collections.abc import Mapping
from datetime import date
from pathlib import Path

from atlas.evidence import EvidenceKind, Observation, SourceRef, Temporal


class SECDataError(ValueError):
    """Raised when Company Facts lacks a supported capex fact."""


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


def _load_payload(payload_or_path: Mapping[str, object] | Path) -> Mapping[str, object]:
    if isinstance(payload_or_path, Path):
        try:
            return _mapping(json.loads(payload_or_path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as error:
            raise SECDataError(f"could not read Company Facts payload: {payload_or_path}") from error
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
