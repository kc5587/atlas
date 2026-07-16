"""Refresh one live Atlas v1 snapshot."""

import argparse
import os
from datetime import date, datetime, timezone
from pathlib import Path

from atlas.ingest.eia import EIAClient
from atlas.ingest.sec import SECClient
from atlas.refresh import DEFAULT_COMPANIES, DEFAULT_REGIONS, RefreshConfig, refresh_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, required=True)
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("data/snapshots"))
    parser.add_argument("--snapshot-id", default=None)
    parser.add_argument("--wholesale-price-csv", type=Path, default=None)
    args = parser.parse_args()
    generated_at = datetime.now(timezone.utc)
    snapshot_id = args.snapshot_id or generated_at.strftime("%Y%m%dT%H%M%SZ")
    eia_key = os.environ.get("EIA_API_KEY")
    sec_user_agent = os.environ.get("SEC_USER_AGENT")
    if not eia_key:
        raise SystemExit("EIA_API_KEY is required for live refresh")
    if not sec_user_agent:
        raise SystemExit("SEC_USER_AGENT is required for live refresh")
    config = RefreshConfig(
        output_dir=args.output_dir,
        snapshot_id=snapshot_id,
        generated_at=generated_at,
        start=args.start,
        end=args.end,
        regions=DEFAULT_REGIONS,
        companies=tuple(DEFAULT_COMPANIES.items()),
        eia_api_key=eia_key,
        sec_user_agent=sec_user_agent,
        wholesale_price_csv=args.wholesale_price_csv,
    )
    final_dir = refresh_snapshot(
        config,
        EIAClient(api_key=eia_key),
        SECClient(user_agent=sec_user_agent),
    )
    print(final_dir)


if __name__ == "__main__":
    main()
