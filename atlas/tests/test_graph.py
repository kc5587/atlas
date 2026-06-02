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
