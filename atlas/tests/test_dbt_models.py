from pathlib import Path


def test_graph_nodes_model_preserves_cik():
    sql = Path("dbt_project/models/graph/graph_nodes.sql").read_text()
    assert "cik" in sql
