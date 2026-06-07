import duckdb
import pandas as pd
import pytest

from ingest import fundamentals
from ingest.fundamentals import (
    _strict_mode,
    _validate_cik,
    _validate_tag,
    normalize_concept,
    pick_first_filed,
    stitch_concepts,
)


def _tag_json(rows):
    """rows: list of (end, filed, val)."""
    return {"units": {"USD": [
        {"start": end, "end": end, "val": val, "fy": 2020, "fp": "Q1",
         "form": "10-Q", "filed": filed, "accn": f"a-{i}"}
        for i, (end, filed, val) in enumerate(rows)
    ]}}


def test_stitch_concepts_fills_gaps_and_prefers_priority_tag():
    # Tag A (priority 0) covers 2019-2020; Tag B (priority 1) covers 2020-2021.
    a = normalize_concept(_tag_json([("2019-01-31", "2019-03-01", 100),
                                     ("2020-01-31", "2020-03-01", 110)]),
                          cik="x", ticker="T", metric="capex", concept="TagA")
    b = normalize_concept(_tag_json([("2020-01-31", "2020-03-01", 999),
                                     ("2021-01-31", "2021-03-01", 130)]),
                          cik="x", ticker="T", metric="capex", concept="TagB")
    out = stitch_concepts([a, b])
    ends = sorted(str(d.date()) for d in out["period_end"])
    assert ends == ["2019-01-31", "2020-01-31", "2021-01-31"]   # gap filled from B
    # overlap quarter keeps the priority (A) value, not B's 999
    v2020 = out.loc[out["period_end"] == pd.Timestamp("2020-01-31"), "value"].iloc[0]
    assert v2020 == 110


def test_stitch_concepts_handles_empty_and_single():
    a = normalize_concept(_tag_json([("2020-01-31", "2020-03-01", 50)]),
                          cik="x", ticker="T", metric="capex", concept="TagA")
    assert stitch_concepts([]).empty
    assert len(stitch_concepts([a])) == 1


def _concept_json():
    return {
        "cik": 1045810,
        "tag": "Revenues",
        "units": {
            "USD": [
                {
                    "start": "2023-01-01",
                    "end": "2023-03-31",
                    "val": 7192000000,
                    "fy": 2023,
                    "fp": "Q1",
                    "form": "10-Q",
                    "filed": "2023-05-05",
                    "accn": "acc-1",
                },
                {
                    "start": "2023-01-01",
                    "end": "2023-03-31",
                    "val": 7200000000,
                    "fy": 2023,
                    "fp": "Q1",
                    "form": "10-Q/A",
                    "filed": "2023-08-01",
                    "accn": "acc-2",
                },
                {
                    "start": "2023-04-01",
                    "end": "2023-06-30",
                    "val": 13507000000,
                    "fy": 2023,
                    "fp": "Q2",
                    "form": "10-Q",
                    "filed": "2023-08-21",
                    "accn": "acc-3",
                },
            ]
        },
    }


def test_normalize_concept_long_format():
    out = normalize_concept(
        _concept_json(),
        cik="0001045810",
        ticker="NVDA",
        metric="revenue",
        concept="Revenues",
    )
    assert list(out.columns)[:4] == ["cik", "ticker", "concept", "metric"]
    assert (out["metric"] == "revenue").all()
    assert {"period_end", "filed", "value", "accn"}.issubset(out.columns)
    assert len(out) == 3


def test_pick_first_filed_drops_restatements():
    df = normalize_concept(
        _concept_json(),
        cik="0001045810",
        ticker="NVDA",
        metric="revenue",
        concept="Revenues",
    )
    pit = pick_first_filed(df)
    assert len(pit) == 2
    q1 = pit[pit["period_end"] == pd.Timestamp("2023-03-31")].iloc[0]
    assert q1["value"] == 7192000000
    assert q1["accn"] == "acc-1"


def test_run_skips_failed_metric_and_writes_success(tmp_path, monkeypatch):
    db_path = tmp_path / "atlas.duckdb"
    con = duckdb.connect(str(db_path))
    con.execute("""
        create table graph_nodes as
        select 'nvidia' as id, '["NVDA"]' as tickers, '0001045810' as cik
    """)
    con.close()

    revenue = normalize_concept(
        _concept_json(),
        cik="0001045810",
        ticker="NVDA",
        metric="revenue",
        concept="Revenues",
    )

    def fake_resolve_metric(cik, ticker, metric):
        if metric == "capex":
            raise TimeoutError("SEC timeout")
        return revenue if metric == "revenue" else pd.DataFrame(columns=fundamentals.COLUMNS)

    monkeypatch.setattr(fundamentals.config, "DUCKDB_PATH", db_path)
    monkeypatch.setattr(fundamentals, "DATA_RAW", tmp_path / "raw")
    monkeypatch.setattr(fundamentals, "resolve_metric", fake_resolve_metric)
    monkeypatch.setattr(fundamentals, "_gross_margin", lambda cik, ticker: pd.DataFrame())

    fundamentals.run()

    out = tmp_path / "raw" / "fundamentals" / "NVDA.parquet"
    assert out.exists()
    written = pd.read_parquet(out)
    assert set(written["metric"]) == {"revenue"}


def test_validate_cik_accepts_10_digits_and_rejects_others():
    assert _validate_cik("0000320193") == "0000320193"
    for bad in ("320193", "00003201930", "abc1234567", "../../etc/passwd"):
        with pytest.raises(ValueError):
            _validate_cik(bad)


def test_validate_tag_rejects_path_altering_chars():
    assert _validate_tag("Revenues") == "Revenues"
    for bad in ("Revenues.json", "../Assets", "a/b", "tag?x=1", ""):
        with pytest.raises(ValueError):
            _validate_tag(bad)


def test_strict_mode_reads_env(monkeypatch):
    monkeypatch.delenv("ATLAS_INGEST_STRICT", raising=False)
    assert _strict_mode() is False
    monkeypatch.setenv("ATLAS_INGEST_STRICT", "1")
    assert _strict_mode() is True
