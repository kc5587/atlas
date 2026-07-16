"""Finite v1 refresh orchestration with atomic snapshot publication."""

import re
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Protocol

from atlas.evidence import SourceRef
from atlas.ingest.eia import (
    EIAHourlyQuery,
    EIA_SOURCE,
    parse_hourly_demand,
    parse_hourly_generation,
)
from atlas.ingest.sec import SECDataError, SEC_SOURCE, parse_capex_observations
from atlas.ingest.eia930 import EIA930_SOURCE, parse_eia930_files
from atlas.ingest.nyiso import NYISO_SOURCE, parse_nyiso_lbmp_zip
from atlas.ingest.wholesale import WHOLESALE_SOURCE, parse_wholesale_csv
from atlas.snapshot import (
    SnapshotManifest,
    sha256_file,
    write_json_document,
    write_manifest,
    write_observations,
)


DEFAULT_REGIONS = ("ERCO", "PJM", "MISO", "CISO", "SWPP", "NYIS", "ISNE")
DEFAULT_COMPANIES = {
    "Microsoft": "789019",
    "Amazon": "1018724",
    "Alphabet": "1652044",
    "Meta": "1326801",
    "Oracle": "1341439",
    "Equinix": "1101239",
    "Digital Realty": "1297996",
    "Vertiv": "1674101",
}


class EIARefreshClient(Protocol):
    def fetch_hourly_payload(self, query: EIAHourlyQuery) -> Mapping[str, object]: ...


class SECRefreshClient(Protocol):
    def fetch_company_facts(self, cik: str) -> Mapping[str, object]: ...


@dataclass(frozen=True, slots=True)
class RefreshConfig:
    """Inputs that define one complete v1 snapshot."""

    output_dir: Path
    snapshot_id: str
    generated_at: datetime
    start: date
    end: date
    regions: tuple[str, ...] = DEFAULT_REGIONS
    companies: tuple[tuple[str, str], ...] | Mapping[str, str] = ()
    eia_api_key: str | None = None
    sec_user_agent: str = ""
    wholesale_price_csv: Path | None = None
    nyiso_price_zips: tuple[Path, ...] = ()
    eia930_balance_csvs: tuple[Path, ...] = ()

    def __post_init__(self) -> None:
        companies = self.companies
        if not companies:
            companies = tuple(DEFAULT_COMPANIES.items())
        elif isinstance(companies, Mapping):
            companies = tuple(sorted(companies.items()))
        object.__setattr__(self, "companies", tuple(companies))
        object.__setattr__(self, "nyiso_price_zips", tuple(self.nyiso_price_zips))
        object.__setattr__(self, "eia930_balance_csvs", tuple(self.eia930_balance_csvs))
        if not self.snapshot_id.strip() or self.start > self.end:
            raise ValueError("invalid snapshot identity or date range")
        if not self.regions or not self.companies:
            raise ValueError("snapshot requires regions and companies")
        if not self.sec_user_agent.strip():
            raise ValueError("sec_user_agent is required")


def refresh_snapshot(
    config: RefreshConfig,
    eia_client: EIARefreshClient,
    sec_client: SECRefreshClient,
) -> Path:
    """Build and atomically publish one complete snapshot."""

    final_dir = config.output_dir / config.snapshot_id
    staging_dir = config.output_dir / f".{config.snapshot_id}.staging"
    if final_dir.exists() or staging_dir.exists():
        raise FileExistsError(f"snapshot path already exists: {config.snapshot_id}")
    staging_dir.mkdir(parents=True, exist_ok=False)
    try:
        artifacts = _refresh_eia(config, eia_client, staging_dir)
        artifacts.extend(_refresh_sec(config, sec_client, staging_dir))
        manifest = SnapshotManifest.create(
            snapshot_id=config.snapshot_id,
            generated_at=config.generated_at,
            dataset_status="complete",
            artifacts=tuple(artifacts),
        )
        write_manifest(staging_dir / "manifest.json", manifest)
        staging_dir.replace(final_dir)
        return final_dir
    except Exception as error:
        write_json_document(
            staging_dir / "FAILED.json",
            {
                "snapshot_id": config.snapshot_id,
                "generated_at": config.generated_at.isoformat(),
                "dataset_status": "failed",
                "error_type": type(error).__name__,
                "error": str(error),
            },
        )
        raise


