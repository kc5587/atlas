from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

APP_SCHEMA_VERSION = "1"
_GITHUB_API = "https://api.github.com/repos"


@dataclass(frozen=True)
class DatabaseStatus:
    path: Path
    tag: str
    generated_at: str
    stale: bool
    source: str


def verify_checksum(path: str | Path, expected_sha256: str) -> bool:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest() == expected_sha256


def _tag_sort_key(rel: dict) -> str:
    return rel["tag"]


def resolve_valid_release(
    releases: list[dict], *, app_schema_version: str
) -> Optional[dict]:
    """Return the newest release whose manifest schema_version matches the app.

    Releases are date+time tagged (`data-YYYY-MM-DDThhmmssZ`) so lexical sort by
    tag is chronological. Returns None if none match (caller shows an error).
    """
    candidates = [
        r for r in releases
        if r.get("manifest", {}).get("schema_version") == app_schema_version
    ]
    if not candidates:
        return None
    return sorted(candidates, key=_tag_sort_key, reverse=True)[0]


def _asset_url(release: dict, name: str) -> str:
    assets = release.get("assets", [])
    matches = [asset["browser_download_url"] for asset in assets if asset.get("name") == name]
    if len(matches) != 1:
        raise ValueError(f"release must include exactly one {name} asset")
    return matches[0]


def _download_to_temp(response, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as fh:
        tmp = Path(fh.name)
        for chunk in response.iter_content(chunk_size=1 << 20):
            if chunk:
                fh.write(chunk)
    return tmp


def _write_manifest(target: Path, manifest: dict) -> None:
    sidecar = target.with_suffix(".manifest.json")
    with tempfile.NamedTemporaryFile(mode="w", dir=sidecar.parent, delete=False) as fh:
        tmp = Path(fh.name)
        json.dump(manifest, fh, indent=2)
    tmp.replace(sidecar)


def _cached_status(target: Path, *, app_schema_version: str) -> Optional[DatabaseStatus]:
    sidecar = target.with_suffix(".manifest.json")
    if not target.exists() or not sidecar.exists():
        return None
    try:
        manifest = json.loads(sidecar.read_text())
        if manifest.get("schema_version") != app_schema_version:
            return None
        if not verify_checksum(target, manifest["sha256"]):
            return None
        return DatabaseStatus(
            path=target,
            tag=manifest["tag"],
            generated_at=manifest["generated_at"],
            stale=True,
            source="cache",
        )
    except (json.JSONDecodeError, KeyError, OSError):
        return None


def _headers(token: Optional[str]) -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def refresh_database(
    repo: str,
    target: str | Path,
    *,
    session=requests,
    token: Optional[str] = None,
    app_schema_version: str = APP_SCHEMA_VERSION,
) -> DatabaseStatus:
    """Fetch the newest valid immutable release, falling back remotely then locally."""
    target = Path(target)
    headers = _headers(token)
    try:
        response = session.get(f"{_GITHUB_API}/{repo}/releases", headers=headers, timeout=15)
        response.raise_for_status()
        releases = sorted(response.json(), key=lambda release: release["tag_name"], reverse=True)
    except (requests.RequestException, KeyError, TypeError, ValueError):
        releases = []

    data_releases = [
        release for release in releases
        if release.get("tag_name", "").startswith("data-")
        and not release.get("draft")
        and not release.get("prerelease")
    ]
    for index, release in enumerate(data_releases):
        try:
            manifest_url = _asset_url(release, "manifest.json")
            db_url = _asset_url(release, "atlas.duckdb")
            response = session.get(manifest_url, headers=headers, timeout=15)
            response.raise_for_status()
            manifest = response.json()
            if manifest["schema_version"] != app_schema_version:
                continue
            if manifest["db_asset_url"] != db_url:
                continue
            response = session.get(db_url, headers=headers, timeout=60, stream=True)
            response.raise_for_status()
            tmp = _download_to_temp(response, target)
            try:
                if not verify_checksum(tmp, manifest["sha256"]):
                    continue
                tmp.replace(target)
            finally:
                tmp.unlink(missing_ok=True)
            cached_manifest = {**manifest, "tag": release["tag_name"]}
            _write_manifest(target, cached_manifest)
            return DatabaseStatus(
                path=target,
                tag=release["tag_name"],
                generated_at=manifest["generated_at"],
                stale=index > 0,
                source="remote",
            )
        except (requests.RequestException, KeyError, TypeError, ValueError, OSError):
            continue

    cached = _cached_status(target, app_schema_version=app_schema_version)
    if cached:
        return cached
    raise RuntimeError("no valid Atlas data release or warm cache is available")
