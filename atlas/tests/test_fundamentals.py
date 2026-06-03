import duckdb
import pandas as pd

from ingest import fundamentals
from ingest.fundamentals import normalize_concept, pick_first_filed


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
