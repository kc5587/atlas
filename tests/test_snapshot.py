from datetime import date, datetime, timezone
from pathlib import Path

from atlas.evidence import EvidenceKind, Observation, SourceRef
from atlas.snapshot import (
    SnapshotManifest,
    read_observations,
    sha256_file,
    write_manifest,
    write_observations,
)


SOURCE = SourceRef(
    id="fixture:test",
    url="https://example.com/data",
    publisher="Test Publisher",
)


def observation(period: date | datetime, index: int) -> Observation:
    return Observation(
        id=f"observation-{index}",
        metric_id="demand",
        entity_id="ERCO",
        period_start=period,
        period_end=period,
        value=100.0 + index,
        unit="MW",
        source=SOURCE,
        retrieved_at=date(2026, 7, 3),
        vintage="2026-07-03",
        kind=EvidenceKind.OBSERVED,
    )


def test_observations_round_trip_with_date_and_datetime_precision(tmp_path: Path) -> None:
    path = tmp_path / "observations.json"
    original = (
        observation(date(2026, 7, 2), 0),
        observation(datetime(2026, 7, 2, tzinfo=timezone.utc), 1),
    )

    write_observations(path, original)
    restored = read_observations(path)

    assert restored == original


def test_manifest_records_artifact_checksum_and_row_count(tmp_path: Path) -> None:
    artifact = tmp_path / "observations.json"
    write_observations(artifact, (observation(date(2026, 7, 2), 0),))
    manifest = SnapshotManifest.create(
        snapshot_id="2026-07-03T120000Z",
        generated_at=datetime(2026, 7, 3, 12, tzinfo=timezone.utc),
        dataset_status="complete",
        artifacts=(
            {
                "path": "observations.json",
                "source_id": "fixture:test",
                "row_count": 1,
                "sha256": sha256_file(artifact),
            },
        ),
    )
    manifest_path = tmp_path / "manifest.json"

    write_manifest(manifest_path, manifest)

    assert manifest_path.exists()
    assert manifest.artifacts[0]["row_count"] == 1
    assert len(manifest.artifacts[0]["sha256"]) == 64
