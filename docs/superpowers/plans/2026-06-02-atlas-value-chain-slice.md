# Atlas v2 — First Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a reproducible, clone-and-run AI-value-chain research engine that ingests daily prices + macro from free sources, models them with dbt-duckdb, maps a supplier→customer graph, computes autocorrelation-aware lead/lag relationships, and presents an interactive map + dashboard + report in Streamlit — refreshed nightly via immutable GitHub data releases.

**Architecture:** Lean, single-machine. Idempotent Python ingestion writes partitioned Parquet → dbt-duckdb cleans into marts → a validated YAML loader populates graph tables (consumed by dbt as sources) → an analysis module computes lead/lag with block-bootstrap p-values + BH-FDR → a Streamlit app reads DuckDB. GitHub Actions runs CI (secret-scan + tests + dbt build) and a nightly job that publishes an immutable date-tagged DuckDB release the app fetches and checksum-validates.

**Tech Stack:** Python ≥3.11 (3.13 pinned in dev/CI), uv, yfinance, pandas-datareader (FRED, no API key), pandera, pandas/pyarrow, DuckDB, dbt-duckdb, PyYAML + pydantic, networkx, numpy/scipy, plotly, Streamlit, requests (FRED CSV, no API key), pytest/pytest-cov, gitleaks (CI), GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-06-02-atlas-value-chain-design.md`

---

## File Structure

All new code lives in a fresh top-level `atlas/` package (clean-room — no v1 code reused).

```
atlas/
  pyproject.toml                 # deps + tooling config (ruff, pytest, coverage)
  .python-version                # pins dev/CI interpreter to 3.13 (floor is >=3.11)
  Makefile                       # setup / ingest / build / analyze / app / all
  .gitignore                     # repo-wide denylist (Phase 0)
  .gitleaks.toml                 # secret-scan config (Phase 0)
  README.md                      # narrative + live demo link + non-goals
  config.py                      # constants: universe, FRED series, windows, paths
  ingest/
    __init__.py
    _base.py                     # atomic_write_parquet, with_retry
    schemas.py                   # pandera schemas: PRICE_SCHEMA, MACRO_SCHEMA
    prices.py                    # yfinance -> data/raw/prices/*.parquet
    macro.py                     # FRED    -> data/raw/macro/*.parquet
    graph.py                     # validate value_chain.yml -> duckdb graph tables
  seeds/
    value_chain.yml              # nodes + edges (single source of truth)
  analysis/
    __init__.py
    leadlag.py                   # returns, alignment, xcorr, bootstrap p, BH-FDR, stability
  app/
    streamlit_app.py             # 3 tabs: map | dashboard | report
    data.py                      # release resolution + checksum verify + fallback
  reports/
    report.md                    # narrative (plain markdown; read by the app)
  dbt_project/
    dbt_project.yml
    profiles.yml                 # duckdb profile (path from env)
    models/
      staging/stg_prices.sql
      staging/stg_macro.sql
      staging/schema.yml         # staging tests
      marts/prices_daily.sql
      marts/returns.sql
      marts/macro_daily.sql
      marts/schema.yml           # mart tests
      graph/sources.yml          # graph_nodes/graph_edges as dbt sources
      graph/graph_nodes.sql
      graph/graph_edges.sql
  tests/
    test_base.py
    test_schemas.py
    test_prices.py
    test_macro.py
    test_graph.py
    test_leadlag.py
    test_app_data.py
    fixtures/                    # tiny CSV/parquet fixtures for CI smoke test
  .github/workflows/
    ci.yml
    update-data.yml
```

**Naming contracts (used across tasks — keep stable):**
- Price long-format columns: `ticker, date, open, high, low, close, adj_close, volume`
- Macro long-format columns: `series_id, date, value`
- Graph node columns: `id, name, tickers (list->json string), stage, region`
- Graph edge columns: `from_id, to_id, relationship, note, evidence, as_of`
- Lead/lag table columns: `pair_type, left, right, lag, corr, p_value, q_value, n_eff, stable`

---

## Phase 0 — Public-Release Security Gate (BLOCKING)

> No public push / tag / v1 archive until this phase passes. These steps operate on the repo root (`/Users/kaushalchitturu/Data_Quant_project`), not yet inside `atlas/`.

### Task 0.1: Add repo-wide `.gitignore` denylist

**Files:**
- Create: `.gitignore`

- [ ] **Step 1: Create `.gitignore`**

```gitignore
# secrets / keys
.env
*.env
!.env.example
*.pem
ssh_key
ssh_key.pub
*.key

# data / db / logs (regenerated from source)
data/
*.duckdb
*.duckdb.wal
*.parquet
logs/
*.log

# committed CI test fixtures (override the broad *.parquet rule above)
!atlas/tests/fixtures/
!atlas/tests/fixtures/**/
!atlas/tests/fixtures/**/*.parquet

# python
__pycache__/
*.pyc
.venv/
.pytest_cache/
.coverage
htmlcov/

# dbt
dbt_project/target/
dbt_project/dbt_packages/
dbt_project/logs/
dbt_project/.user.yml

# os
.DS_Store
```

- [ ] **Step 2: Verify the denylist rules match these paths**

`git check-ignore` stays silent for files already in the index (tracked files override
`.gitignore`), and `.env` + the DuckDB are still tracked at this point — so use
`--no-index` to test rule coverage independent of tracked status.

Run: `git check-ignore -v --no-index ai-value-chain-data/.env ssh_key ai-value-chain-data/data/atlas.duckdb`
Expected: each path prints a matching `.gitignore` rule. (Task 0.2 then removes the
tracked ones from the index, after which plain `git check-ignore` would also report them.)

- [ ] **Step 3: Commit**

```bash
git add .gitignore
git commit -m "chore: add repo-wide secret/data denylist"
```

### Task 0.2: Remove tracked secrets/data from the index (keep on disk)

**Files:**
- Modify: git index (untrack `ai-value-chain-data/.env`, tracked `*.duckdb`, tracked logs)

- [ ] **Step 1: Untrack secrets and regenerated data (does not delete working-tree files)**

```bash
git rm --cached ai-value-chain-data/.env
git rm --cached -r --ignore-unmatch ai-value-chain-data/logs
git rm --cached --ignore-unmatch ai-value-chain-data/data/atlas.duckdb
```

- [ ] **Step 2: Verify they are no longer tracked**

Run: `git ls-files | grep -E '\.env$|\.duckdb$|/logs/'`
Expected: no output.

- [ ] **Step 3: Commit ONLY the staged removals — do NOT `git add -A`**

The `git rm --cached` in Step 1 already staged exactly the intended deletions. Running
`git add -A` here would sweep in unrelated pre-existing v1 working-tree edits and
untracked files. Commit the staged index as-is:

```bash
git commit -m "chore: untrack secrets, db, and logs"
```

### Task 0.3: Credential audit with gitleaks (working tree + full history)

**Files:**
- Create: `.gitleaks.toml`

- [ ] **Step 1: Create gitleaks config**

```toml
title = "atlas gitleaks config"
[extend]
useDefault = true

[allowlist]
description = "non-secret example files"
paths = ['''\.env\.example$''', '''docs/.*''']
```

- [ ] **Step 2: Scan the working tree**

Run: `gitleaks detect --no-git --config .gitleaks.toml --redact -v`
Expected: exit 0, "no leaks found". If leaks: record them in `SECURITY_AUDIT.md` (created below) and remove the offending values before proceeding.

- [ ] **Step 3: Scan full git history**

Run: `gitleaks detect --config .gitleaks.toml --redact -v`
Expected: list of every secret ever committed (we expect `.env` hits historically). Capture the output.

- [ ] **Step 4: Write the audit record**

Create `SECURITY_AUDIT.md` listing every credential found (type, file, redacted), with a column for "rotated? (y/n)" and the history-scrub decision.

- [ ] **Step 5: Commit**

```bash
git add .gitleaks.toml SECURITY_AUDIT.md
git commit -m "chore: add gitleaks config and credential audit record"
```

### Task 0.4: Rotate every credential ever committed + record history-scrub decision

**Files:**
- Modify: `SECURITY_AUDIT.md`

- [ ] **Step 1: Rotate (human action — list in audit)**

For each credential in `SECURITY_AUDIT.md`: rotate it at the provider (DB password, any API keys, regenerate the SSH keypair), mark "rotated? = y". Rotation is required even if history is scrubbed — committed = compromised.

- [ ] **Step 2: Record the history-scrub decision**

In `SECURITY_AUDIT.md`, choose and document **(b) start the public repo from fresh history** (recommended — aligns with the clean-room rebuild and avoids `filter-repo` surgery on the messy v1 log). State that the public repo will be initialized from the post-cleanup tree with a single root commit; the current private repo is retained as the historical record.

- [ ] **Step 3: Commit**

```bash
git add SECURITY_AUDIT.md
git commit -m "docs: record credential rotation and fresh-history decision"
```

### Task 0.5: Verification gate

- [ ] **Step 1: Re-scan the exact tree to be published**

Run: `gitleaks detect --no-git --config .gitleaks.toml --redact -v`
Expected: exit 0, no leaks. This must be green before any public push/tag/v1 archive.

---

## Phase 1 — Fresh `atlas/` scaffold

### Task 1.1: Package metadata and dependencies

**Files:**
- Create: `atlas/pyproject.toml`

- [ ] **Step 1: Create `atlas/pyproject.toml`**

```toml
[build-system]
requires = ["setuptools>=61"]
build-backend = "setuptools.build_meta"

