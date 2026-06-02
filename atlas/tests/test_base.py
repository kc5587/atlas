from pathlib import Path

import pandas as pd
import pytest

from ingest._base import atomic_write_parquet, with_retry


def test_atomic_write_parquet_roundtrip(tmp_path: Path):
    df = pd.DataFrame({"a": [1, 2], "b": ["x", "y"]})
    out = tmp_path / "nested" / "f.parquet"
    atomic_write_parquet(df, out)
    assert out.exists()
    pd.testing.assert_frame_equal(pd.read_parquet(out), df)


def test_atomic_write_leaves_no_tmp_on_success(tmp_path: Path):
    atomic_write_parquet(pd.DataFrame({"a": [1]}), tmp_path / "f.parquet")
    assert list(tmp_path.glob("*.tmp")) == []


def test_atomic_write_no_partial_file_on_failure(tmp_path: Path, monkeypatch):
    out = tmp_path / "f.parquet"

    def boom(*a, **k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", boom)
    with pytest.raises(RuntimeError):
        atomic_write_parquet(pd.DataFrame({"a": [1]}), out)
    assert not out.exists()
    assert list(tmp_path.glob("*.tmp")) == []


def test_with_retry_succeeds_after_failures():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ValueError("transient")
        return "ok"

    assert with_retry(flaky, attempts=3, base_delay=0) == "ok"
    assert calls["n"] == 3


def test_with_retry_raises_last_error():
    def always():
        raise KeyError("nope")

    with pytest.raises(KeyError):
        with_retry(always, attempts=2, base_delay=0)