def _refresh_eia(
    config: RefreshConfig,
    client: EIARefreshClient,
    staging_dir: Path,
) -> list[dict[str, object]]:
    query = EIAHourlyQuery(
        regions=config.regions,
        start=config.start,
        end=config.end,
        api_key=config.eia_api_key,
    )
    retrieved_at = config.generated_at
    if config.eia930_balance_csvs:
        operating = parse_eia930_files(
            config.eia930_balance_csvs, config.regions, retrieved_at
        )
        demand = tuple(item for item in operating if item.metric_id == "demand")
        generation = tuple(
            item for item in operating if item.metric_id == "net_generation"
        )
        payload: Mapping[str, object] = {
            "source": "eia930_bulk_balance",
            "files": [str(path) for path in config.eia930_balance_csvs],
            "row_count": len(operating),
        }
    else:
        payload = client.fetch_hourly_payload(query)
        demand = parse_hourly_demand(payload, EIA_SOURCE, retrieved_at)
        generation = parse_hourly_generation(payload, EIA_SOURCE, retrieved_at)
    price_observations = ()
    raw_path = staging_dir / "raw/eia_operating.json"
    observation_path = staging_dir / "curated/eia_observations.json"
    write_json_document(raw_path, payload)
    artifacts = [
        _artifact(
            staging_dir, raw_path, EIA_SOURCE, _raw_row_count(payload), retrieved_at
        ),
    ]
    if config.eia930_balance_csvs:
        for balance_path in config.eia930_balance_csvs:
            raw_balance_path = staging_dir / "raw/eia930" / balance_path.name
            raw_balance_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(balance_path, raw_balance_path)
            artifacts.append(
                _artifact(
                    staging_dir,
                    raw_balance_path,
                    EIA930_SOURCE,
                    0,
                    retrieved_at,
                )
            )
    if config.wholesale_price_csv is not None:
        price_observations = parse_wholesale_csv(
            config.wholesale_price_csv, WHOLESALE_SOURCE, retrieved_at
        )
        raw_price_path = staging_dir / "raw/eia_wholesale.csv"
        shutil.copyfile(config.wholesale_price_csv, raw_price_path)
        artifacts.append(
            _artifact(
                staging_dir,
                raw_price_path,
                WHOLESALE_SOURCE,
                len(price_observations),
                retrieved_at,
            )
        )
    nyiso_observations = ()
    for nyiso_zip in config.nyiso_price_zips:
        parsed = parse_nyiso_lbmp_zip(nyiso_zip, NYISO_SOURCE, retrieved_at)
        nyiso_observations += parsed
        raw_nyiso_path = staging_dir / "raw/nyiso" / nyiso_zip.name
        raw_nyiso_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(nyiso_zip, raw_nyiso_path)
        artifacts.append(
            _artifact(
                staging_dir,
                raw_nyiso_path,
                NYISO_SOURCE,
                len(parsed),
                retrieved_at,
            )
        )
    all_observations = demand + generation + price_observations + nyiso_observations
    write_observations(observation_path, all_observations)
    artifacts.append(
        _artifact(
            staging_dir,
            observation_path,
            EIA_SOURCE,
            len(all_observations),
            retrieved_at,
        )
    )
    return artifacts


def _refresh_sec(
    config: RefreshConfig,
    client: SECRefreshClient,
    staging_dir: Path,
) -> list[dict[str, object]]:
    raw_dir = staging_dir / "raw/sec"
    all_observations = []
    artifacts: list[dict[str, object]] = []
    for company, cik in config.companies:
        payload = client.fetch_company_facts(cik)
        slug = _slug(company)
        raw_path = raw_dir / f"{slug}.json"
        write_json_document(raw_path, payload)
        artifacts.append(
            _artifact(staging_dir, raw_path, SEC_SOURCE, 1, config.generated_at)
        )
        try:
            observations = parse_capex_observations(
                payload, cik, SEC_SOURCE, config.generated_at
            )
        except SECDataError:
            observations = ()
        all_observations.extend(observations)
    observation_path = staging_dir / "curated/sec_capex.json"
    write_observations(observation_path, tuple(all_observations))
    artifacts.append(
        _artifact(
            staging_dir,
            observation_path,
            SEC_SOURCE,
            len(all_observations),
            config.generated_at,
        )
    )
    return artifacts


def _artifact(
    root: Path,
    path: Path,
    source: SourceRef,
    row_count: int,
    retrieved_at: datetime,
) -> dict[str, object]:
    return {
        "path": str(path.relative_to(root)),
        "source_id": source.id,
        "source_url": source.url,
        "retrieved_at": retrieved_at.isoformat(),
        "row_count": row_count,
        "sha256": sha256_file(path),
    }


def _raw_row_count(payload: Mapping[str, object]) -> int:
    response = payload.get("response")
    if isinstance(response, dict) and isinstance(response.get("data"), list):
        return len(response["data"])
    return 1


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