[project]
name = "atlas"
version = "0.1.0"
description = "AI value-chain research engine"
requires-python = ">=3.11"
dependencies = [
  "yfinance>=0.2.40",
  "pandas>=2.2",
  "pyarrow>=16",
  "pandera>=0.20",
  "duckdb>=1.0",
  "dbt-duckdb>=1.8",
  "pyyaml>=6",
  "pydantic>=2.7",
  "networkx>=3.3",
  "numpy>=1.26",
  "scipy>=1.13",
  "plotly>=5.22",
  "streamlit>=1.36",
  "requests>=2.32",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-cov>=5", "ruff>=0.5"]

# Explicit discovery: `config` is a top-level module; ingest/analysis/app are packages.
# Without this, setuptools flat-layout auto-discovery fails once >1 top-level package exists.
[tool.setuptools]
py-modules = ["config"]

[tool.setuptools.packages.find]
include = ["ingest*", "analysis*", "app*"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.pytest.ini_options]
addopts = "-q"
pythonpath = ["."]
testpaths = ["tests"]

[tool.coverage.run]
source = ["ingest", "analysis", "app"]
# streamlit_app.py is UI glue (no unit tests by design); tests are not self-measured.
omit = ["tests/*", "app/streamlit_app.py"]

[tool.coverage.report]
# IO/orchestration boundaries are exercised via the integration (make all / dbt fixture
# build), not unit tests. Mark them `# pragma: no cover`; also exclude __main__ guards.
exclude_also = [
  "if __name__ == .__main__.:",
  "# pragma: no cover",
]
```

> **Coverage policy:** the 80% gate measures *library logic* (normalization, schemas, graph
> loading, lead/lag math, app data resolution) — all unit-tested. Network `fetch_*` functions
> and the per-module `run()` orchestrators are IO boundaries; mark each with a trailing
> `# pragma: no cover` on the `def` line so they're excluded from the gate.

- [ ] **Step 2: Pin the interpreter, create env, and install**

`requires-python = ">=3.11"` is the floor; for deterministic clone-and-run we pin the dev/CI
interpreter to 3.13 via a committed `.python-version` (uv auto-downloads it if absent).

Run: `cd atlas && uv python pin 3.13 && uv venv && uv pip install -e ".[dev]"`
Expected: `.python-version` created with `3.13`, `.venv` on Python 3.13.x, install completes
with no resolver errors. (If a `.venv` from an earlier run exists on a different version,
delete it first: `rm -rf .venv` then re-run.)

- [ ] **Step 3: Commit**

```bash
git add atlas/pyproject.toml atlas/.python-version
git commit -m "feat: scaffold atlas package metadata and deps"
```

### Task 1.2: Config constants and package init files

**Files:**
- Create: `atlas/config.py`, `atlas/ingest/__init__.py`, `atlas/analysis/__init__.py`

- [ ] **Step 1: Create `atlas/config.py`**

```python
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_RAW = ROOT / "data" / "raw"
DUCKDB_PATH = ROOT / "data" / "atlas.duckdb"
SEED_PATH = ROOT / "seeds" / "value_chain.yml"

# Core spine universe (curated; extend in value_chain.yml too).
UNIVERSE: list[str] = [
    "ASML", "TSM", "NVDA", "AMD", "AVGO", "MU", "AMAT", "LRCX",
    "MSFT", "GOOGL", "AMZN", "META", "ORCL", "DELL", "SMCI",
]

# FRED series id -> human label. Native frequency handled at analysis time.
FRED_SERIES: dict[str, str] = {
    "DFF": "Effective Fed Funds Rate",
    "DGS10": "10Y Treasury Yield",
    "IPG3344S": "Semiconductor & Components IP Index",
}

PRICE_START = "2010-01-01"

# Lead/lag analysis windows.
MAX_LAG_DAYS = 20
PRICE_NMIN = 250
MACRO_NMIN = 36
TRAILING_YEARS = 3
BOOTSTRAP_ITERS = 1000
BOOTSTRAP_BLOCK = 20
FDR_ALPHA = 0.10
RANDOM_SEED = 7
```

- [ ] **Step 2: Create empty package markers**

```bash
mkdir -p atlas/ingest atlas/analysis
printf '' > atlas/ingest/__init__.py
printf '' > atlas/analysis/__init__.py
```

- [ ] **Step 3: Commit**

```bash
git add atlas/config.py atlas/ingest/__init__.py atlas/analysis/__init__.py
git commit -m "feat: add atlas config constants and package markers"
```

### Task 1.3: Makefile

**Files:**
- Create: `atlas/Makefile`

- [ ] **Step 1: Create `atlas/Makefile`**

```makefile
.PHONY: setup ingest build analyze app all test lint

setup:
	uv venv && uv pip install -e ".[dev]"

ingest:
	python -m ingest.prices && python -m ingest.macro && python -m ingest.graph

build:
	cd dbt_project && dbt build --profiles-dir .

analyze:
	python -m analysis.leadlag

app:
	streamlit run app/streamlit_app.py

all: ingest build analyze

test:
	pytest --cov --cov-report=term-missing

lint:
	ruff check .
```

- [ ] **Step 2: Verify make targets parse**

Run: `cd atlas && make -n all`
Expected: prints the ingest/build/analyze commands without executing.

- [ ] **Step 3: Commit**

```bash
git add atlas/Makefile
git commit -m "feat: add atlas Makefile"
```

---

## Phase 2 — Ingest foundation (`_base.py`, schemas)

### Task 2.1: Atomic parquet write + retry helper

**Files:**
- Create: `atlas/ingest/_base.py`
- Test: `atlas/tests/test_base.py`

- [ ] **Step 1: Write the failing test**

```python
# atlas/tests/test_base.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlas && pytest tests/test_base.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ingest._base'`.

- [ ] **Step 3: Write minimal implementation**

```python
# atlas/ingest/_base.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd atlas && pytest tests/test_base.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add atlas/ingest/_base.py atlas/tests/test_base.py
git commit -m "feat: atomic parquet write + retry helper with tests"
```

### Task 2.2: Pandera validation schemas

**Files:**
- Create: `atlas/ingest/schemas.py`
- Test: `atlas/tests/test_schemas.py`

- [ ] **Step 1: Write the failing test**

```python
# atlas/tests/test_schemas.py
import pandas as pd
import pandera.errors
import pytest

from ingest.schemas import MACRO_SCHEMA, PRICE_SCHEMA


def _valid_prices() -> pd.DataFrame:
    return pd.DataFrame({
        "ticker": ["NVDA"],
        "date": pd.to_datetime(["2024-01-02"]),
        "open": [1.0], "high": [2.0], "low": [0.5],
        "close": [1.5], "adj_close": [1.5], "volume": [100],
    })


def test_price_schema_accepts_valid():
    PRICE_SCHEMA.validate(_valid_prices())


def test_price_schema_rejects_negative_close():
    bad = _valid_prices()
    bad.loc[0, "close"] = -1.0
    with pytest.raises(pandera.errors.SchemaError):
        PRICE_SCHEMA.validate(bad)


def test_price_schema_rejects_null_close():
    bad = _valid_prices()
    bad.loc[0, "close"] = None
    with pytest.raises(pandera.errors.SchemaError):
        PRICE_SCHEMA.validate(bad)


def test_macro_schema_accepts_valid():
    df = pd.DataFrame({
        "series_id": ["DFF"],
        "date": pd.to_datetime(["2024-01-01"]),
        "value": [5.33],
    })
    MACRO_SCHEMA.validate(df)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlas && pytest tests/test_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ingest.schemas'`.

- [ ] **Step 3: Write minimal implementation**

```python
# atlas/ingest/schemas.py
from __future__ import annotations

import pandera.pandas as pa

PRICE_SCHEMA = pa.DataFrameSchema(
    {
        "ticker": pa.Column(str, nullable=False),
        "date": pa.Column("datetime64[ns]", nullable=False),
        "open": pa.Column(float, pa.Check.ge(0), nullable=True),
        "high": pa.Column(float, pa.Check.ge(0), nullable=True),
        "low": pa.Column(float, pa.Check.ge(0), nullable=True),
        "close": pa.Column(float, pa.Check.ge(0), nullable=False),
        "adj_close": pa.Column(float, pa.Check.ge(0), nullable=False),
        "volume": pa.Column("int64", pa.Check.ge(0), nullable=True, coerce=True),
    },
    strict=True,
)

MACRO_SCHEMA = pa.DataFrameSchema(
    {
        "series_id": pa.Column(str, nullable=False),
        "date": pa.Column("datetime64[ns]", nullable=False),
        "value": pa.Column(float, nullable=False),
    },
    strict=True,
)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd atlas && pytest tests/test_schemas.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add atlas/ingest/schemas.py atlas/tests/test_schemas.py
git commit -m "feat: pandera price/macro schemas with tests"
```

---

## Phase 3 — Price ingestion

### Task 3.1: Normalize yfinance output to validated long format

**Files:**
- Create: `atlas/ingest/prices.py`
- Test: `atlas/tests/test_prices.py`

- [ ] **Step 1: Write the failing test**

```python
# atlas/tests/test_prices.py
import pandas as pd

from ingest.prices import normalize_prices


def _raw_yf() -> pd.DataFrame:
    # Mimics yfinance single-ticker frame: DatetimeIndex + OHLCV columns.
    idx = pd.to_datetime(["2024-01-02", "2024-01-03"])
    return pd.DataFrame(
        {
            "Open": [1.0, 1.1],
            "High": [2.0, 2.1],
            "Low": [0.5, 0.6],
            "Close": [1.5, 1.6],
            "Adj Close": [1.4, 1.5],
            "Volume": [100, 200],
        },
        index=idx,
    )


def test_normalize_prices_long_format():
    out = normalize_prices(_raw_yf(), "NVDA")
    assert list(out.columns) == [
        "ticker", "date", "open", "high", "low", "close", "adj_close", "volume",
    ]
    assert out["ticker"].unique().tolist() == ["NVDA"]
    assert len(out) == 2
    assert out["volume"].dtype == "int64"


def test_normalize_prices_drops_all_nan_rows():
    raw = _raw_yf()
    raw.loc[raw.index[1], ["Open", "High", "Low", "Close", "Adj Close", "Volume"]] = None
    out = normalize_prices(raw, "NVDA")
    assert len(out) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlas && pytest tests/test_prices.py -v`
Expected: FAIL — cannot import `normalize_prices`.

- [ ] **Step 3: Write minimal implementation**

```python
# atlas/ingest/prices.py
from __future__ import annotations

from pathlib import Path

import pandas as pd
import yfinance as yf

from config import DATA_RAW, PRICE_START, UNIVERSE
from ingest._base import atomic_write_parquet, with_retry
from ingest.schemas import PRICE_SCHEMA

_COLUMN_MAP = {
    "Open": "open",
    "High": "high",
    "Low": "low",
    "Close": "close",
    "Adj Close": "adj_close",
    "Volume": "volume",
}


def normalize_prices(raw: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Convert a yfinance OHLCV frame into validated long format."""
    df = raw.rename(columns=_COLUMN_MAP).copy()
    df = df[[c for c in _COLUMN_MAP.values() if c in df.columns]]
    df = df.dropna(how="all")
    df.insert(0, "date", pd.to_datetime(df.index))
    df.insert(0, "ticker", ticker)
    df = df.reset_index(drop=True)
    df["volume"] = df["volume"].fillna(0).astype("int64")
    df["date"] = df["date"].dt.tz_localize(None)
    return PRICE_SCHEMA.validate(df)


def fetch_prices(ticker: str, start: str = PRICE_START) -> pd.DataFrame:
    """Download one ticker's daily history (retried)."""
    def _dl() -> pd.DataFrame:
        raw = yf.download(ticker, start=start, auto_adjust=False, progress=False)
        if raw.empty:
            raise RuntimeError(f"empty download for {ticker}")
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        return raw

    return normalize_prices(with_retry(_dl), ticker)


def run(tickers: list[str] | None = None) -> None:
    tickers = tickers or UNIVERSE
    out_dir = Path(DATA_RAW) / "prices"
    for t in tickers:
        df = fetch_prices(t)
        atomic_write_parquet(df, out_dir / f"{t}.parquet")
        print(f"prices: wrote {len(df)} rows for {t}")


if __name__ == "__main__":
    run()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd atlas && pytest tests/test_prices.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add atlas/ingest/prices.py atlas/tests/test_prices.py
git commit -m "feat: price ingestion (yfinance) with normalization tests"
```

---

## Phase 4 — Macro ingestion

### Task 4.1: Normalize FRED output to validated long format

**Files:**
- Create: `atlas/ingest/macro.py`
- Test: `atlas/tests/test_macro.py`

- [ ] **Step 1: Write the failing test**

```python
# atlas/tests/test_macro.py
import pandas as pd

from ingest.macro import _csv_to_indexed_frame, normalize_macro


def test_csv_to_indexed_frame_parses_and_handles_missing():
    # FRED encodes missing observations as '.'
    csv = "DATE,DFF\n2024-01-01,5.33\n2024-01-02,.\n2024-01-03,5.40\n"
    frame = _csv_to_indexed_frame(csv, "DFF")
    assert list(frame.columns) == ["DFF"]
    assert len(frame) == 3
    assert pd.isna(frame["DFF"].iloc[1])
    # downstream normalize drops the missing row
    out = normalize_macro(frame, "DFF")
    assert len(out) == 2


def test_normalize_macro_long_format():
    raw = pd.DataFrame(
        {"DFF": [5.33, 5.33]},
        index=pd.to_datetime(["2024-01-01", "2024-01-02"]),
    )
    out = normalize_macro(raw, "DFF")
    assert list(out.columns) == ["series_id", "date", "value"]
    assert out["series_id"].unique().tolist() == ["DFF"]
    assert len(out) == 2


def test_normalize_macro_drops_nan_values():
    raw = pd.DataFrame(
        {"DGS10": [4.0, None]},
        index=pd.to_datetime(["2024-01-01", "2024-01-02"]),
    )
    out = normalize_macro(raw, "DGS10")
    assert len(out) == 1
    assert out["value"].iloc[0] == 4.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlas && pytest tests/test_macro.py -v`
Expected: FAIL — cannot import `normalize_macro`.

- [ ] **Step 3: Write minimal implementation**

```python
# atlas/ingest/macro.py
from __future__ import annotations

import io
from pathlib import Path

import pandas as pd
import requests

from config import DATA_RAW, FRED_SERIES, PRICE_START
from ingest._base import atomic_write_parquet, with_retry
from ingest.schemas import MACRO_SCHEMA

# FRED's public CSV endpoint — no API key required.
FRED_CSV_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv"


def normalize_macro(raw: pd.DataFrame, series_id: str) -> pd.DataFrame:
    """Convert a single-column, date-indexed FRED frame into validated long format."""
    s = raw[series_id] if series_id in raw.columns else raw.iloc[:, 0]
    df = pd.DataFrame(
        {
            "series_id": series_id,
            "date": pd.to_datetime(s.index).tz_localize(None),
            "value": pd.to_numeric(s.values, errors="coerce"),
        }
    )
    df = df.dropna(subset=["value"]).reset_index(drop=True)
    df["value"] = df["value"].astype(float)
    return MACRO_SCHEMA.validate(df)


def _csv_to_indexed_frame(text: str, series_id: str) -> pd.DataFrame:
    """Parse a fredgraph CSV (DATE,<series>) into a date-indexed single-column frame.

    FRED encodes missing observations as '.'; convert those to NaN.
    """
    df = pd.read_csv(io.StringIO(text))
    if df.shape[1] < 2 or df.empty:
        raise RuntimeError(f"unexpected FRED CSV shape for {series_id}")
    date_col, val_col = df.columns[0], df.columns[1]
    df = df.rename(columns={val_col: series_id})
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.set_index(date_col)
    df[series_id] = pd.to_numeric(df[series_id].replace(".", pd.NA), errors="coerce")
    return df[[series_id]]


def fetch_macro(series_id: str, start: str = PRICE_START) -> pd.DataFrame:
    def _dl() -> pd.DataFrame:
        resp = requests.get(
            FRED_CSV_URL, params={"id": series_id, "cosd": start}, timeout=30
        )
        resp.raise_for_status()
        frame = _csv_to_indexed_frame(resp.text, series_id)
        if frame.empty:
            raise RuntimeError(f"empty FRED download for {series_id}")
        return frame

    return normalize_macro(with_retry(_dl), series_id)


def run() -> None:
    out_dir = Path(DATA_RAW) / "macro"
    for series_id in FRED_SERIES:
        df = fetch_macro(series_id)
        atomic_write_parquet(df, out_dir / f"{series_id}.parquet")
        print(f"macro: wrote {len(df)} rows for {series_id}")


if __name__ == "__main__":
    run()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd atlas && pytest tests/test_macro.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add atlas/ingest/macro.py atlas/tests/test_macro.py
git commit -m "feat: macro ingestion (FRED) with normalization tests"
```

---

## Phase 5 — Value-chain graph loader

### Task 5.1: Seed file `value_chain.yml`

**Files:**
- Create: `atlas/seeds/value_chain.yml`

- [ ] **Step 1: Create the seed (core spine excerpt — extend as needed)**

```yaml
nodes:
  - id: asml
    name: ASML Holding
    tickers: [ASML]
    stage: equipment
    region: NL
  - id: tsmc
    name: TSMC
    tickers: [TSM]
    stage: foundry
    region: TW
  - id: nvidia
    name: NVIDIA
    tickers: [NVDA]
    stage: chips
    region: US
  - id: microsoft
    name: Microsoft
    tickers: [MSFT]
    stage: cloud
    region: US
edges:
  - from: asml
    to: tsmc
    relationship: supplies
    note: EUV lithography systems
    evidence: "ASML FY2023 20-F"
    as_of: 2024-01-01
  - from: tsmc
    to: nvidia
    relationship: supplies
    note: Advanced-node wafer fabrication
    evidence: "NVDA 10-K supplier concentration"
    as_of: 2024-01-01
  - from: nvidia
    to: microsoft
    relationship: supplies
    note: Data-center GPUs
    evidence: "MSFT capex commentary FY2024"
    as_of: 2024-01-01
```

- [ ] **Step 2: Commit**

```bash
git add atlas/seeds/value_chain.yml
git commit -m "feat: add value-chain seed for core spine"
```

### Task 5.2: Validated YAML → DuckDB graph loader

**Files:**
- Create: `atlas/ingest/graph.py`
- Test: `atlas/tests/test_graph.py`

- [ ] **Step 1: Write the failing test**

```python
# atlas/tests/test_graph.py
import duckdb
import pytest

from ingest.graph import load_graph, write_graph_to_duckdb

VALID = """
nodes:
  - id: asml
    name: ASML
    tickers: [ASML]
    stage: equipment
    region: NL
  - id: tsmc
    name: TSMC
    tickers: [TSM, 2330.TW]
    stage: foundry
    region: TW
edges:
  - from: asml
    to: tsmc
    relationship: supplies
    note: EUV
    evidence: "20-F"
    as_of: 2024-01-01
"""

EDGE_TO_MISSING = """
nodes:
  - id: asml
    name: ASML
    tickers: [ASML]
    stage: equipment
    region: NL
edges:
  - from: asml
    to: ghost
    relationship: supplies
    note: x
    evidence: y
    as_of: 2024-01-01
"""

DUP_ID = """
nodes:
  - id: asml
    name: ASML
    tickers: [ASML]
    stage: equipment
    region: NL
  - id: asml
    name: Dup
    tickers: [DUP]
    stage: chips
    region: US
edges: []
"""


def test_load_graph_returns_nodes_and_edges(tmp_path):
    p = tmp_path / "g.yml"
    p.write_text(VALID)
    nodes, edges = load_graph(p)
    assert set(nodes.columns) == {"id", "name", "tickers", "stage", "region"}
    assert set(edges.columns) == {
        "from_id", "to_id", "relationship", "note", "evidence", "as_of",
    }
    assert nodes.loc[nodes["id"] == "tsmc", "tickers"].iloc[0] == '["TSM", "2330.TW"]'


def test_edge_referencing_missing_node_raises(tmp_path):
    p = tmp_path / "g.yml"
    p.write_text(EDGE_TO_MISSING)
    with pytest.raises(ValueError, match="unknown node"):
        load_graph(p)


def test_duplicate_node_id_raises(tmp_path):
    p = tmp_path / "g.yml"
    p.write_text(DUP_ID)
    with pytest.raises(ValueError, match="duplicate node id"):
        load_graph(p)


def test_write_graph_to_duckdb(tmp_path):
    p = tmp_path / "g.yml"
    p.write_text(VALID)
    nodes, edges = load_graph(p)
    con = duckdb.connect(str(tmp_path / "t.duckdb"))
    write_graph_to_duckdb(con, nodes, edges)
    assert con.execute("SELECT count(*) FROM graph_nodes").fetchone()[0] == 2
    assert con.execute("SELECT count(*) FROM graph_edges").fetchone()[0] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlas && pytest tests/test_graph.py -v`
Expected: FAIL — cannot import `ingest.graph`.

- [ ] **Step 3: Write minimal implementation**

```python
# atlas/ingest/graph.py
from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import duckdb
import pandas as pd
import yaml
from pydantic import BaseModel, field_validator

Stage = Literal["equipment", "foundry", "chips", "cloud"]


class Node(BaseModel):
    id: str
    name: str
    tickers: list[str]
    stage: Stage
    region: str

    @field_validator("tickers")
    @classmethod
    def _non_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("node must have at least one ticker")
        return v


class Edge(BaseModel):
    from_id: str
    to_id: str
    relationship: Literal["supplies", "partner"]
    note: str = ""
    evidence: str = ""
    as_of: str


def load_graph(yaml_path: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validate the value-chain YAML and return (nodes_df, edges_df).

    Raises ValueError on duplicate node ids or edges referencing unknown nodes.
    """
    data = yaml.safe_load(Path(yaml_path).read_text())
    raw_nodes = data.get("nodes", []) or []
    raw_edges = data.get("edges", []) or []

    nodes = [Node(**n) for n in raw_nodes]
    ids = [n.id for n in nodes]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate node id in seed")
    id_set = set(ids)

    edges: list[Edge] = []
    for e in raw_edges:
        edge = Edge(
            from_id=e["from"],
            to_id=e["to"],
            relationship=e["relationship"],
            note=e.get("note", ""),
            evidence=e.get("evidence", ""),
            as_of=str(e["as_of"]),
        )
        for endpoint in (edge.from_id, edge.to_id):
            if endpoint not in id_set:
                raise ValueError(f"edge references unknown node: {endpoint}")
        edges.append(edge)

    nodes_df = pd.DataFrame(
        [
            {
                "id": n.id,
                "name": n.name,
                "tickers": json.dumps(n.tickers),
                "stage": n.stage,
                "region": n.region,
            }
            for n in nodes
        ],
        columns=["id", "name", "tickers", "stage", "region"],
    )
    edges_df = pd.DataFrame(
        [e.model_dump() for e in edges],
        columns=["from_id", "to_id", "relationship", "note", "evidence", "as_of"],
    )
    return nodes_df, edges_df


def write_graph_to_duckdb(
    con: duckdb.DuckDBPyConnection, nodes: pd.DataFrame, edges: pd.DataFrame
) -> None:
    con.register("nodes_df", nodes)
    con.register("edges_df", edges)
    con.execute("CREATE OR REPLACE TABLE graph_nodes AS SELECT * FROM nodes_df")
    con.execute("CREATE OR REPLACE TABLE graph_edges AS SELECT * FROM edges_df")
    con.unregister("nodes_df")
    con.unregister("edges_df")


def run() -> None:
    from config import DUCKDB_PATH, SEED_PATH

    nodes, edges = load_graph(SEED_PATH)
    Path(DUCKDB_PATH).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DUCKDB_PATH))
    write_graph_to_duckdb(con, nodes, edges)
    con.close()
    print(f"graph: wrote {len(nodes)} nodes, {len(edges)} edges")


if __name__ == "__main__":
    run()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd atlas && pytest tests/test_graph.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add atlas/ingest/graph.py atlas/tests/test_graph.py
git commit -m "feat: validated YAML graph loader -> duckdb tables"
```

---

## Phase 6 — dbt-duckdb modeling

### Task 6.1: dbt project, profile, and sources

**Files:**
- Create: `atlas/dbt_project/dbt_project.yml`, `atlas/dbt_project/profiles.yml`, `atlas/dbt_project/models/graph/sources.yml`

- [ ] **Step 1: Create `dbt_project.yml`**

```yaml
name: atlas
version: "1.0"
profile: atlas
model-paths: ["models"]
models:
  atlas:
    staging:
      +materialized: view
    marts:
      +materialized: table
    graph:
      +materialized: table
```

- [ ] **Step 2: Create `profiles.yml`**

```yaml
atlas:
  target: dev
  outputs:
    dev:
      type: duckdb
      path: "{{ env_var('ATLAS_DUCKDB_PATH', '../data/atlas.duckdb') }}"
      extensions: []
      external_root: "{{ env_var('ATLAS_DATA_RAW', '../data/raw') }}"
```

- [ ] **Step 3: Create `models/graph/sources.yml`**

```yaml
version: 2
sources:
  - name: graph
    schema: main
    tables:
      - name: graph_nodes
      - name: graph_edges
```

- [ ] **Step 4: Commit**

```bash
git add atlas/dbt_project/dbt_project.yml atlas/dbt_project/profiles.yml atlas/dbt_project/models/graph/sources.yml
git commit -m "feat: dbt-duckdb project, profile, and graph sources"
```

### Task 6.2: Staging models reading raw parquet

**Files:**
- Create: `atlas/dbt_project/models/staging/stg_prices.sql`, `stg_macro.sql`, `schema.yml`

- [ ] **Step 1: Create `stg_prices.sql`**

```sql
with src as (
    select * from read_parquet('{{ env_var("ATLAS_DATA_RAW", "../data/raw") }}/prices/*.parquet')
)
select
    cast(ticker as varchar)      as ticker,
    cast(date as date)           as date,
    cast(open as double)         as open,
    cast(high as double)         as high,
    cast(low as double)          as low,
    cast(close as double)        as close,
    cast(adj_close as double)    as adj_close,
    cast(volume as bigint)       as volume
from src
```

- [ ] **Step 2: Create `stg_macro.sql`**

```sql
with src as (
    select * from read_parquet('{{ env_var("ATLAS_DATA_RAW", "../data/raw") }}/macro/*.parquet')
)
select
    cast(series_id as varchar) as series_id,
    cast(date as date)         as date,
    cast(value as double)      as value
from src
```

- [ ] **Step 3: Create staging `schema.yml` (data-quality tests)**

```yaml
version: 2
models:
  - name: stg_prices
    columns:
      - name: ticker
        tests: [not_null]
      - name: date
        tests: [not_null]
      - name: close
        tests: [not_null]
    tests:
      - dbt_utils.unique_combination_of_columns:
          combination_of_columns: [ticker, date]
  - name: stg_macro
    columns:
      - name: series_id
        tests: [not_null]
      - name: value
        tests: [not_null]
    tests:
      - dbt_utils.unique_combination_of_columns:
          combination_of_columns: [series_id, date]
```

- [ ] **Step 4: Add `packages.yml` for dbt_utils and install**

Create `atlas/dbt_project/packages.yml`:

```yaml
packages:
  - package: dbt-labs/dbt_utils
    version: [">=1.1.0", "<2.0.0"]
```

Run: `cd atlas/dbt_project && dbt deps`
Expected: dbt_utils installed.

- [ ] **Step 5: Commit**

`dbt deps` also writes `package-lock.yml` (commit it — it pins package versions for
reproducibility) and `.user.yml` (a per-machine anonymous-usage UUID — gitignore it; rule
added in Task 0.1's `.gitignore`). `dbt_packages/` stays ignored.

```bash
git add .gitignore \
  atlas/dbt_project/models/staging \
  atlas/dbt_project/packages.yml \
  atlas/dbt_project/package-lock.yml
git commit -m "feat: dbt staging models for prices/macro with quality tests"
```

### Task 6.3: Mart + graph models

**Files:**
- Create: `atlas/dbt_project/models/marts/prices_daily.sql`, `returns.sql`, `macro_daily.sql`, `schema.yml`
- Create: `atlas/dbt_project/models/graph/graph_nodes.sql`, `graph_edges.sql`

- [ ] **Step 1: Create `marts/prices_daily.sql`**

```sql
select ticker, date, open, high, low, close, adj_close, volume
from {{ ref('stg_prices') }}
```

- [ ] **Step 2: Create `marts/returns.sql`**

```sql
with p as (
    select ticker, date, adj_close,
           lag(adj_close) over (partition by ticker order by date) as prev_adj_close
    from {{ ref('stg_prices') }}
)
select ticker, date, ln(adj_close / prev_adj_close) as log_return
from p
where prev_adj_close is not null and prev_adj_close > 0
```

- [ ] **Step 3: Create `marts/macro_daily.sql`**

```sql
select series_id, date, value
from {{ ref('stg_macro') }}
```

- [ ] **Step 4: Create `graph/graph_nodes.sql` and `graph/graph_edges.sql`**

```sql
-- graph_nodes.sql
select id, name, tickers, stage, region
from {{ source('graph', 'graph_nodes') }}
```

```sql
-- graph_edges.sql
select from_id, to_id, relationship, note, evidence, as_of
from {{ source('graph', 'graph_edges') }}
```

- [ ] **Step 5: Create marts `schema.yml`**

```yaml
version: 2
models:
  - name: prices_daily
    columns:
      - name: ticker
        tests: [not_null]
  - name: returns
    columns:
      - name: log_return
        tests: [not_null]
  - name: graph_nodes
    columns:
      - name: id
        tests: [not_null, unique]
      - name: stage
        tests:
          - accepted_values:
              values: [equipment, foundry, chips, cloud]
```

- [ ] **Step 6: Build and verify (requires Phase 3–5 data present)**

Run: `cd atlas && make ingest && cd dbt_project && dbt build --profiles-dir .`
Expected: all models built, all tests pass.

- [ ] **Step 7: Commit**

```bash
git add atlas/dbt_project/models/marts atlas/dbt_project/models/graph/graph_nodes.sql atlas/dbt_project/models/graph/graph_edges.sql
git commit -m "feat: dbt mart + graph models with tests"
```

---

## Phase 7 — Lead/lag analysis

### Task 7.1: Returns, alignment, cross-correlation

**Files:**
- Create: `atlas/analysis/leadlag.py`
- Test: `atlas/tests/test_leadlag.py`

- [ ] **Step 1: Write the failing test**

```python
# atlas/tests/test_leadlag.py
import numpy as np
import pandas as pd

from analysis.leadlag import (
    align_pair,
    bh_fdr,
    cross_correlations,
    log_returns,
    stationary_bootstrap_pvalue,
)


def test_log_returns_basic():
    s = pd.Series([100.0, 110.0, 121.0],
                  index=pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]))
    r = log_returns(s)
    assert len(r) == 2
    np.testing.assert_allclose(r.values, [np.log(1.1), np.log(1.1)], rtol=1e-9)


def test_align_pair_inner_join_no_ffill():
    a = pd.Series([1.0, 2.0, 3.0], index=pd.to_datetime(["2024-01-01", "2024-01-02", "2024-01-03"]))
    b = pd.Series([10.0, 30.0], index=pd.to_datetime(["2024-01-01", "2024-01-03"]))
    xa, xb = align_pair(a, b)
    assert list(xa.index) == list(pd.to_datetime(["2024-01-01", "2024-01-03"]))
    assert len(xa) == len(xb) == 2


def test_cross_correlations_detects_lag():
    # y leads x by 2: x_t == y_{t-2}; so corr peaks at lag where upstream(y) leads.
    rng = np.random.default_rng(0)
    n = 500
    y = pd.Series(rng.standard_normal(n), index=pd.date_range("2020-01-01", periods=n, freq="B"))
    x = y.shift(2).dropna()
    y2, x2 = align_pair(y, x)
    table = cross_correlations(y2, x2, max_lag=5)
    peak = table.loc[table["corr"].abs().idxmax(), "lag"]
    assert peak == 2


def test_bh_fdr_monotone():
    p = np.array([0.001, 0.01, 0.2, 0.8])
    q = bh_fdr(p)
    assert (q >= p).all()
    assert q[0] <= q[-1]


def test_bootstrap_pvalue_in_unit_interval():
    rng = np.random.default_rng(1)
    n = 300
    x = pd.Series(rng.standard_normal(n))
    y = x * 0.5 + rng.standard_normal(n) * 0.5
    p = stationary_bootstrap_pvalue(x.values, y.values, iters=200, block=10, seed=3)
    assert 0.0 <= p <= 1.0
    assert p < 0.5  # genuine correlation -> smallish p
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlas && pytest tests/test_leadlag.py -v`
Expected: FAIL — cannot import `analysis.leadlag`.

- [ ] **Step 3: Write minimal implementation**

```python
# atlas/analysis/leadlag.py
from __future__ import annotations

import numpy as np
import pandas as pd


def log_returns(prices: pd.Series) -> pd.Series:
    """Daily log returns; index preserved, first obs dropped."""
    return np.log(prices / prices.shift(1)).dropna()


def align_pair(a: pd.Series, b: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Inner-join two series on index. No forward-fill across gaps."""
    df = pd.concat([a.rename("a"), b.rename("b")], axis=1, join="inner").dropna()
    return df["a"], df["b"]


def cross_correlations(left: pd.Series, right: pd.Series, max_lag: int) -> pd.DataFrame:
    """Pearson corr of left_t vs right_{t+lag} for lag in [-max_lag, max_lag].

    Positive lag => `left` leads `right`.
    """
    rows = []
    lv = left.to_numpy()
    rv = right.to_numpy()
    n = len(lv)
    for lag in range(-max_lag, max_lag + 1):
        if lag >= 0:
            x, y = lv[: n - lag], rv[lag:]
        else:
            x, y = lv[-lag:], rv[: n + lag]
        if len(x) < 3 or np.std(x) == 0 or np.std(y) == 0:
            corr = np.nan
        else:
            corr = float(np.corrcoef(x, y)[0, 1])
        rows.append({"lag": lag, "corr": corr, "n": len(x)})
    return pd.DataFrame(rows)


def _abs_corr(x: np.ndarray, y: np.ndarray) -> float:
    if np.std(x) == 0 or np.std(y) == 0:
        return 0.0
    return abs(float(np.corrcoef(x, y)[0, 1]))


def stationary_bootstrap_pvalue(
    x: np.ndarray, y: np.ndarray, *, iters: int, block: int, seed: int
) -> float:
    """Two-sided p-value for |corr(x, y)| via stationary block bootstrap of y.

    Resamples y in random-length blocks (preserving serial structure) to build
    a null distribution of |corr| under broken cross-dependence.
    """
    rng = np.random.default_rng(seed)
    n = len(x)
    observed = _abs_corr(x, y)
    p_geom = 1.0 / block
    count = 0
    for _ in range(iters):
        idx = np.empty(n, dtype=int)
        i = 0
        while i < n:
            start = rng.integers(0, n)
            length = rng.geometric(p_geom)
            for k in range(length):
                if i >= n:
                    break
                idx[i] = (start + k) % n
                i += 1
        if _abs_corr(x, y[idx]) >= observed:
            count += 1
    return (count + 1) / (iters + 1)


def bh_fdr(pvalues: np.ndarray) -> np.ndarray:
    """Benjamini-Hochberg adjusted q-values."""
    p = np.asarray(pvalues, dtype=float)
    n = len(p)
    order = np.argsort(p)
    ranked = p[order] * n / (np.arange(n) + 1)
    q_sorted = np.minimum.accumulate(ranked[::-1])[::-1]
    q = np.empty(n)
    q[order] = np.clip(q_sorted, 0, 1)
    return q
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd atlas && pytest tests/test_leadlag.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add atlas/analysis/leadlag.py atlas/tests/test_leadlag.py
git commit -m "feat: lead/lag primitives (returns, xcorr, bootstrap p, BH-FDR)"
```

### Task 7.2: Orchestrator producing the lead/lag table

**Files:**
- Modify: `atlas/analysis/leadlag.py` (append `build_leadlag_table` + `run`)
- Test: `atlas/tests/test_leadlag.py` (append orchestrator test)

- [ ] **Step 1: Write the failing test (append)**

```python
# append to atlas/tests/test_leadlag.py
import duckdb

from analysis.leadlag import build_leadlag_table


def test_build_leadlag_table_price_pairs(tmp_path):
    rng = np.random.default_rng(5)
    dates = pd.date_range("2019-01-01", periods=400, freq="B")
    y = rng.standard_normal(400)
    # nvidia leads microsoft by 1 day
    returns = pd.DataFrame(
        {
            "ticker": ["asml_t"] * 400 + ["tsmc_t"] * 400,
            "date": list(dates) * 2,
            "log_return": list(y) + list(np.roll(y, 1)),
        }
    )
    edges = pd.DataFrame(
        {"from_id": ["asml"], "to_id": ["tsmc"],
         "relationship": ["supplies"], "note": [""], "evidence": [""], "as_of": ["2024-01-01"]}
    )
    nodes = pd.DataFrame(
        {"id": ["asml", "tsmc"], "name": ["A", "T"],
         "tickers": ['["asml_t"]', '["tsmc_t"]'],
         "stage": ["equipment", "foundry"], "region": ["NL", "TW"]}
    )
    table = build_leadlag_table(returns, pd.DataFrame(columns=["series_id", "date", "value"]),
                                nodes, edges, max_lag=5, price_nmin=100, iters=100)
    assert set(["pair_type", "left", "right", "lag", "corr", "p_value", "q_value", "n_eff", "stable"]).issubset(table.columns)
    assert (table["pair_type"] == "edge").any()
    assert (table["q_value"] <= 1.0).all()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlas && pytest tests/test_leadlag.py::test_build_leadlag_table_price_pairs -v`
Expected: FAIL — cannot import `build_leadlag_table`.

- [ ] **Step 3: Append implementation**

```python
# append to atlas/analysis/leadlag.py
import json

from config import (
    BOOTSTRAP_BLOCK,
    BOOTSTRAP_ITERS,
    DUCKDB_PATH,
    FDR_ALPHA,
    MACRO_NMIN,
    MAX_LAG_DAYS,
    PRICE_NMIN,
    RANDOM_SEED,
)

_LEADLAG_COLUMNS = [
    "pair_type", "left", "right", "lag", "corr", "p_value", "q_value", "n_eff", "stable",
]


def _ticker_for_node(nodes: pd.DataFrame, node_id: str) -> str:
    row = nodes.loc[nodes["id"] == node_id]
    if row.empty:
        return ""
    return json.loads(row["tickers"].iloc[0])[0]


def _stable_across_halves(left: pd.Series, right: pd.Series, lag: int) -> bool:
    half = len(left) // 2
    if half < 30:
        return False
    peaks = []
    for sl in (slice(0, half), slice(half, None)):
        t = cross_correlations(left.iloc[sl], right.iloc[sl], max_lag=abs(lag) + 5)
        t = t.dropna(subset=["corr"])
        if t.empty:
            return False
        peaks.append(int(t.loc[t["corr"].abs().idxmax(), "lag"]))
    return all(np.sign(p) == np.sign(lag) for p in peaks) if lag != 0 else all(p == 0 for p in peaks)


def build_leadlag_table(
    returns: pd.DataFrame,
    macro: pd.DataFrame,
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    *,
    max_lag: int = MAX_LAG_DAYS,
    price_nmin: int = PRICE_NMIN,
    iters: int = BOOTSTRAP_ITERS,
) -> pd.DataFrame:
    """Compute lead/lag rows for supplier->customer edges (price pairs).

    `returns` columns: ticker, date, log_return. Macro pairs use native frequency
    (handled by the caller resampling); here macro is left for extension and
    contributes no rows when empty.
    """
    rows: list[dict] = []
    ret_by_ticker = {t: g.set_index("date")["log_return"] for t, g in returns.groupby("ticker")}

    for _, e in edges.iterrows():
        lt = _ticker_for_node(nodes, e["from_id"])
        rt = _ticker_for_node(nodes, e["to_id"])
        if lt not in ret_by_ticker or rt not in ret_by_ticker:
            continue
        left, right = align_pair(ret_by_ticker[lt], ret_by_ticker[rt])
        if len(left) < price_nmin:
            continue
        table = cross_correlations(left, right, max_lag=max_lag).dropna(subset=["corr"])
        if table.empty:
            continue
        peak = table.loc[table["corr"].abs().idxmax()]
        lag = int(peak["lag"])
        if lag >= 0:
            x, y = left.to_numpy()[: len(left) - lag], right.to_numpy()[lag:]
        else:
            x, y = left.to_numpy()[-lag:], right.to_numpy()[: len(right) + lag]
        p = stationary_bootstrap_pvalue(
            x, y, iters=iters, block=BOOTSTRAP_BLOCK, seed=RANDOM_SEED
        )
        rows.append(
            {
                "pair_type": "edge",
                "left": e["from_id"],
                "right": e["to_id"],
                "lag": lag,
                "corr": float(peak["corr"]),
                "p_value": p,
                "q_value": np.nan,
                "n_eff": int(peak["n"]),
                "stable": _stable_across_halves(left, right, lag),
            }
        )

    df = pd.DataFrame(rows, columns=_LEADLAG_COLUMNS)
    if not df.empty:
        df["q_value"] = bh_fdr(df["p_value"].to_numpy())
    return df


def run() -> None:
    import duckdb

    con = duckdb.connect(str(DUCKDB_PATH))
    returns = con.execute("SELECT ticker, date, log_return FROM returns").fetchdf()
    macro = con.execute("SELECT series_id, date, value FROM macro_daily").fetchdf()
    nodes = con.execute("SELECT * FROM graph_nodes").fetchdf()
    edges = con.execute("SELECT * FROM graph_edges").fetchdf()
    table = build_leadlag_table(returns, macro, nodes, edges)
    con.register("ll", table)
    con.execute("CREATE OR REPLACE TABLE leadlag AS SELECT * FROM ll")
    con.unregister("ll")
    con.close()
    print(f"leadlag: wrote {len(table)} rows (alpha={FDR_ALPHA})")


if __name__ == "__main__":
    run()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd atlas && pytest tests/test_leadlag.py -v`
Expected: all passed.

- [ ] **Step 5: Commit**

```bash
git add atlas/analysis/leadlag.py atlas/tests/test_leadlag.py
git commit -m "feat: lead/lag table orchestrator writing to duckdb"
```

### Task 7.3: Native-frequency macro lead/lag (spec §Lead/lag)

> Closes the spec requirement that macro is analyzed at its **native frequency** with an
> **effective-observations** floor — never forward-filled onto daily dates. Price returns
> are resampled to each macro series' frequency before correlating.

**Files:**
- Modify: `atlas/analysis/leadlag.py` (add resampling + macro rows; single BH over the full family)
- Test: `atlas/tests/test_leadlag.py` (append)

- [ ] **Step 1: Write the failing test (append)**

```python
# append to atlas/tests/test_leadlag.py
from analysis.leadlag import infer_period_freq, resample_returns_to_freq


def test_infer_period_freq_monthly():
    idx = pd.date_range("2015-01-31", periods=24, freq="ME")
    assert infer_period_freq(idx) == "ME"


def test_infer_period_freq_daily():
    idx = pd.date_range("2020-01-01", periods=60, freq="B")
    assert infer_period_freq(idx) == "D"


def test_resample_returns_to_monthly_counts_periods():
    d = pd.date_range("2020-01-01", periods=400, freq="B")
    r = pd.Series(0.001, index=d)
    monthly = resample_returns_to_freq(r, "ME")
    assert len(monthly) <= 20  # ~19 months, far fewer than 400 daily obs


def test_macro_pairs_use_native_frequency(tmp_path):
    # Monthly macro must NOT be counted as daily observations.
    dates_d = pd.date_range("2015-01-01", periods=2000, freq="B")
    rng = np.random.default_rng(2)
    returns = pd.DataFrame(
        {"ticker": ["nvda_t"] * 2000, "date": dates_d,
         "log_return": rng.standard_normal(2000) * 0.01}
    )
    macro_dates = pd.date_range("2015-01-31", periods=96, freq="ME")
    macro = pd.DataFrame(
        {"series_id": ["IPG"] * 96, "date": macro_dates, "value": rng.standard_normal(96)}
    )
    nodes = pd.DataFrame(
        {"id": ["nvidia"], "name": ["NVIDIA"], "tickers": ['["nvda_t"]'],
         "stage": ["chips"], "region": ["US"]}
    )
    edges = pd.DataFrame(columns=["from_id", "to_id", "relationship", "note", "evidence", "as_of"])
    table = build_leadlag_table(returns, macro, nodes, edges, iters=50)
    macro_rows = table[table["pair_type"] == "macro"]
    assert not macro_rows.empty
    # n_eff reflects monthly periods (~96), not 2000 daily rows
    assert macro_rows["n_eff"].max() <= 96
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlas && pytest tests/test_leadlag.py -k "freq or macro_pairs" -v`
Expected: FAIL — cannot import `infer_period_freq` / `resample_returns_to_freq`.

- [ ] **Step 3: Add resampling helpers and macro branch**

Add these helpers near the top of the module (after `align_pair`):

```python
# add to atlas/analysis/leadlag.py
def infer_period_freq(index: pd.DatetimeIndex) -> str:
    """Classify a series' native frequency from median spacing in days."""
    if len(index) < 3:
        return "D"
    median_days = pd.Series(index).sort_values().diff().dt.days.median()
    if median_days >= 20:
        return "ME"
    if median_days >= 5:
        return "W"
    return "D"


def resample_returns_to_freq(daily_returns: pd.Series, freq: str) -> pd.Series:
    """Aggregate daily log-returns into the target frequency by summing (log-additive)."""
    if freq == "D":
        return daily_returns
    return daily_returns.resample(freq).sum().dropna()


def macro_changes(values: pd.Series, freq: str) -> pd.Series:
    """First-difference the macro level at its native frequency for stationarity."""
    return values.resample(freq).last().diff().dropna()
```

Then **replace** the macro stub in `build_leadlag_table`. Change the docstring line and add a
macro loop *before* the final `bh_fdr` call so price + macro form one correction family:

```python
# inside build_leadlag_table, AFTER the edge loop and BEFORE building `df`:
    if not macro.empty and not nodes.empty:
        macro_by_id = {sid: g.set_index("date")["value"] for sid, g in macro.groupby("series_id")}
        for sid, mser in macro_by_id.items():
            mser = mser.sort_index()
            freq = infer_period_freq(pd.DatetimeIndex(mser.index))
            m_chg = macro_changes(mser, freq)
            for _, node in nodes.iterrows():
                tkr = json.loads(node["tickers"])[0]
                if tkr not in ret_by_ticker:
                    continue
                pr = resample_returns_to_freq(ret_by_ticker[tkr], freq)
                left, right = align_pair(pr, m_chg)
                if len(left) < MACRO_NMIN:
                    continue
                table = cross_correlations(left, right, max_lag=12).dropna(subset=["corr"])
                if table.empty:
                    continue
                peak = table.loc[table["corr"].abs().idxmax()]
                lag = int(peak["lag"])
                if lag >= 0:
                    x, y = left.to_numpy()[: len(left) - lag], right.to_numpy()[lag:]
                else:
                    x, y = left.to_numpy()[-lag:], right.to_numpy()[: len(right) + lag]
                p = stationary_bootstrap_pvalue(x, y, iters=iters, block=4, seed=RANDOM_SEED)
                rows.append(
                    {
                        "pair_type": "macro",
                        "left": node["id"],
                        "right": sid,
                        "lag": lag,
                        "corr": float(peak["corr"]),
                        "p_value": p,
                        "q_value": np.nan,
                        "n_eff": int(peak["n"]),
                        "stable": _stable_across_halves(left, right, lag),
                    }
                )
```

The existing `df = pd.DataFrame(rows, ...)` + single `bh_fdr` call now corrects over the
combined price+macro family. Macro lags are in native periods (months/weeks), documented in
the report.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd atlas && pytest tests/test_leadlag.py -v`
Expected: all passed (price + macro + helper tests).

- [ ] **Step 5: Commit**

```bash
git add atlas/analysis/leadlag.py atlas/tests/test_leadlag.py
git commit -m "feat: native-frequency macro lead/lag with effective-obs floor"
```

---

## Phase 8 — App data layer (release fetch + checksum + fallback)

### Task 8.1: Release resolution and checksum verification

**Files:**
- Create: `atlas/app/data.py`
- Test: `atlas/tests/test_app_data.py`

- [ ] **Step 1: Write the failing test**

```python
# atlas/tests/test_app_data.py
import hashlib
from pathlib import Path

import pytest

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlas && pytest tests/test_app_data.py -v`
Expected: FAIL — cannot import `app.data`.

- [ ] **Step 3: Write minimal implementation**

```python
# atlas/app/data.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd atlas && pytest tests/test_app_data.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add atlas/app/data.py atlas/tests/test_app_data.py
git commit -m "feat: app data layer - release resolution + checksum verify"
```

### Task 8.2: Streamlit app (map / dashboard / report)

**Files:**
- Create: `atlas/app/streamlit_app.py`

> No unit test (UI glue); verified by manual smoke run. Keep logic in `app/data.py` (tested) and read-only queries here.

- [ ] **Step 1: Create `streamlit_app.py`**

```python
# atlas/app/streamlit_app.py
from __future__ import annotations

import json
from pathlib import Path

import duckdb
import networkx as nx
import plotly.graph_objects as go
import streamlit as st

from config import DUCKDB_PATH

st.set_page_config(page_title="Atlas — AI Value Chain", layout="wide")


@st.cache_resource
def _con() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DUCKDB_PATH), read_only=True)


