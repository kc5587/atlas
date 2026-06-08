# atlas/web/tests/test_export_data.py
import json
import math
from datetime import date, timedelta
from pathlib import Path

import duckdb
import pytest

import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from export_data import downsample, export_all  # noqa: E402
from tests.make_fixture_db import build as build_web_fixture  # noqa: E402


def _fixture_db(path: Path) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE graph_nodes(id VARCHAR, name VARCHAR, tickers VARCHAR, stage VARCHAR, region VARCHAR, cik VARCHAR)")
    con.execute("INSERT INTO graph_nodes VALUES ('nvidia','NVIDIA','[\"NVDA\"]','chips','US','0001045810')")
    con.execute("INSERT INTO graph_nodes VALUES ('amd','AMD','[\"AMD\"]','chips','US','0000002488')")
    con.execute("CREATE TABLE graph_edges(from_id VARCHAR,to_id VARCHAR,relationship VARCHAR,note VARCHAR,evidence VARCHAR,as_of VARCHAR)")
    con.execute("INSERT INTO graph_edges VALUES ('nvidia','amd','supplies','','','2024-01-01')")
    con.execute(
        "CREATE TABLE leadlag("
        'pair_type VARCHAR, "left" VARCHAR, "right" VARCHAR, '
        "factor_model VARCHAR, corr_raw DOUBLE, corr_resid DOUBLE, "
        "corr_contemporaneous DOUBLE, lag INT, corr DOUBLE, p_value DOUBLE, "
        "q_value DOUBLE, p_selection DOUBLE, oos_sign_rate DOUBLE, "
        "contradicts_thesis BOOLEAN, n_eff INT, stable BOOLEAN)"
    )
    con.execute(
        "INSERT INTO leadlag VALUES "
        "('edge','nvidia','amd','M1_market',0.5,0.5,0.2,2,0.5,0.01,0.05,0.01,0.8,false,300,true),"
        "('edge','nvidia','amd','M2_market_sector',0.5,0.4,0.1,2,0.4,0.02,0.06,0.02,0.7,false,300,true)"
    )
    con.execute("CREATE TABLE returns(ticker VARCHAR, date DATE, log_return DOUBLE)")
    rows = []
    left_idio = [0.0006 * math.sin(i / 3.0) for i in range(400)]
    for i in range(400):
        spy = 0.001 * math.sin(i / 7.0)
        soxx = 0.0015 * math.cos(i / 5.0)
        nvda = 1.1 * spy + 0.9 * soxx + left_idio[i]
        amd = 1.0 * spy + 1.0 * soxx + (left_idio[i - 5] if i >= 5 else 0.0)
        day = date(2020, 1, 1) + timedelta(days=i)
        rows.extend([
            ("SPY", day, spy),
            ("SOXX", day, soxx),
            ("NVDA", day, nvda),
            ("AMD", day, amd),
        ])
    con.executemany("INSERT INTO returns VALUES (?, ?, ?)", rows)
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
    assert meta["schema_version"] == "3"
    assert meta["stages"] == [
        "eda", "equipment", "foundry", "packaging", "chips",
        "networking", "grid", "power", "cloud",
    ]


def test_fixture_db_exports_fundamentals(tmp_path):
    db = tmp_path / "fixture.duckdb"
    build_web_fixture(db)
    con = duckdb.connect(str(db), read_only=True)
    out = tmp_path / "data"
    export_all(con, out)
    con.close()

    series = json.loads((out / "series.json").read_text())
    leadlag = json.loads((out / "leadlag.json").read_text())
    assert "fundamentals" in series
    assert series["fundamentals"]["NVDA"]["capex"][0]["value"] == 248000000.0
    assert {row["pair_type"] for row in leadlag} >= {"fund_capex_rev", "fund_capex_price"}


def test_export_writes_correlogram(tmp_path):
    db = tmp_path / "atlas.duckdb"
    con = _fixture_db(db)
    out = tmp_path / "data"
    export_all(con, out)
    con.close()

    cg = json.loads((out / "correlogram.json").read_text())
    assert "pair" in cg and "left" in cg["pair"] and "right" in cg["pair"]
    assert isinstance(cg["points"], list) and len(cg["points"]) >= 1
    row = cg["points"][0]
    assert {"lag", "corr", "ci_lo", "ci_hi", "is_peak", "passes_fdr"} <= set(row)
    lag0 = next(point for point in cg["points"] if point["lag"] == 0)
    assert abs(lag0["corr"]) < 0.2


def test_export_writes_vrp(tmp_path):
    db = tmp_path / "atlas.duckdb"
    con = _fixture_db(db)
    con.execute("CREATE TABLE vol_indices(series VARCHAR, date DATE, close DOUBLE)")
    con.execute(
        "INSERT INTO vol_indices SELECT '^VIX', DATE '2020-01-01' + INTERVAL (i) DAY, 20.0 "
        "FROM range(0,120) t(i)"
    )
    out = tmp_path / "data"
    export_all(con, out)
    con.close()

    vrp = json.loads((out / "vrp.json").read_text())
    assert "pair" in vrp and isinstance(vrp["points"], list)
    if vrp["points"]:
        row = vrp["points"][0]
        assert {"date", "implied_var", "realized_var", "vrp"} <= set(row)


def test_export_all_missing_required_table_raises(tmp_path):
    db = tmp_path / "x.duckdb"
    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE graph_nodes(id VARCHAR)")  # missing edges/leadlag
    with pytest.raises(RuntimeError, match="missing required table"):
        export_all(con, tmp_path / "out")
    con.close()
