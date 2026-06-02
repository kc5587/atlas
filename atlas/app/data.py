from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional


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