def _load(table: str):
    return _con().execute(f"SELECT * FROM {table}").fetchdf()


def _graph_figure(nodes, edges, leadlag) -> go.Figure:
    g = nx.DiGraph()
    for _, n in nodes.iterrows():
        g.add_node(n["id"], label=n["name"], stage=n["stage"])
    lag_by_pair = {(r["left"], r["right"]): r for _, r in leadlag.iterrows()}
    for _, e in edges.iterrows():
        g.add_edge(e["from_id"], e["to_id"])
    pos = nx.spring_layout(g, seed=7)
    edge_x, edge_y = [], []
    for u, v in g.edges():
        edge_x += [pos[u][0], pos[v][0], None]
        edge_y += [pos[u][1], pos[v][1], None]
    node_x = [pos[n][0] for n in g.nodes()]
    node_y = [pos[n][1] for n in g.nodes()]
    labels = [g.nodes[n]["label"] for n in g.nodes()]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=edge_x, y=edge_y, mode="lines",
                             line=dict(width=1, color="#888"), hoverinfo="none"))
    fig.add_trace(go.Scatter(x=node_x, y=node_y, mode="markers+text", text=labels,
                             textposition="top center", marker=dict(size=18)))
    fig.update_layout(showlegend=False, margin=dict(l=10, r=10, t=10, b=10))
    return fig


