# Atlas Layer 2 — SEC EDGAR Fundamentals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add SEC EDGAR fundamentals (revenue, capex, gross margin) for US filers and surface point-in-time quarterly **capex→downstream-revenue** and **capex→price** lead/lag, testing the "AI-buildout capex leads downstream" thesis.

**Architecture:** New `ingest/fundamentals.py` pulls SEC XBRL `companyconcept` JSON (concept-fallback resolver, throttled, `User-Agent` required) → validated long-format Parquet → dbt `stg_fundamentals` + `fundamentals_quarterly` mart (indexed by SEC `filed` date, not period-end, to avoid lookahead) → `analysis/leadlag.py` extended with a quarterly fundamentals pair type reusing the existing native-frequency + block-bootstrap + BH-FDR machinery → Streamlit "Fundamentals" view. Manifest `schema_version` bumps to `2`.

**Tech Stack:** unchanged from the slice (Python 3.13, requests, pandas, pandera, DuckDB, dbt-duckdb, scipy/numpy, Streamlit). No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-02-atlas-layer2-fundamentals-scope.md`
**Decisions (locked):** US filers first; revenue + capex + gross margin; capex→revenue + capex→price, point-in-time on `filed`.

---

## File Structure (new + modified)

```
atlas/
  config.py                       # MODIFY: SEC_USER_AGENT, CONCEPT_TAGS, FUND_* windows
  seeds/value_chain.yml           # MODIFY: add `cik` to each US-filer node
  ingest/
    schemas.py                    # MODIFY: add FUNDAMENTAL_SCHEMA
    graph.py                      # MODIFY: Node gains optional `cik`
    fundamentals.py               # CREATE: concept resolver + normalize + fetch + run
  analysis/leadlag.py             # MODIFY: build_leadlag_table accepts fundamentals
  app/streamlit_app.py            # MODIFY: Fundamentals tab
  dbt_project/models/
    staging/stg_fundamentals.sql  # CREATE
    staging/schema.yml            # MODIFY: add stg_fundamentals tests
    marts/fundamentals_quarterly.sql  # CREATE
    marts/schema.yml              # MODIFY: add mart tests
  scripts/publish_release.py      # MODIFY: SCHEMA_VERSION="2", add fundamentals to row_counts
  app/data.py                     # MODIFY: APP_SCHEMA_VERSION="2"
  tests/
    test_fundamentals.py          # CREATE
    test_leadlag.py               # MODIFY: append fundamentals pair test
    fixtures/fundamentals/*.parquet  # CREATE (tiny)
  reports/report.md               # MODIFY: fundamentals findings section
  README.md                       # MODIFY: Layer 2 note
```

**Naming contracts (new):**
- Fundamentals long-format columns: `cik, ticker, concept, metric, period_start, period_end, filed, fiscal_period, fy, form, value, unit, accn`
- `metric` ∈ {`revenue`, `capex`, `gross_margin`}
- `fundamentals_quarterly` mart columns: `ticker, period_end, filed, fy, fiscal_period, revenue, capex, gross_margin`
- New lead/lag `pair_type` values: `fund_capex_rev`, `fund_capex_price` (lag unit: quarters)

---

## Task 1: Add CIK to the graph

**Files:**
- Modify: `atlas/seeds/value_chain.yml`, `atlas/ingest/graph.py`
- Test: `atlas/tests/test_graph.py` (append)

- [ ] **Step 1: Write the failing test (append to `test_graph.py`)**

```python
# append to atlas/tests/test_graph.py
VALID_WITH_CIK = """
nodes:
  - id: nvidia
    name: NVIDIA
    tickers: [NVDA]
    stage: chips
    region: US
    cik: "0001045810"
edges: []
"""


def test_node_carries_cik(tmp_path):
    p = tmp_path / "g.yml"
    p.write_text(VALID_WITH_CIK)
    nodes, _ = load_graph(p)
    assert "cik" in nodes.columns
    assert nodes.loc[nodes["id"] == "nvidia", "cik"].iloc[0] == "0001045810"


def test_node_cik_optional(tmp_path):
    # foreign filers (ASML/TSM) may omit cik in Layer 2
    p = tmp_path / "g.yml"
    p.write_text(VALID)  # VALID has no cik; defined earlier in this file
    nodes, _ = load_graph(p)
    assert "cik" in nodes.columns
    assert nodes["cik"].isna().all() or (nodes["cik"] == "").all()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlas && uv run pytest tests/test_graph.py -k cik -v`
Expected: FAIL — `cik` not in columns / `KeyError`.

- [ ] **Step 3: Modify `Node` and the nodes_df builder in `atlas/ingest/graph.py`**

In the `Node` model add an optional field:

```python
    cik: str | None = None
```

In `load_graph`, change the nodes_df row dict to include `cik` (normalized to empty string
when absent so the column is always present and string-typed):

```python
                "cik": (n.cik or ""),
```

and add `"cik"` to the `columns=[...]` list for `nodes_df`.

- [ ] **Step 4: Add `cik` to the US-filer nodes in `seeds/value_chain.yml`**

Add a `cik:` line (10-digit zero-padded SEC CIK, quoted to preserve leading zeros) to each
US-filer node. Reference values:

```yaml
# nvidia: cik: "0001045810"   amd: "0000002488"   avgo: "0001730168"
# micron: "0000723125"   amat: "0000006951"   lam(lrcx): "0000707549"
# microsoft: "0000789019"   alphabet(googl): "0001652044"   amazon: "0001018724"
# meta: "0001326801"   oracle: "0001341439"   dell: "0001571996"   supermicro(smci): "0001375365"
```
ASML/TSM nodes get no `cik` (deferred to Layer 2b).

- [ ] **Step 5: Run test to verify it passes**

Run: `cd atlas && uv run pytest tests/test_graph.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add atlas/ingest/graph.py atlas/seeds/value_chain.yml atlas/tests/test_graph.py
git commit -m "feat: add CIK to value-chain nodes for fundamentals"
```

---

## Task 2: SEC config + fundamentals schema

**Files:**
- Modify: `atlas/config.py`, `atlas/ingest/schemas.py`
- Test: `atlas/tests/test_schemas.py` (append)

- [ ] **Step 1: Write the failing test (append to `test_schemas.py`)**

```python
# append to atlas/tests/test_schemas.py
from ingest.schemas import FUNDAMENTAL_SCHEMA


def _valid_fundamentals():
    return pd.DataFrame({
        "cik": ["0001045810"],
        "ticker": ["NVDA"],
        "concept": ["Revenues"],
        "metric": ["revenue"],
        "period_start": pd.to_datetime(["2023-01-01"]),
        "period_end": pd.to_datetime(["2023-03-31"]),
        "filed": pd.to_datetime(["2023-05-05"]),
        "fiscal_period": ["Q1"],
        "fy": [2023],
        "form": ["10-Q"],
        "value": [7192000000.0],
        "unit": ["USD"],
        "accn": ["0001045810-23-000079"],
    })


def test_fundamental_schema_accepts_valid():
    FUNDAMENTAL_SCHEMA.validate(_valid_fundamentals())


def test_fundamental_schema_rejects_bad_metric():
    bad = _valid_fundamentals()
    bad.loc[0, "metric"] = "ebitda"
    with pytest.raises(pandera.errors.SchemaError):
        FUNDAMENTAL_SCHEMA.validate(bad)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlas && uv run pytest tests/test_schemas.py -k fundamental -v`
Expected: FAIL — cannot import `FUNDAMENTAL_SCHEMA`.

- [ ] **Step 3: Add `FUNDAMENTAL_SCHEMA` to `atlas/ingest/schemas.py`**

```python
FUNDAMENTAL_SCHEMA = pa.DataFrameSchema(
    {
        "cik": pa.Column(str, nullable=False),
        "ticker": pa.Column(str, nullable=False),
        "concept": pa.Column(str, nullable=False),
        "metric": pa.Column(str, pa.Check.isin(["revenue", "capex", "gross_margin"])),
        "period_start": pa.Column("datetime64[ns]", nullable=True),
        "period_end": pa.Column("datetime64[ns]", nullable=False),
        "filed": pa.Column("datetime64[ns]", nullable=False),
        "fiscal_period": pa.Column(str, nullable=True),
        "fy": pa.Column("int64", nullable=True, coerce=True),
        "form": pa.Column(str, nullable=True),
        "value": pa.Column(float, nullable=False),
        "unit": pa.Column(str, nullable=False),
        "accn": pa.Column(str, nullable=False),
    },
    strict=True,
)
```

- [ ] **Step 4: Add SEC config to `atlas/config.py`**

```python
# --- Layer 2: SEC EDGAR fundamentals ---
# SEC requires a descriptive User-Agent; set ATLAS_SEC_USER_AGENT in CI/local env.
SEC_USER_AGENT = os.getenv("ATLAS_SEC_USER_AGENT", "atlas-research atlas@example.com")
SEC_RATE_LIMIT_SECONDS = 0.2  # ~5 req/s, under SEC's ~10 req/s ceiling

# Concept-tag fallbacks per metric, tried in order until one returns data.
CONCEPT_TAGS: dict[str, list[str]] = {
    "revenue": [
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "Revenues",
        "SalesRevenueNet",
    ],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ],
    "gross_profit": ["GrossProfit"],
    "cost_of_revenue": ["CostOfRevenue", "CostOfGoodsAndServicesSold"],
}

FUND_MAX_LAG_QUARTERS = 4
FUND_NMIN = 12  # minimum overlapping quarterly observations
```

Ensure `import os` is present at the top of `config.py` (it already is).

- [ ] **Step 5: Run test to verify it passes**

Run: `cd atlas && uv run pytest tests/test_schemas.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add atlas/ingest/schemas.py atlas/config.py atlas/tests/test_schemas.py
git commit -m "feat: SEC config and fundamentals pandera schema"
```

---

## Task 3: Fundamentals ingestion (concept resolver + normalize + fetch)

**Files:**
- Create: `atlas/ingest/fundamentals.py`
- Test: `atlas/tests/test_fundamentals.py`

- [ ] **Step 1: Write the failing test**

```python
# atlas/tests/test_fundamentals.py
import pandas as pd

from ingest.fundamentals import normalize_concept, pick_first_filed


def _concept_json():
    return {
        "cik": 1045810,
        "tag": "Revenues",
        "units": {
            "USD": [
                {"start": "2023-01-01", "end": "2023-03-31", "val": 7192000000,
                 "fy": 2023, "fp": "Q1", "form": "10-Q", "filed": "2023-05-05",
                 "accn": "acc-1"},
                # restatement of the same period, filed later -> must be dropped
                {"start": "2023-01-01", "end": "2023-03-31", "val": 7200000000,
                 "fy": 2023, "fp": "Q1", "form": "10-Q/A", "filed": "2023-08-01",
                 "accn": "acc-2"},
                {"start": "2023-04-01", "end": "2023-06-30", "val": 13507000000,
                 "fy": 2023, "fp": "Q2", "form": "10-Q", "filed": "2023-08-21",
                 "accn": "acc-3"},
            ]
        },
    }


def test_normalize_concept_long_format():
    out = normalize_concept(_concept_json(), cik="0001045810", ticker="NVDA",
                            metric="revenue", concept="Revenues")
    assert list(out.columns)[:4] == ["cik", "ticker", "concept", "metric"]
    assert (out["metric"] == "revenue").all()
    assert {"period_end", "filed", "value", "accn"}.issubset(out.columns)
    assert len(out) == 3


def test_pick_first_filed_drops_restatements():
    df = normalize_concept(_concept_json(), cik="0001045810", ticker="NVDA",
                           metric="revenue", concept="Revenues")
    pit = pick_first_filed(df)
    # one row per period_end, keeping the earliest filed
    assert len(pit) == 2
    q1 = pit[pit["period_end"] == pd.Timestamp("2023-03-31")].iloc[0]
    assert q1["value"] == 7192000000  # original, not the restatement
    assert q1["accn"] == "acc-1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlas && uv run pytest tests/test_fundamentals.py -v`
Expected: FAIL — cannot import `ingest.fundamentals`.

- [ ] **Step 3: Write minimal implementation**

```python
# atlas/ingest/fundamentals.py
from __future__ import annotations

import json
import time
from pathlib import Path

import pandas as pd
import requests

from config import (
    CONCEPT_TAGS,
    DATA_RAW,
    SEC_RATE_LIMIT_SECONDS,
    SEC_USER_AGENT,
)
from ingest._base import atomic_write_parquet, with_retry
from ingest.schemas import FUNDAMENTAL_SCHEMA

_CONCEPT_URL = "https://data.sec.gov/api/xbrl/companyconcept/CIK{cik}/us-gaap/{tag}.json"
_COLUMNS = [
    "cik", "ticker", "concept", "metric", "period_start", "period_end", "filed",
    "fiscal_period", "fy", "form", "value", "unit", "accn",
]


def normalize_concept(
    concept_json: dict, *, cik: str, ticker: str, metric: str, concept: str
) -> pd.DataFrame:
    """Flatten a companyconcept JSON (USD units) into validated long format."""
    obs = (concept_json.get("units", {}) or {}).get("USD", [])
    rows = []
    for o in obs:
        rows.append(
            {
                "cik": cik,
                "ticker": ticker,
                "concept": concept,
                "metric": metric,
                "period_start": o.get("start"),
                "period_end": o.get("end"),
                "filed": o.get("filed"),
                "fiscal_period": o.get("fp"),
                "fy": o.get("fy"),
                "form": o.get("form"),
                "value": o.get("val"),
                "unit": "USD",
                "accn": o.get("accn"),
            }
        )
    df = pd.DataFrame(rows, columns=_COLUMNS)
    if df.empty:
        return FUNDAMENTAL_SCHEMA.validate(df)
    for col in ("period_start", "period_end", "filed"):
        df[col] = pd.to_datetime(df[col], errors="coerce")
    df = df.dropna(subset=["period_end", "filed", "value"])
    df["value"] = df["value"].astype(float)
    df["fy"] = df["fy"].astype("Int64").astype("int64")
    return FUNDAMENTAL_SCHEMA.validate(df.reset_index(drop=True))


def pick_first_filed(df: pd.DataFrame) -> pd.DataFrame:
    """Point-in-time: keep the earliest-filed observation per period_end (drop restatements)."""
    if df.empty:
        return df
    return (
        df.sort_values("filed")
        .drop_duplicates(subset=["metric", "period_end"], keep="first")
        .reset_index(drop=True)
    )


def fetch_concept(cik: str, tag: str) -> dict | None:  # pragma: no cover
    """Fetch one us-gaap concept for a CIK; return None on 404 (tag not used by filer)."""
    def _dl() -> dict | None:
        time.sleep(SEC_RATE_LIMIT_SECONDS)
        url = _CONCEPT_URL.format(cik=cik, tag=tag)
        resp = requests.get(url, headers={"User-Agent": SEC_USER_AGENT}, timeout=30)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()

    return with_retry(_dl)


def resolve_metric(cik: str, ticker: str, metric: str) -> pd.DataFrame:  # pragma: no cover
    """Try each fallback tag for `metric` until one returns data; return point-in-time rows."""
    for tag in CONCEPT_TAGS[metric]:
        data = fetch_concept(cik, tag)
        if data and (data.get("units", {}) or {}).get("USD"):
            df = normalize_concept(data, cik=cik, ticker=ticker, metric=metric, concept=tag)
            if not df.empty:
                return pick_first_filed(df)
    return pd.DataFrame(columns=_COLUMNS)


def run() -> None:  # pragma: no cover
    import duckdb

    from config import DUCKDB_PATH

    con = duckdb.connect(str(DUCKDB_PATH), read_only=True)
    nodes = con.execute(
        "SELECT id, tickers, cik FROM graph_nodes WHERE cik IS NOT NULL AND cik != ''"
    ).fetchdf()
    con.close()

    out_dir = Path(DATA_RAW) / "fundamentals"
    unresolved: list[str] = []
    for _, node in nodes.iterrows():
        ticker = json.loads(node["tickers"])[0]
        cik = str(node["cik"]).zfill(10)
        frames = []
        # revenue and capex come straight from a concept; gross_margin is derived below.
        for metric in ("revenue", "capex"):
            df = resolve_metric(cik, ticker, metric)
            if df.empty:
                unresolved.append(f"{ticker}:{metric}")
            else:
                frames.append(df)
        gm = _gross_margin(cik, ticker)
        if gm.empty:
            unresolved.append(f"{ticker}:gross_margin")
        else:
            frames.append(gm)
        if frames:
            combined = pd.concat(frames, ignore_index=True)
            atomic_write_parquet(combined, out_dir / f"{ticker}.parquet")
            print(f"fundamentals: wrote {len(combined)} rows for {ticker}")
    if unresolved:
        print("fundamentals: unresolved (recorded, skipped):", ", ".join(unresolved))


def _gross_margin(cik: str, ticker: str) -> pd.DataFrame:  # pragma: no cover
    """Derive gross_margin = gross_profit / revenue per period_end (point-in-time)."""
    rev = resolve_metric(cik, ticker, "revenue")
    gp = resolve_metric_from_tags(cik, ticker, "gross_profit")
    if rev.empty or gp.empty:
        cor = resolve_metric_from_tags(cik, ticker, "cost_of_revenue")
        if rev.empty or cor.empty:
            return pd.DataFrame(columns=_COLUMNS)
        merged = rev.merge(cor, on="period_end", suffixes=("_rev", "_cor"))
        merged["gm"] = (merged["value_rev"] - merged["value_cor"]) / merged["value_rev"]
        base = rev
    else:
        merged = rev.merge(gp, on="period_end", suffixes=("_rev", "_gp"))
        merged["gm"] = merged["value_gp"] / merged["value_rev"]
        base = rev
    out = base.merge(merged[["period_end", "gm"]], on="period_end", how="inner").copy()
    out["metric"] = "gross_margin"
    out["concept"] = "derived"
    out["value"] = out["gm"].astype(float)
    out = out.drop(columns=["gm"])
    return FUNDAMENTAL_SCHEMA.validate(out[_COLUMNS].dropna(subset=["value"]).reset_index(drop=True))


def resolve_metric_from_tags(cik: str, ticker: str, key: str) -> pd.DataFrame:  # pragma: no cover
    """Like resolve_metric but for helper concept keys (gross_profit, cost_of_revenue)."""
    for tag in CONCEPT_TAGS[key]:
        data = fetch_concept(cik, tag)
        if data and (data.get("units", {}) or {}).get("USD"):
            df = normalize_concept(data, cik=cik, ticker=ticker, metric="revenue", concept=tag)
            if not df.empty:
                return pick_first_filed(df)
    return pd.DataFrame(columns=_COLUMNS)


if __name__ == "__main__":  # pragma: no cover
    run()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd atlas && uv run pytest tests/test_fundamentals.py -v`
Expected: 2 passed. (`normalize_concept` and `pick_first_filed` are the pure, unit-tested
core; network/orchestration carry `# pragma: no cover`.)

- [ ] **Step 5: Commit**

```bash
git add atlas/ingest/fundamentals.py atlas/tests/test_fundamentals.py
git commit -m "feat: SEC fundamentals ingestion (resolver, point-in-time normalize)"
```

---

## Task 4: dbt staging + mart for fundamentals

**Files:**
- Create: `atlas/dbt_project/models/staging/stg_fundamentals.sql`, `atlas/dbt_project/models/marts/fundamentals_quarterly.sql`
- Modify: `atlas/dbt_project/models/staging/schema.yml`, `atlas/dbt_project/models/marts/schema.yml`

- [ ] **Step 1: Create `stg_fundamentals.sql`**

```sql
with src as (
    select * from read_parquet('{{ env_var("ATLAS_DATA_RAW", "../data/raw") }}/fundamentals/*.parquet')
)
select
    cast(cik as varchar)            as cik,
    cast(ticker as varchar)         as ticker,
    cast(metric as varchar)         as metric,
    cast(period_end as date)        as period_end,
    cast(filed as date)             as filed,
    cast(fy as integer)             as fy,
    cast(fiscal_period as varchar)  as fiscal_period,
    cast(form as varchar)           as form,
    cast(value as double)           as value,
    cast(accn as varchar)           as accn
from src
```

- [ ] **Step 2: Create `fundamentals_quarterly.sql`** (pivot to one row per ticker+period, indexed by filed date)

```sql
with q as (
    select ticker, period_end, filed, fy, fiscal_period, metric, value
    from {{ ref('stg_fundamentals') }}
    where fiscal_period in ('Q1', 'Q2', 'Q3', 'Q4')
)
select
    ticker,
    period_end,
    max(filed) as filed,
    any_value(fy) as fy,
    any_value(fiscal_period) as fiscal_period,
    max(case when metric = 'revenue' then value end)      as revenue,
    max(case when metric = 'capex' then value end)        as capex,
    max(case when metric = 'gross_margin' then value end) as gross_margin
from q
group by ticker, period_end
```

- [ ] **Step 3: Add tests to staging `schema.yml`**

```yaml
  - name: stg_fundamentals
    columns:
      - name: ticker
        tests: [not_null]
      - name: metric
        tests:
          - accepted_values:
              values: [revenue, capex, gross_margin]
      - name: value
        tests: [not_null]
    tests:
      - dbt_utils.unique_combination_of_columns:
          combination_of_columns: [cik, metric, period_end, accn]
```

- [ ] **Step 4: Add tests to marts `schema.yml`**

```yaml
  - name: fundamentals_quarterly
    columns:
      - name: ticker
        tests: [not_null]
      - name: period_end
        tests: [not_null]
    tests:
      - dbt_utils.unique_combination_of_columns:
          combination_of_columns: [ticker, period_end]
```

- [ ] **Step 5: Build and verify (with fundamentals present)**

Run: `cd atlas && uv run python -m ingest.fundamentals && cd dbt_project && uv run dbt build --profiles-dir .`
Expected: `stg_fundamentals` + `fundamentals_quarterly` build; all tests pass.
(If SEC network is blocked, STOP — the operator runs `make ingest` + `python -m ingest.fundamentals`.)

- [ ] **Step 6: Commit**

```bash
git add atlas/dbt_project/models/staging/stg_fundamentals.sql \
  atlas/dbt_project/models/marts/fundamentals_quarterly.sql \
  atlas/dbt_project/models/staging/schema.yml \
  atlas/dbt_project/models/marts/schema.yml
git commit -m "feat: dbt fundamentals staging + quarterly mart with tests"
```

---

## Task 5: Lead/lag — quarterly fundamentals pairs

**Files:**
- Modify: `atlas/analysis/leadlag.py`
- Test: `atlas/tests/test_leadlag.py` (append)

- [ ] **Step 1: Write the failing test (append)**

```python
# append to atlas/tests/test_leadlag.py
def test_fundamentals_capex_revenue_pair():
    # upstream capex leads downstream revenue by 1 quarter
    periods = pd.date_range("2016-03-31", periods=32, freq="QE")
    filed = periods + pd.Timedelta(days=40)
    rng = np.random.default_rng(11)
    capex = rng.normal(100, 10, 32)
    fundamentals = pd.DataFrame({
        "ticker": ["up_t"] * 32 + ["down_t"] * 32,
        "period_end": list(periods) * 2,
        "filed": list(filed) * 2,
        "revenue": [np.nan] * 32 + list(np.roll(capex, 1) * 5),
        "capex": list(capex) + [np.nan] * 32,
        "gross_margin": [np.nan] * 64,
    })
    nodes = pd.DataFrame({
        "id": ["up", "down"], "name": ["U", "D"],
        "tickers": ['["up_t"]', '["down_t"]'],
        "stage": ["foundry", "chips"], "region": ["US", "US"], "cik": ["1", "2"],
    })
    edges = pd.DataFrame({
        "from_id": ["up"], "to_id": ["down"], "relationship": ["supplies"],
        "note": [""], "evidence": [""], "as_of": ["2024-01-01"],
    })
    empty_ret = pd.DataFrame(columns=["ticker", "date", "log_return"])
    empty_macro = pd.DataFrame(columns=["series_id", "date", "value"])
    table = build_leadlag_table(empty_ret, empty_macro, nodes, edges,
                                fundamentals=fundamentals, iters=100)
    fund = table[table["pair_type"] == "fund_capex_rev"]
    assert not fund.empty
    assert fund["n_eff"].max() <= 32  # quarterly obs, never daily
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd atlas && uv run pytest tests/test_leadlag.py -k fundamentals_capex -v`
Expected: FAIL — `build_leadlag_table` has no `fundamentals` parameter.

- [ ] **Step 3: Extend `build_leadlag_table` in `atlas/analysis/leadlag.py`**

Add a `fundamentals: pd.DataFrame | None = None` keyword parameter (default `None`). Add a
helper near the other helpers:

```python
def _fund_series(fundamentals: pd.DataFrame, ticker: str, col: str) -> pd.Series:
    """Point-in-time quarterly series for one ticker/metric, indexed by FILED date."""
    sub = fundamentals[fundamentals["ticker"] == ticker][["filed", col]].dropna()
    if sub.empty:
        return pd.Series(dtype=float)
    s = sub.set_index(pd.to_datetime(sub["filed"]))[col].sort_index()
    return s[~s.index.duplicated(keep="first")]
```

Inside `build_leadlag_table`, AFTER the macro block and BEFORE building `df`, add:

```python
    if fundamentals is not None and not fundamentals.empty and not nodes.empty:
        from config import FUND_MAX_LAG_QUARTERS, FUND_NMIN

        def _id_ticker(node_id: str) -> str:
            row = nodes.loc[nodes["id"] == node_id]
            return "" if row.empty else json.loads(row["tickers"].iloc[0])[0]

        # capex -> downstream revenue (edge-aware)
        for _, e in edges.iterrows():
            up = _fund_series(fundamentals, _id_ticker(e["from_id"]), "capex")
            down = _fund_series(fundamentals, _id_ticker(e["to_id"]), "revenue")
            left, right = align_pair(up, down)
            if len(left) < FUND_NMIN:
                continue
            tbl = cross_correlations(left, right, max_lag=FUND_MAX_LAG_QUARTERS).dropna(subset=["corr"])
            if tbl.empty:
                continue
            peak = tbl.loc[tbl["corr"].abs().idxmax()]
            lag = int(peak["lag"])
            x, y = (left.to_numpy()[: len(left) - lag], right.to_numpy()[lag:]) if lag >= 0 \
                else (left.to_numpy()[-lag:], right.to_numpy()[: len(right) + lag])
            p = stationary_bootstrap_pvalue(x, y, iters=iters, block=2, seed=RANDOM_SEED)
            rows.append({
                "pair_type": "fund_capex_rev", "left": e["from_id"], "right": e["to_id"],
                "lag": lag, "corr": float(peak["corr"]), "p_value": p, "q_value": np.nan,
                "n_eff": int(peak["n"]), "stable": _stable_across_halves(left, right, lag),
            })

        # capex -> own price (quarterly returns)
        if not returns.empty:
            for _, node in nodes.iterrows():
                tkr = json.loads(node["tickers"])[0]
                cap = _fund_series(fundamentals, tkr, "capex")
                if tkr not in ret_by_ticker or cap.empty:
                    continue
                pr = resample_returns_to_freq(ret_by_ticker[tkr], "QE")
                left, right = align_pair(cap, pr)
                if len(left) < FUND_NMIN:
                    continue
                tbl = cross_correlations(left, right, max_lag=FUND_MAX_LAG_QUARTERS).dropna(subset=["corr"])
                if tbl.empty:
                    continue
                peak = tbl.loc[tbl["corr"].abs().idxmax()]
                lag = int(peak["lag"])
                x, y = (left.to_numpy()[: len(left) - lag], right.to_numpy()[lag:]) if lag >= 0 \
                    else (left.to_numpy()[-lag:], right.to_numpy()[: len(right) + lag])
                p = stationary_bootstrap_pvalue(x, y, iters=iters, block=2, seed=RANDOM_SEED)
                rows.append({
                    "pair_type": "fund_capex_price", "left": node["id"], "right": node["id"],
                    "lag": lag, "corr": float(peak["corr"]), "p_value": p, "q_value": np.nan,
                    "n_eff": int(peak["n"]), "stable": _stable_across_halves(left, right, lag),
                })
```

The existing single `bh_fdr` call at the end now corrects over price + macro + fundamentals
as one family.

- [ ] **Step 4: Update `run()`** in `leadlag.py` to load fundamentals and pass them:

```python
    fundamentals = con.execute(
        "SELECT ticker, period_end, filed, revenue, capex, gross_margin "
        "FROM fundamentals_quarterly"
    ).fetchdf()
    table = build_leadlag_table(returns, macro, nodes, edges, fundamentals=fundamentals)
```

Wrap the fetch in a try/except `duckdb.CatalogException` returning an empty frame so the
slice still runs if the fundamentals mart is absent.

- [ ] **Step 5: Run test to verify it passes**

Run: `cd atlas && uv run pytest tests/test_leadlag.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add atlas/analysis/leadlag.py atlas/tests/test_leadlag.py
git commit -m "feat: quarterly capex->revenue and capex->price lead/lag"
```

---

## Task 6: App — Fundamentals view

**Files:**
- Modify: `atlas/app/streamlit_app.py`

> UI glue (omitted from coverage). Verified by smoke run.

- [ ] **Step 1: Add a Fundamentals tab**

Change the tab declaration to include a fourth tab and add its body. Read the
`fundamentals_quarterly` table defensively (it may be absent on an older DB):

```python
tab_map, tab_dash, tab_fund, tab_report = st.tabs(
    ["Value-chain map", "Dashboard", "Fundamentals", "Report"]
)
```

```python
with tab_fund:
    try:
        f = _load("fundamentals_quarterly")
    except Exception:
        f = None
    if f is None or f.empty:
        st.info("No fundamentals yet — run `python -m ingest.fundamentals` then `make build`.")
    else:
        st.subheader("Capex by company (quarterly, point-in-time)")
        st.line_chart(f.pivot_table(index="period_end", columns="ticker", values="capex"))
        st.subheader("Revenue by company (quarterly)")
        st.line_chart(f.pivot_table(index="period_end", columns="ticker", values="revenue"))
        ll = _load("leadlag")
        st.subheader("Capex lead/lag (FDR-significant flagged)")
        st.dataframe(ll[ll["pair_type"].isin(["fund_capex_rev", "fund_capex_price"])])
```

- [ ] **Step 2: Smoke-run**

Run: `cd atlas && uv run streamlit run app/streamlit_app.py --server.headless true & sleep 8 && curl -sf localhost:8501 >/dev/null && echo OK; kill %1`
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add atlas/app/streamlit_app.py
git commit -m "feat: Streamlit fundamentals tab (capex/revenue + capex lead/lag)"
```

---

## Task 7: CI fixtures, coverage, schema-version bump

**Files:**
- Create: `atlas/tests/fixtures/fundamentals/NVDA.parquet`
- Modify: `atlas/scripts/publish_release.py`, `atlas/app/data.py`

- [ ] **Step 1: Generate a tiny fundamentals fixture**

Run:
```bash
cd atlas && python -c "
import pandas as pd, pathlib
pathlib.Path('tests/fixtures/fundamentals').mkdir(parents=True, exist_ok=True)
pe = pd.date_range('2020-03-31', periods=16, freq='QE')
rows=[]
for i,d in enumerate(pe):
    rows += [
      dict(cik='0001045810',ticker='NVDA',concept='Revenues',metric='revenue',period_start=d-pd.Timedelta(days=89),period_end=d,filed=d+pd.Timedelta(days=40),fiscal_period='Q'+str((i%4)+1),fy=d.year,form='10-Q',value=5e9+i*1e8,unit='USD',accn=f'a{i}r'),
      dict(cik='0001045810',ticker='NVDA',concept='PaymentsToAcquirePropertyPlantAndEquipment',metric='capex',period_start=d-pd.Timedelta(days=89),period_end=d,filed=d+pd.Timedelta(days=40),fiscal_period='Q'+str((i%4)+1),fy=d.year,form='10-Q',value=3e8+i*1e7,unit='USD',accn=f'a{i}c'),
    ]
pd.DataFrame(rows).to_parquet('tests/fixtures/fundamentals/NVDA.parquet',index=False)
print('wrote', len(rows), 'rows')
"
```

- [ ] **Step 2: Extend CI fixture dbt build** — confirm `.github/workflows/ci.yml`'s dbt step now also runs the fundamentals models (it builds all models via `dbt build`, so no change needed beyond the fixtures existing). The fixture-negation `.gitignore` rule already covers `atlas/tests/fixtures/**/*.parquet`.

- [ ] **Step 3: Bump schema version to 2**

In `atlas/app/data.py`: `APP_SCHEMA_VERSION = "2"`.
In `atlas/scripts/publish_release.py`: `SCHEMA_VERSION = "2"` and add the new tables to
`ROW_COUNT_TABLES`:

```python
ROW_COUNT_TABLES = [
    "prices_daily", "returns", "macro_daily", "graph_nodes", "graph_edges", "leadlag",
    "stg_fundamentals", "fundamentals_quarterly",
]
```

> **Compatibility note:** bumping to `2` means the deployed app (schema `2`) will ignore the
> existing schema-`1` release until the next nightly run publishes a schema-`2` release. That
> is the intended immutable-release behavior; the first post-merge nightly run (or a manual
> `gh workflow run update-data.yml`) makes Layer 2 data live.

- [ ] **Step 4: Verify full suite + fixture build**

Run:
```bash
cd atlas && uv run ruff check . \
 && uv run pytest --cov --cov-report=term-missing --cov-fail-under=80 \
 && uv run python -m ingest.graph \
 && (cd dbt_project && ATLAS_DATA_RAW=../tests/fixtures uv run dbt build --profiles-dir .)
