import hashlib
from pathlib import Path


from app.data import resolve_valid_release, verify_checksum


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
