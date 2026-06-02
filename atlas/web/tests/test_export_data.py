# atlas/web/tests/test_export_data.py
import json
from pathlib import Path

import duckdb
import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from export_data import downsample, export_all  # noqa: E402


def _fixture_db(path: Path) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE graph_nodes(id VARCHAR, name VARCHAR, tickers VARCHAR, stage VARCHAR, region VARCHAR, cik VARCHAR)")
    con.execute("INSERT INTO graph_nodes VALUES ('nvidia','NVIDIA','[\"NVDA\"]','chips','US','0001045810')")
    con.execute("CREATE TABLE graph_edges(from_id VARCHAR,to_id VARCHAR,relationship VARCHAR,note VARCHAR,evidence VARCHAR,as_of VARCHAR)")
    con.execute("INSERT INTO graph_edges VALUES ('nvidia','nvidia','supplies','','','2024-01-01')")
    con.execute("CREATE TABLE leadlag(pair_type VARCHAR,\"left\" VARCHAR,\"right\" VARCHAR,lag INT,corr DOUBLE,p_value DOUBLE,q_value DOUBLE,n_eff INT,stable BOOLEAN)")
    con.execute("INSERT INTO leadlag VALUES ('edge','nvidia','nvidia',2,0.5,0.01,0.05,300,true)")
    con.execute("CREATE TABLE returns(ticker VARCHAR, date DATE, log_return DOUBLE)")
    con.execute("INSERT INTO returns SELECT 'NVDA', DATE '2020-01-01' + INTERVAL (i) DAY, 0.001 FROM range(0,400) t(i)")
    return con


def test_downsample_reduces_points():
    pts = [{"date": f"2020-01-{i:02d}", "value": float(i)} for i in range(1, 29)]
    out = downsample(pts, max_points=10)
    assert len(out) <= 10
    assert out[0] == pts[0] and out[-1] == pts[-1]  # endpoints preserved


def test_export_all_writes_expected_files(tmp_path):
    db = tmp_path / "atlas.duckdb"
    con = _fixture_db(db)
    out = tmp_path / "data"
    export_all(con, out)
    con.close()
    for name in ("graph.json", "leadlag.json", "series.json", "meta.json"):
        assert (out / name).exists(), name
    graph = json.loads((out / "graph.json").read_text())
    assert graph["nodes"][0]["tickers"] == ["NVDA"]   # JSON-parsed, not a string
    assert "criticality" in graph["nodes"][0]
    assert graph["edges"][0]["from_id"] == "nvidia"
    meta = json.loads((out / "meta.json").read_text())
    assert meta["schema_version"] == "2"


def test_export_all_missing_required_table_raises(tmp_path):
    db = tmp_path / "x.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE graph_nodes(id VARCHAR)")  # missing edges/leadlag
    with pytest.raises(RuntimeError, match="missing required table"):
        export_all(con, tmp_path / "out")
    con.close()