```
Expected: ruff clean, coverage ≥80%, dbt build (incl. fundamentals models) green.

- [ ] **Step 5: Commit**

```bash
git add atlas/tests/fixtures/fundamentals atlas/scripts/publish_release.py atlas/app/data.py
git commit -m "ci: fundamentals fixtures + bump release schema_version to 2"
```

---

## Task 8: Docs

**Files:**
- Modify: `atlas/reports/report.md`, `atlas/README.md`

- [ ] **Step 1: Add a Fundamentals findings section to `report.md`**

Real headings: "Capex as the AI-buildout signal", "Method (point-in-time, quarterly, filed-date aligned)", "Capex→downstream-revenue findings (reads `leadlag` where `pair_type` in fund_*)", "Caveats (US filers only; foreign filers deferred; first-filed, no restatements)".

- [ ] **Step 2: Update `README.md`** — add a Layer 2 bullet (SEC EDGAR fundamentals, US filers, capex lead/lag) and note ASML/TSM fundamentals are deferred to Layer 2b.

- [ ] **Step 3: Commit**

```bash
git add atlas/reports/report.md atlas/README.md
git commit -m "docs: document Layer 2 fundamentals and capex lead/lag"
```

---

## Definition of Done (Layer 2)

- [ ] US-filer nodes carry `cik`; loader validates it (optional for foreign filers).
- [ ] `ingest/fundamentals.py` resolves revenue/capex/gross_margin via concept-fallback, point-in-time on `filed`; pure core unit-tested.
- [ ] dbt `stg_fundamentals` + `fundamentals_quarterly` build with quality tests.
- [ ] `build_leadlag_table` emits `fund_capex_rev` + `fund_capex_price` rows (quarterly, filed-aligned), corrected in one BH-FDR family with price/macro.
- [ ] Streamlit Fundamentals tab renders capex/revenue + capex lead/lag.
- [ ] `ruff` clean, `pytest --cov` ≥80%, dbt fixture build green in CI.
- [ ] `schema_version` bumped to 2 (app + publisher); first schema-2 nightly release makes Layer 2 live.
- [ ] report.md + README updated.
- [ ] Non-goals honored: US filers only, first-filed (no restatements), reported actuals only, descriptive not predictive.
