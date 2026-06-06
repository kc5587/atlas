from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import duckdb
import pandas as pd
import yaml
from pydantic import BaseModel, field_validator

Stage = Literal[
    "eda", "equipment", "foundry", "packaging",
    "chips", "networking", "grid", "power", "cloud",
]


class Node(BaseModel):
    id: str
    name: str
    tickers: list[str]
    stage: Stage
    region: str
    cik: str | None = None

    @field_validator("tickers")
    @classmethod
    def _non_empty(cls, v: list[str]) -> list[str]:
        if not v:
            raise ValueError("node must have at least one ticker")
        return v


class Edge(BaseModel):
    from_id: str
    to_id: str
    relationship: Literal["supplies", "partner"]
    note: str = ""
    evidence: str = ""
    as_of: str


def load_graph(yaml_path: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Validate the value-chain YAML and return (nodes_df, edges_df).

    Raises ValueError on duplicate node ids or edges referencing unknown nodes.
    """
    data = yaml.safe_load(Path(yaml_path).read_text())
    raw_nodes = data.get("nodes", []) or []
    raw_edges = data.get("edges", []) or []

    nodes = [Node(**n) for n in raw_nodes]
    ids = [n.id for n in nodes]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate node id in seed")
    id_set = set(ids)

    edges: list[Edge] = []
    for e in raw_edges:
        edge = Edge(
            from_id=e["from"],
            to_id=e["to"],
            relationship=e["relationship"],
            note=e.get("note", ""),
            evidence=e.get("evidence", ""),
            as_of=str(e["as_of"]),
        )
        for endpoint in (edge.from_id, edge.to_id):
            if endpoint not in id_set:
                raise ValueError(f"edge references unknown node: {endpoint}")
        edges.append(edge)

    nodes_df = pd.DataFrame(
        [
            {
                "id": n.id,
                "name": n.name,
                "tickers": json.dumps(n.tickers),
                "stage": n.stage,
                "region": n.region,
                "cik": n.cik or "",
            }
            for n in nodes
        ],
        columns=["id", "name", "tickers", "stage", "region", "cik"],
    )
    edges_df = pd.DataFrame(
        [e.model_dump() for e in edges],
        columns=["from_id", "to_id", "relationship", "note", "evidence", "as_of"],
    )
    return nodes_df, edges_df


def write_graph_to_duckdb(
    con: duckdb.DuckDBPyConnection, nodes: pd.DataFrame, edges: pd.DataFrame
) -> None:
    con.register("nodes_df", nodes)
    con.register("edges_df", edges)
    con.execute("CREATE OR REPLACE TABLE graph_nodes AS SELECT * FROM nodes_df")
    con.execute("CREATE OR REPLACE TABLE graph_edges AS SELECT * FROM edges_df")
    con.unregister("nodes_df")
    con.unregister("edges_df")


def run() -> None:  # pragma: no cover
    from config import DUCKDB_PATH, SEED_PATH

    nodes, edges = load_graph(SEED_PATH)
    Path(DUCKDB_PATH).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DUCKDB_PATH))
    write_graph_to_duckdb(con, nodes, edges)
    con.close()
    print(f"graph: wrote {len(nodes)} nodes, {len(edges)} edges")


if __name__ == "__main__":
    run()
