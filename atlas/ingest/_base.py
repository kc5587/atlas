from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Callable, TypeVar

import pandas as pd

T = TypeVar("T")


def atomic_write_parquet(df: pd.DataFrame, path: str | Path) -> None:
    """Write a DataFrame to parquet atomically (temp file + rename).

    Nothing is written at `path` if serialization fails.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".parquet.tmp")
    os.close(fd)
    try:
        df.to_parquet(tmp, index=False)
        os.replace(tmp, path)  # atomic on same filesystem
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def with_retry(fn: Callable[[], T], *, attempts: int = 3, base_delay: float = 1.0) -> T:
    """Call `fn`, retrying with exponential backoff. Re-raises the last error."""
    last: Exception | None = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - retry boundary
            last = exc
            if i < attempts - 1:
                time.sleep(base_delay * (2**i))
    assert last is not None
    raise last
