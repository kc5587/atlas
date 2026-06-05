from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from config import DATA_RAW, DUCKDB_PATH

SCHEMA_VERSION = "1"
KEEP_RELEASES = 14
# Tables whose row counts go into the manifest (skipped silently if absent).
ROW_COUNT_TABLES = [
    "prices_daily",
    "returns",
    "macro_daily",
    "graph_nodes",
    "graph_edges",
    "leadlag",
    "stg_fundamentals",
    "fundamentals_quarterly",
    "iv_snapshots",
]


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _row_counts(db: Path) -> dict[str, int]:
    con = duckdb.connect(str(db), read_only=True)
    counts: dict[str, int] = {}
    try:
        for t in ROW_COUNT_TABLES:
            try:
                counts[t] = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            except duckdb.CatalogException:
                continue
    finally:
        con.close()
    return counts


def _repo() -> str:
    repo = os.environ.get("GITHUB_REPOSITORY")
    if repo:
        return repo
    return subprocess.run(
        ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def main() -> None:
    db = Path(DUCKDB_PATH)
    if not db.exists():
        raise SystemExit("no duckdb to publish")

    tag = "data-" + datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    sha = _sha256(db)
    repo = _repo()
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema_version": SCHEMA_VERSION,
        "db_asset_url": f"https://github.com/{repo}/releases/download/{tag}/atlas.duckdb",
        "sha256": sha,
        "row_counts": _row_counts(db),
    }
    Path("manifest.json").write_text(json.dumps(manifest, indent=2))
    panel = Path(DATA_RAW) / "iv_snapshots" / "panel.parquet"
    assets = [str(db), "manifest.json"]
    if panel.exists():
        assets.append(str(panel))

    # 1) create as DRAFT, 2) upload all assets to the draft
    subprocess.run(
        ["gh", "release", "create", tag, *assets,
         "--draft", "--title", tag, "--notes", "automated data release"],
        check=True,
    )

    # 3) download the uploaded asset back from the draft and verify its sha256
    #    against the manifest BEFORE publishing. Abort (leaving only the draft) on mismatch.
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(
            ["gh", "release", "download", tag, "--pattern", "atlas.duckdb", "--dir", tmp],
            check=True,
        )
        downloaded_sha = _sha256(Path(tmp) / "atlas.duckdb")
        if downloaded_sha != sha:
            raise SystemExit(
                f"checksum mismatch for uploaded asset ({downloaded_sha} != {sha}); "
                f"leaving draft {tag} unpublished"
            )

    # 4) verification passed -> publish the draft
    subprocess.run(["gh", "release", "edit", tag, "--draft=false"], check=True)

    # retention: delete ENTIRE old releases (release + tag + all assets), keep last N
    out = subprocess.run(
        ["gh", "release", "list", "--limit", "100"],
        check=True, capture_output=True, text=True,
    ).stdout.splitlines()
    data_tags = sorted(
        line.split("\t")[0] for line in out if line.split("\t")[0].startswith("data-")
    )
    for old in data_tags[:-KEEP_RELEASES]:
        subprocess.run(["gh", "release", "delete", old, "--cleanup-tag", "--yes"], check=True)


if __name__ == "__main__":
    main()
