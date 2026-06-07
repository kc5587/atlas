import duckdb
import pandas as pd

import analysis.leadlag as leadlag_module


EXPECTED_PIPELINE_TABLES = {
    "leadlag",
    "fundamentals_leadlag",
    "capex_price",
    "networking_propagation",
    "networking_pricing",
    "link_momentum",
    "event_drift",
    "vol_premium",
    "vol_termstructure",
    "leading_revenue",
    "macro_sector",
    "power_margins",
    "power_demand",
}


def test_write_table_replaces_table_and_prints_message(capsys):
    con = duckdb.connect(":memory:")
    try:
        first = pd.DataFrame({"ticker": ["NVDA"], "value": [1.0]})
        second = pd.DataFrame({"ticker": ["AMD"], "value": [2.0]})

        leadlag_module._write_table(con, "sample_table", first, "sample: wrote 1 row")
        leadlag_module._write_table(con, "sample_table", second, "sample: wrote 1 row")

        rows = con.execute("SELECT ticker, value FROM sample_table").fetchall()
    finally:
        con.close()

    assert rows == [("AMD", 2.0)]
    assert capsys.readouterr().out == "sample: wrote 1 row\nsample: wrote 1 row\n"


def test_run_writes_expected_pipeline_tables(tmp_path, monkeypatch):
    db_path = tmp_path / "atlas.duckdb"
    con = duckdb.connect(str(db_path))
    try:
        con.execute("CREATE TABLE returns(ticker VARCHAR, date DATE, log_return DOUBLE)")
        con.execute(
            "INSERT INTO returns VALUES "
            "('SOXX', DATE '2024-01-01', 0.01),"
            "('VST', DATE '2024-01-01', 0.02)"
        )
        con.execute("CREATE TABLE macro_daily(series_id VARCHAR, date DATE, value DOUBLE)")
        con.execute(
            "INSERT INTO macro_daily VALUES "
            "('XTEXVA01KRM664S', DATE '2024-01-01', 1.0),"
            "('WPU0543', DATE '2024-01-01', 2.0),"
            "('IPG2211A2N', DATE '2024-01-01', 3.0)"
        )
        con.execute(
            "CREATE TABLE graph_nodes("
            "id VARCHAR, name VARCHAR, tickers VARCHAR, stage VARCHAR, region VARCHAR)"
            ""
        )
        con.execute(
            "INSERT INTO graph_nodes VALUES "
            "('nvidia', 'NVIDIA', '[\"NVDA\"]', 'chips', 'US'),"
            "('cloud', 'Cloud', '[\"MSFT\"]', 'cloud', 'US')"
        )
        con.execute(
            "CREATE TABLE graph_edges("
            "from_id VARCHAR, to_id VARCHAR, relationship VARCHAR, note VARCHAR, "
            "evidence VARCHAR, as_of VARCHAR)"
        )
        con.execute(
            "INSERT INTO graph_edges VALUES "
            "('nvidia', 'cloud', 'supplies', '', '', '2024-01-01')"
        )
        con.execute(
            "CREATE TABLE fundamentals_quarterly("
            "ticker VARCHAR, period_end DATE, filed DATE, revenue DOUBLE, "
            "capex DOUBLE, gross_margin DOUBLE)"
        )
        con.execute(
            "INSERT INTO fundamentals_quarterly VALUES "
            "('NVDA', DATE '2023-12-31', DATE '2024-02-01', 1.0, 2.0, 0.5)"
        )
        con.execute("CREATE TABLE vol_indices(series VARCHAR, date DATE, close DOUBLE)")
        con.execute("INSERT INTO vol_indices VALUES ('^VIX', DATE '2024-01-01', 12.0)")
    finally:
        con.close()

    def frame(name):
        return pd.DataFrame({"source": [name], "value": [1.0]})

    monkeypatch.setattr(leadlag_module, "DUCKDB_PATH", db_path)
    monkeypatch.setattr(
        leadlag_module,
        "compute_leadlag",
        lambda *args, **kwargs: pd.DataFrame(
            {"pair_type": ["macro", "edge"], "value": [1.0, 2.0]}
        ),
    )
    for func_name in (
        "compute_h1",
        "compute_h5",
        "compute_h11",
        "compute_h12",
        "compute_h6",
        "compute_h7",
        "compute_h8",
        "compute_h4",
        "compute_h9",
        "compute_h10",
    ):
        monkeypatch.setattr(
            leadlag_module,
            func_name,
            lambda *args, _func_name=func_name, **kwargs: frame(_func_name),
        )
    monkeypatch.setattr(
        leadlag_module,
        "compute_h15",
        lambda *args, **kwargs: pd.DataFrame(
            [{"slope": 0.1, "p_value": 0.2, "oos_sign_rate": 1.0, "gated": True}]
        ),
    )
    monkeypatch.setattr(
        leadlag_module,
        "compute_h2",
        lambda *args, **kwargs: pd.DataFrame(
            [{"slope": 0.1, "n_events": 2, "p_selection": 0.2, "q_value": 0.2}]
        ),
    )

    leadlag_module.run()

    con = duckdb.connect(str(db_path))
    try:
        tables = {
            row[0]
            for row in con.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'main'"
            ).fetchall()
        }
    finally:
        con.close()

    assert EXPECTED_PIPELINE_TABLES.issubset(tables)
