from pathlib import Path


def test_graph_nodes_model_preserves_cik():
    sql = Path("dbt_project/models/graph/graph_nodes.sql").read_text()
    assert "cik" in sql


def test_vol_models_exist_and_select_expected_columns():
    root = Path(__file__).resolve().parents[1] / "dbt_project" / "models"
    stg = (root / "staging" / "stg_vol.sql").read_text()
    mart = (root / "marts" / "vol_indices.sql").read_text()
    assert "read_parquet" in stg and "vol/*.parquet" in stg
    assert "stg_vol" in mart
    for col in ("series", "date", "close"):
        assert col in stg and col in mart


def test_iv_snapshot_models_exist():
    root = Path(__file__).resolve().parents[1] / "dbt_project" / "models"
    stg = (root / "staging" / "stg_iv_snapshots.sql").read_text()
    mart = (root / "marts" / "iv_snapshots.sql").read_text()
    assert "iv_snapshots/panel.parquet" in stg or "iv_snapshots/*.parquet" in stg
    assert "stg_iv_snapshots" in mart