st.title("Atlas — AI Value-Chain Research Engine")
st.caption("Descriptive lead/lag relationships, not trading signals. Correlation ≠ causation.")

if not Path(DUCKDB_PATH).exists():
    st.warning("No database found. Run `make all` to build it.")
    st.stop()

tab_map, tab_dash, tab_report = st.tabs(["Value-chain map", "Dashboard", "Report"])

with tab_map:
    nodes, edges, leadlag = _load("graph_nodes"), _load("graph_edges"), _load("leadlag")
    st.plotly_chart(_graph_figure(nodes, edges, leadlag), use_container_width=True)
    st.subheader("Measured lead/lag (FDR-significant flagged)")
    st.dataframe(leadlag)

with tab_dash:
    returns = _load("returns")
    st.line_chart(returns.pivot_table(index="date", columns="ticker", values="log_return").cumsum())

with tab_report:
    rp = Path(__file__).resolve().parent.parent / "reports" / "report.md"
    st.markdown(rp.read_text() if rp.exists() else "Report not yet generated.")
```

- [ ] **Step 2: Smoke-run (requires `make all` to have produced the DB)**

Run: `cd atlas && make all && streamlit run app/streamlit_app.py --server.headless true & sleep 8 && curl -sf localhost:8501 >/dev/null && echo OK; kill %1`
Expected: prints `OK` (app served without crashing).

- [ ] **Step 3: Commit**

```bash
git add atlas/app/streamlit_app.py
git commit -m "feat: Streamlit app - value-chain map, dashboard, report tabs"
```

---

## Phase 9 — CI, nightly data release, docs

### Task 9.1: CI workflow (secret-scan + lint + tests + dbt build on fixtures)

**Files:**
- Create: `atlas/tests/fixtures/prices/NVDA.parquet`, `atlas/tests/fixtures/macro/DFF.parquet` (tiny)
- Create: `.github/workflows/ci.yml`

- [ ] **Step 1: Generate tiny fixtures**

Run:
```bash
cd atlas && python -c "
import pandas as pd, pathlib
pathlib.Path('tests/fixtures/prices').mkdir(parents=True, exist_ok=True)
pathlib.Path('tests/fixtures/macro').mkdir(parents=True, exist_ok=True)
d=pd.date_range('2020-01-01',periods=300,freq='B')
pd.DataFrame({'ticker':'NVDA','date':d,'open':1.0,'high':1.0,'low':1.0,'close':1.0,'adj_close':(1.0+pd.Series(range(300))/300),'volume':100}).to_parquet('tests/fixtures/prices/NVDA.parquet',index=False)
pd.DataFrame({'series_id':'DFF','date':d,'value':5.0}).to_parquet('tests/fixtures/macro/DFF.parquet',index=False)
"
```

- [ ] **Step 2: Create `.github/workflows/ci.yml`**

```yaml
name: ci
on:
  push:
  pull_request:
