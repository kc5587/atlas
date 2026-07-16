"""Versioned observation storage and refresh manifests."""

import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from atlas.evidence import EvidenceKind, Observation, SourceRef, Temporal


SNAPSHOT_SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class SnapshotManifest:
    """Metadata required to identify and audit one refresh snapshot."""

    schema_version: int
    snapshot_id: str
    generated_at: datetime
    dataset_status: str
    artifacts: tuple[dict[str, Any], ...]

    @classmethod
    def create(
        cls,
        snapshot_id: str,
        generated_at: datetime,
        dataset_status: str,
        artifacts: tuple[dict[str, Any], ...],
    ) -> "SnapshotManifest":
        if not snapshot_id.strip() or not dataset_status.strip():
            raise ValueError("snapshot_id and dataset_status are required")
        return cls(
            schema_version=SNAPSHOT_SCHEMA_VERSION,
            snapshot_id=snapshot_id,
            generated_at=generated_at,
            dataset_status=dataset_status,
            artifacts=tuple(dict(artifact) for artifact in artifacts),
        )


def write_observations(path: Path, observations: tuple[Observation, ...]) -> None:
    """Write observations atomically as one versioned JSON document."""

    payload = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "observations": [_serialize_observation(observation) for observation in observations],
    }
    _atomic_write_json(path, payload)


def read_observations(path: Path) -> tuple[Observation, ...]:
    """Read and validate a versioned observation document."""

    payload = _read_json(path)
    if payload.get("schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("unsupported observation schema version")
    raw_observations = payload.get("observations")
    if not isinstance(raw_observations, list):
        raise ValueError("observation document must contain a list")
    return tuple(_deserialize_observation(raw) for raw in raw_observations)


def write_manifest(path: Path, manifest: SnapshotManifest) -> None:
    """Write a manifest atomically so incomplete refreshes cannot replace it."""

    _atomic_write_json(path, _serialize_manifest(manifest))


def write_json_document(path: Path, payload: Mapping[str, object]) -> None:
    """Write a raw source response atomically."""

    _atomic_write_json(path, payload)


def write_text_document(path: Path, content: str) -> None:
    """Write a text artifact atomically."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as temporary:
        temporary.write(content)
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    try:
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)


def sha256_file(path: Path) -> str:
    """Compute a content checksum for a completed artifact."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _serialize_observation(observation: Observation) -> dict[str, Any]:
    return {
        "id": observation.id,
        "metric_id": observation.metric_id,
        "entity_id": observation.entity_id,
        "period_start": observation.period_start.isoformat(),
        "period_end": observation.period_end.isoformat(),
        "value": observation.value,
        "unit": observation.unit,
        "source": asdict(observation.source),
        "retrieved_at": observation.retrieved_at.isoformat(),
        "vintage": observation.vintage,
        "kind": observation.kind.value,
        "quality_flags": list(observation.quality_flags),
    }


def _deserialize_observation(raw: object) -> Observation:
    if not isinstance(raw, Mapping):
        raise ValueError("observation entry must be an object")
    source = raw.get("source")
    if not isinstance(source, Mapping):
        raise ValueError("observation source must be an object")
    return Observation(
        id=_string(raw, "id"),
        metric_id=_string(raw, "metric_id"),
        entity_id=_string(raw, "entity_id"),
        period_start=_parse_temporal(raw, "period_start"),
        period_end=_parse_temporal(raw, "period_end"),
        value=float(raw["value"]),
        unit=_string(raw, "unit"),
        source=SourceRef(
            id=_string(source, "id"),
            url=_string(source, "url"),
            publisher=_string(source, "publisher"),
        ),
        retrieved_at=_parse_temporal(raw, "retrieved_at"),
        vintage=_string(raw, "vintage"),
        kind=EvidenceKind(_string(raw, "kind")),
        quality_flags=tuple(str(flag) for flag in raw.get("quality_flags", ())),
    )


def _serialize_manifest(manifest: SnapshotManifest) -> dict[str, Any]:
    return {
        "schema_version": manifest.schema_version,
        "snapshot_id": manifest.snapshot_id,
        "generated_at": manifest.generated_at.isoformat(),
        "dataset_status": manifest.dataset_status,
        "artifacts": [dict(artifact) for artifact in manifest.artifacts],
    }


def _parse_temporal(raw: Mapping[str, object], key: str) -> Temporal:
    value = raw.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be an ISO string")
    return datetime.fromisoformat(value) if "T" in value else date.fromisoformat(value)


def _string(raw: Mapping[str, object], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _read_json(path: Path) -> Mapping[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"could not read snapshot file: {path}") from error
    if not isinstance(payload, Mapping):
        raise ValueError("snapshot file must contain an object")
    return payload


def _atomic_write_json(path: Path, payload: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        delete=False,
    ) as temporary:
        json.dump(payload, temporary, indent=2, sort_keys=True)
        temporary.write("\n")
        temporary.flush()
        os.fsync(temporary.fileno())
        temporary_path = Path(temporary.name)
    try:
        temporary_path.replace(path)
    finally:
        temporary_path.unlink(missing_ok=True)
