"""Build a throwaway DuckDB fixture for the Playwright smoke test and CI.

There is NO committed `.duckdb`, and `ingest.graph` alone only creates the
graph tables (no `returns`/`leadlag`), so `export_data.export_all` would raise
"missing required table: leadlag". This script builds a small but complete DB
containing `graph_nodes`, `graph_edges`, `leadlag`, and `returns` so the export
produces real JSON for the front-end to render.

Usage:
    uv run python web/tests/make_fixture_db.py /tmp/atlas_fixture.duckdb
"""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb

# A few nodes across all four stages.
NODES = [
    ("asml", "ASML", '["ASML"]', "equipment", "NL", ""),
    ("amat", "Applied Materials", '["AMAT"]', "equipment", "US", ""),
    ("tsmc", "TSMC", '["TSM"]', "foundry", "TW", ""),
    ("nvidia", "NVIDIA", '["NVDA"]', "chips", "US", "0001045810"),
    ("amd", "AMD", '["AMD"]', "chips", "US", ""),
    ("microsoft", "Microsoft", '["MSFT"]', "cloud", "US", ""),
]

# A couple of forward edges plus one in-house back-edge (cloud -> chips).
EDGES = [
    ("asml", "tsmc", "supplies", "EUV lithography", "", "2024-01-01"),
    ("amat", "tsmc", "supplies", "deposition/etch", "", "2024-01-01"),
    ("tsmc", "nvidia", "supplies", "advanced nodes", "", "2024-01-01"),
    ("tsmc", "amd", "supplies", "advanced nodes", "", "2024-01-01"),
    ("nvidia", "microsoft", "supplies", "GPUs", "", "2024-01-01"),
    ("microsoft", "nvidia", "supplies", "in-house silicon", "", "2024-01-01"),
]

# A couple of lead/lag rows; note the quoted "left"/"right" reserved words.
LEADLAG = [
    ("edge", "asml", "tsmc", 5, 0.6, 0.001, 0.02, 300, True),
    ("edge", "tsmc", "nvidia", 3, 0.45, 0.01, 0.04, 300, True),
]


def build(path: Path) -> None:
    if path.exists():
        path.unlink()
    con = duckdb.connect(str(path))
    try:
        con.execute(
            "CREATE TABLE graph_nodes("
            "id VARCHAR, name VARCHAR, tickers VARCHAR, "
            "stage VARCHAR, region VARCHAR, cik VARCHAR)"
        )
        con.executemany(
            "INSERT INTO graph_nodes VALUES (?, ?, ?, ?, ?, ?)", NODES
        )

        con.execute(
            "CREATE TABLE graph_edges("
            "from_id VARCHAR, to_id VARCHAR, relationship VARCHAR, "
            "note VARCHAR, evidence VARCHAR, as_of VARCHAR)"
        )
        con.executemany(
            "INSERT INTO graph_edges VALUES (?, ?, ?, ?, ?, ?)", EDGES
        )

        con.execute(
            "CREATE TABLE leadlag("
            'pair_type VARCHAR, "left" VARCHAR, "right" VARCHAR, '
            "lag INT, corr DOUBLE, p_value DOUBLE, q_value DOUBLE, "
            "n_eff INT, stable BOOLEAN)"
        )
        con.executemany(
            "INSERT INTO leadlag VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", LEADLAG
        )

        # ~400 daily returns rows for one ticker.
        con.execute(
            "CREATE TABLE returns(ticker VARCHAR, date DATE, log_return DOUBLE)"
        )
        con.execute(
            "INSERT INTO returns "
            "SELECT 'NVDA', DATE '2020-01-01' + INTERVAL (i) DAY, 0.001 "
            "FROM range(0, 400) t(i)"
        )
    finally:
        con.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("out", help="output path for the throwaway DuckDB file")
    args = ap.parse_args()
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    build(out)
    print(f"make_fixture_db: wrote fixture DuckDB to {out}")


if __name__ == "__main__":
    main()