jobs:
  secret-scan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: gitleaks/gitleaks-action@v2
        env:
          GITLEAKS_CONFIG: .gitleaks.toml
  test:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: atlas } }
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv venv && uv pip install -e ".[dev]"
      - run: uv run ruff check .
      - run: uv run pytest --cov --cov-report=term-missing --cov-fail-under=80
      - name: dbt build on fixtures
        # dbt runs from dbt_project/, and staging models read_parquet a path relative to
        # that dir, so the fixture path must be ../tests/fixtures (not tests/fixtures).
        env:
          ATLAS_DATA_RAW: ../tests/fixtures
        run: |
          uv run python -m ingest.graph
          cd dbt_project && uv run dbt deps && uv run dbt build --profiles-dir .
```

- [ ] **Step 3: Commit**

The committed `.parquet` fixtures need the negation rules added in Task 0.1's `.gitignore`
(force-add as a fallback if needed: `git add -f atlas/tests/fixtures`). Include `.gitignore`:

```bash
git add .gitignore atlas/tests/fixtures .github/workflows/ci.yml
git commit -m "ci: secret-scan + lint + tests (80% gate) + dbt build on fixtures"
```

### Task 9.2: Nightly data release workflow (atomic immutable publish + retention)

**Files:**
- Create: `atlas/scripts/publish_release.py`
- Create: `.github/workflows/update-data.yml`

- [ ] **Step 1: Create `atlas/scripts/publish_release.py`**

```python
# atlas/scripts/publish_release.py
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from config import DUCKDB_PATH

