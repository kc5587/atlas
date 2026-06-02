import hashlib
import json
from pathlib import Path

import requests

from app.data import refresh_database, resolve_valid_release, verify_checksum


def _release(tag, sha, schema="1"):
    return {
        "tag": tag,
        "manifest": {"schema_version": schema, "sha256": sha, "db_asset_url": f"http://x/{tag}.duckdb"},
    }


def test_verify_checksum_true(tmp_path: Path):
    f = tmp_path / "a.duckdb"
    f.write_bytes(b"hello")
    sha = hashlib.sha256(b"hello").hexdigest()
    assert verify_checksum(f, sha) is True


def test_verify_checksum_false(tmp_path: Path):
    f = tmp_path / "a.duckdb"
    f.write_bytes(b"hello")
    assert verify_checksum(f, "deadbeef") is False


def test_resolve_picks_newest_matching_schema():
    releases = [
        _release("data-2026-06-01T040000Z", "aaa"),
        _release("data-2026-06-02T040000Z", "bbb"),
    ]
    r = resolve_valid_release(releases, app_schema_version="1")
    assert r["tag"] == "data-2026-06-02T040000Z"


def test_resolve_skips_schema_mismatch_falls_back():
    releases = [
        _release("data-2026-06-01T040000Z", "aaa", schema="1"),
        _release("data-2026-06-02T040000Z", "bbb", schema="2"),
    ]
    r = resolve_valid_release(releases, app_schema_version="1")
    assert r["tag"] == "data-2026-06-01T040000Z"


def test_resolve_returns_none_when_no_match():
    releases = [_release("data-2026-06-02T040000Z", "bbb", schema="9")]
    assert resolve_valid_release(releases, app_schema_version="1") is None


class _Response:
    def __init__(self, *, json_data=None, content=b""):
        self._json_data = json_data
        self._content = content

    def raise_for_status(self):
        return None

    def json(self):
        return self._json_data

    def iter_content(self, chunk_size):
        yield self._content


class _Session:
    def __init__(self, responses):
        self.responses = responses

    def get(self, url, **kwargs):
        response = self.responses[url]
        if isinstance(response, Exception):
            raise response
        return response


def _api_release(tag, sha, content):
    base = f"https://github.com/kc5587/atlas/releases/download/{tag}"
    manifest = {
        "generated_at": "2026-06-02T04:00:00+00:00",
        "schema_version": "1",
        "db_asset_url": f"{base}/atlas.duckdb",
        "sha256": sha,
        "row_counts": {},
    }
    release = {
        "tag_name": tag,
        "draft": False,
        "prerelease": False,
        "assets": [
            {"name": "manifest.json", "browser_download_url": f"{base}/manifest.json"},
            {"name": "atlas.duckdb", "browser_download_url": f"{base}/atlas.duckdb"},
        ],
    }
    responses = {
        f"{base}/manifest.json": _Response(json_data=manifest),
        f"{base}/atlas.duckdb": _Response(content=content),
    }
    return release, responses


def test_refresh_database_falls_back_to_previous_valid_remote_release(tmp_path: Path):
    newest, newest_responses = _api_release("data-2026-06-02T050000Z", "bad-sha", b"bad")
    content = b"valid duckdb"
    sha = hashlib.sha256(content).hexdigest()
    previous, previous_responses = _api_release("data-2026-06-02T040000Z", sha, content)
    api_url = "https://api.github.com/repos/kc5587/atlas/releases"
    session = _Session(
        {
            api_url: _Response(json_data=[previous, newest]),
            **newest_responses,
            **previous_responses,
        }
    )

    status = refresh_database("kc5587/atlas", tmp_path / "atlas.duckdb", session=session)

    assert status.tag == "data-2026-06-02T040000Z"
    assert status.stale is True
    assert status.source == "remote"
    assert status.path.read_bytes() == content


def test_refresh_database_uses_valid_warm_cache_when_remote_is_unavailable(tmp_path: Path):
    target = tmp_path / "atlas.duckdb"
    content = b"cached duckdb"
    target.write_bytes(content)
    sha = hashlib.sha256(content).hexdigest()
    target.with_suffix(".manifest.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-06-01T04:00:00+00:00",
                "schema_version": "1",
                "db_asset_url": "https://github.com/kc5587/atlas/releases/download/old/atlas.duckdb",
                "sha256": sha,
                "row_counts": {},
                "tag": "data-2026-06-01T040000Z",
            }
        )
    )
    api_url = "https://api.github.com/repos/kc5587/atlas/releases"
    session = _Session({api_url: requests.ConnectionError("offline")})

    status = refresh_database("kc5587/atlas", target, session=session)

    assert status.tag == "data-2026-06-01T040000Z"
    assert status.stale is True
    assert status.source == "cache"


def test_refresh_database_preserves_warm_cache_when_remote_checksum_fails(tmp_path: Path):
    target = tmp_path / "atlas.duckdb"
    content = b"cached duckdb"
    target.write_bytes(content)
    sha = hashlib.sha256(content).hexdigest()
    target.with_suffix(".manifest.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-06-01T04:00:00+00:00",
                "schema_version": "1",
                "db_asset_url": "https://github.com/kc5587/atlas/releases/download/old/atlas.duckdb",
                "sha256": sha,
                "row_counts": {},
                "tag": "data-2026-06-01T040000Z",
            }
        )
    )
    newest, newest_responses = _api_release("data-2026-06-02T050000Z", "bad-sha", b"bad")
    api_url = "https://api.github.com/repos/kc5587/atlas/releases"
    session = _Session({api_url: _Response(json_data=[newest]), **newest_responses})

    status = refresh_database("kc5587/atlas", target, session=session)

    assert status.source == "cache"
    assert target.read_bytes() == content
