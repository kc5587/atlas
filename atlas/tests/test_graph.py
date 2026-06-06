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


def test_load_graph_returns_nodes_and_edges(tmp_path):
    p = tmp_path / "g.yml"
    p.write_text(VALID)
    nodes, edges = load_graph(p)
    assert set(nodes.columns) == {"id", "name", "tickers", "stage", "region", "cik"}
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


def test_node_carries_cik(tmp_path):
    p = tmp_path / "g.yml"
    p.write_text(VALID_WITH_CIK)
    nodes, _ = load_graph(p)
    assert "cik" in nodes.columns
    assert nodes.loc[nodes["id"] == "nvidia", "cik"].iloc[0] == "0001045810"


def test_node_cik_optional(tmp_path):
    p = tmp_path / "g.yml"
    p.write_text(VALID)
    nodes, _ = load_graph(p)
    assert "cik" in nodes.columns
    assert nodes["cik"].isna().all() or (nodes["cik"] == "").all()


NEW_STAGE = """
nodes:
  - id: arista
    name: Arista Networks
    tickers: [ANET]
    stage: networking
    region: US
edges: []
"""


def test_new_stages_validate(tmp_path):
    p = tmp_path / "g.yml"
    p.write_text(NEW_STAGE)
    nodes, _ = load_graph(p)
    assert nodes.loc[nodes["id"] == "arista", "stage"].iloc[0] == "networking"


def test_seed_has_new_stage_nodes():
    from config import SEED_PATH

    nodes, _ = load_graph(SEED_PATH)
    by_stage = nodes.groupby("stage")["id"].apply(set).to_dict()
    assert by_stage.get("eda") == {"synopsys", "cadence"}
    assert by_stage.get("packaging") == {"amkor"}
    assert by_stage.get("networking") == {"arista", "marvell", "astera_labs"}
    assert by_stage.get("grid") == {"ge_vernova", "quanta"}
    assert len(nodes) == 29


def test_power_stage_nodes_and_edges_load():
    from config import SEED_PATH

    nodes, edges = load_graph(SEED_PATH)
    power = nodes[nodes["stage"] == "power"]
    assert set(power["id"]) >= {"vistra", "constellation", "vertiv", "dominion"}
    cloud_ids = set(nodes[nodes["stage"] == "cloud"]["id"])
    power_ids = set(power["id"])
    assert ((edges["from_id"].isin(cloud_ids)) & (edges["to_id"].isin(power_ids))).any()


def test_seed_has_new_supply_edges():
    from config import SEED_PATH

    _, edges = load_graph(SEED_PATH)
    pairs = set(zip(edges["from_id"], edges["to_id"]))
    assert ("synopsys", "nvidia") in pairs
    assert ("cadence", "broadcom") in pairs
    assert ("amkor", "nvidia") in pairs
    assert ("broadcom", "arista") in pairs
    assert ("arista", "microsoft") in pairs
    assert ("marvell", "amazon") in pairs
    assert ("astera_labs", "microsoft") in pairs
    assert ("ge_vernova", "constellation") in pairs
    assert ("quanta", "dominion") in pairs
    # every new edge must carry a citation (evidence non-empty)
    new_from = {"synopsys", "cadence", "amkor", "broadcom", "arista",
                "marvell", "astera_labs", "ge_vernova", "quanta"}
    cited = edges[edges["from_id"].isin(new_from)]
    assert (cited["evidence"].str.len() > 0).all()