SCHEMA_VERSION = "1"
KEEP_RELEASES = 14
# Tables whose row counts go into the manifest (skipped silently if absent).
ROW_COUNT_TABLES = [
    "prices_daily", "returns", "macro_daily", "graph_nodes", "graph_edges", "leadlag",
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

    # 1) create as DRAFT, 2) upload all assets to the draft
    subprocess.run(
        ["gh", "release", "create", tag, str(db), "manifest.json",
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
```

- [ ] **Step 2: Create `.github/workflows/update-data.yml`**

```yaml
name: update-data
on:
  schedule:
    - cron: "0 4 * * *"
  workflow_dispatch:
permissions:
  contents: write
jobs:
  refresh:
    runs-on: ubuntu-latest
    defaults: { run: { working-directory: atlas } }
    env:
      GH_TOKEN: ${{ github.token }}
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uv venv && uv pip install -e ".[dev]"
      - run: uv run make all
      - run: uv run python scripts/publish_release.py
```

- [ ] **Step 3: Commit**

```bash
git add atlas/scripts/publish_release.py .github/workflows/update-data.yml
git commit -m "ci: nightly immutable DuckDB data release with retention"
```

### Task 9.3: README + report + archive v1

**Files:**
- Create: `atlas/README.md`, `atlas/reports/report.md`
- Move: `ai-value-chain-data/` → `legacy/ai-value-chain-data/`

- [ ] **Step 1: Write `atlas/README.md`**

Include: one-line pitch, live demo link placeholder, `make setup && make all && make app` quickstart, architecture diagram (reference the spec), the data-refresh model, and a **Non-Goals** section copied from spec §8. State the v1→v2 rebuild rationale.

- [ ] **Step 2: Write `atlas/reports/report.md`**

A narrative skeleton with real section headings: Value-chain overview, Method (lead/lag + caveats), Findings (reads the `leadlag` table), Hypotheses ("where to look next"). Include the correlation≠causation disclaimer.

- [ ] **Step 3: Archive v1 (only after Phase 0 gate is green)**

```bash
git mv ai-value-chain-data legacy/ai-value-chain-data
git commit -m "chore: archive v1 stack as legacy reference"
```

- [ ] **Step 4: Commit docs**

```bash
git add atlas/README.md atlas/reports/report.md
git commit -m "docs: atlas README and report skeleton"
```

---

## Definition of Done (slice)

- [ ] Phase 0 security gate green (gitleaks clean, secrets rotated, `.gitignore` in place).
- [ ] `make setup && make all && make app` works from a clean clone.
- [ ] `pytest --cov` ≥ 80% on `ingest`/`analysis`/`app`; all dbt tests pass.
- [ ] CI green (secret-scan + lint + tests + dbt build on fixtures).
- [ ] Streamlit app shows map + dashboard + report; lead/lag table flags FDR-significant, stable edges.
- [ ] Nightly workflow publishes an immutable, checksum-verified data release (Task 9.2). Release-resolution + checksum-verification logic is implemented and unit-tested (Task 8.1). Wiring that loader into the deployed Streamlit app's startup (env-gated: fetch+verify when `ATLAS_RELEASE_REPO` is set, else use local DB) is the final deploy-integration step — the app runs locally on the `make all` DB without it.
- [ ] v1 archived under `legacy/`; README tells the v1→v2 story and lists non-goals.
