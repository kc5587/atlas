"""H11/H12: networking-stage signals.

Reuses the H1 (capex->revenue) and H5 (capex->price) engines on a REVERSED edge
subset so they compute *customer (hyperscaler) capex -> supplier (networking)
revenue / forward returns* -- the demand-pull direction, opposite to H1's
upstream->downstream orientation. Networking is excluded from the H1/H5 core
families (see analysis/leadlag.py::run) so those verdicts are unchanged.
"""
from __future__ import annotations

import pandas as pd

NETWORKING_STAGE = "networking"
CUSTOMER_STAGE = "cloud"


def networking_capex_edges(nodes: pd.DataFrame, edges: pd.DataFrame) -> pd.DataFrame:
    """Graph edges networking->cloud, returned REVERSED as cloud->networking.

    Result rows have from_id = hyperscaler customer, to_id = networking supplier,
    so capex_revenue_edges / capex_price_edges test customer.capex -> supplier.*.
    """
    stage = dict(zip(nodes["id"], nodes["stage"]))
    rows = []
    for e in edges.itertuples():
        if stage.get(e.from_id) == NETWORKING_STAGE and stage.get(e.to_id) == CUSTOMER_STAGE:
            rows.append({"from_id": e.to_id, "to_id": e.from_id, "relationship": "supplies"})
    return pd.DataFrame(rows, columns=["from_id", "to_id", "relationship"])


def networking_propagation(fundamentals: pd.DataFrame, nodes: pd.DataFrame,
                           edges: pd.DataFrame, *, iters: int, seed: int) -> pd.DataFrame:
    """H11: hyperscaler capex -> networking-supplier revenue (reuses H1 engine)."""
    from analysis.fundamentals_leadlag import capex_revenue_edges

    rev_edges = networking_capex_edges(nodes, edges)
    return capex_revenue_edges(fundamentals, nodes, rev_edges, iters=iters, seed=seed)


def networking_pricing(fundamentals: pd.DataFrame, returns: pd.DataFrame,
                       factors: dict, nodes: pd.DataFrame, edges: pd.DataFrame,
                       *, horizons, iters: int, seed: int) -> pd.DataFrame:
    """H12: is the buildout priced into networking equity? (reuses H5 engine)."""
    from analysis.capex_price import capex_price_edges

    rev_edges = networking_capex_edges(nodes, edges)
    return capex_price_edges(fundamentals, returns, factors, nodes, rev_edges,
                             horizons=horizons, iters=iters, seed=seed)
