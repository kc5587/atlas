import json
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from atlas.refresh import RefreshConfig, refresh_snapshot


EIA_FIXTURE = Path("data/fixtures/eia_hourly_demand.json")
SEC_FIXTURE = Path("data/fixtures/sec_companyfacts.json")


class FakeEIAClient:
    def fetch_hourly_payload(self, _query: object) -> dict[str, object]:
        return json.loads(EIA_FIXTURE.read_text(encoding="utf-8"))


class FakeSECClient:
    def fetch_company_facts(self, _cik: str) -> dict[str, object]:
        return json.loads(SEC_FIXTURE.read_text(encoding="utf-8"))


class FailingEIAClient:
    def fetch_hourly_payload(self, _query: object) -> dict[str, object]:
        raise RuntimeError("simulated EIA outage")


def config(tmp_path: Path) -> RefreshConfig:
    return RefreshConfig(
        output_dir=tmp_path,
        snapshot_id="test-snapshot",
        generated_at=datetime(2026, 7, 3, 12, tzinfo=timezone.utc),
        start=date(2026, 7, 2),
        end=date(2026, 7, 2),
        regions=("ERCO",),
        companies={"Example Cloud Holdings": "1"},
        sec_user_agent="Atlas Test <test@example.com>",
    )


def test_refresh_publishes_complete_snapshot_with_manifest(tmp_path: Path) -> None:
    refresh_config = config(tmp_path)
    refresh_config = RefreshConfig(
        output_dir=refresh_config.output_dir,
        snapshot_id=refresh_config.snapshot_id,
        generated_at=refresh_config.generated_at,
        start=refresh_config.start,
        end=refresh_config.end,
        regions=refresh_config.regions,
        companies=refresh_config.companies,
        sec_user_agent=refresh_config.sec_user_agent,
        wholesale_price_csv=Path("data/fixtures/eia_wholesale.csv"),
    )
    final_dir = refresh_snapshot(refresh_config, FakeEIAClient(), FakeSECClient())

    assert final_dir == tmp_path / "test-snapshot"
    assert (final_dir / "manifest.json").exists()
    assert (final_dir / "raw/eia_operating.json").exists()
    assert (final_dir / "curated/eia_observations.json").exists()
    manifest = json.loads((final_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["dataset_status"] == "complete"
    assert len(manifest["artifacts"]) == 5
    assert all(
        artifact["source_url"].startswith("https://")
        for artifact in manifest["artifacts"]
    )
    assert all(
        artifact["retrieved_at"] == "2026-07-03T12:00:00+00:00"
        for artifact in manifest["artifacts"]
    )
    assert not (tmp_path / ".test-snapshot.staging").exists()


def test_refresh_failure_does_not_publish_final_snapshot(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="simulated EIA outage"):
        refresh_snapshot(config(tmp_path), FailingEIAClient(), FakeSECClient())

    assert not (tmp_path / "test-snapshot" / "manifest.json").exists()
    failure_files = list(tmp_path.glob(".test-snapshot.staging/FAILED.json"))
    assert len(failure_files) == 1
