"""Build a deterministic offline snapshot for release testing."""

import argparse
import json
from datetime import date, datetime, timezone
from pathlib import Path

from atlas.refresh import RefreshConfig, refresh_snapshot


class FixtureEIAClient:
    def fetch_hourly_payload(self, _query: object) -> dict[str, object]:
        return json.loads(
            Path("data/fixtures/eia_hourly_demand.json").read_text(encoding="utf-8")
        )


class FixtureSECClient:
    def fetch_company_facts(self, _cik: str) -> dict[str, object]:
        return json.loads(
            Path("data/fixtures/sec_companyfacts.json").read_text(encoding="utf-8")
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("data/snapshots"))
    parser.add_argument("--snapshot-id", default="fixture")
    args = parser.parse_args()
    config = RefreshConfig(
        output_dir=args.output_dir,
        snapshot_id=args.snapshot_id,
        generated_at=datetime(2026, 7, 3, 12, tzinfo=timezone.utc),
        start=date(2026, 7, 2),
        end=date(2026, 7, 2),
        regions=("ERCO",),
        companies=(("Example Cloud Holdings", "1"),),
        sec_user_agent="Atlas Fixture <fixture@example.com>",
    )
    print(refresh_snapshot(config, FixtureEIAClient(), FixtureSECClient()))


if __name__ == "__main__":
    main()
