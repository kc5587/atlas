from __future__ import annotations

from pathlib import Path

import duckdb
import networkx as nx
import plotly.graph_objects as go
import streamlit as st

from config import DUCKDB_PATH

st.set_page_config(page_title="Atlas — AI Value Chain", layout="wide")


@st.cache_resource
def _con() -> duckdb.DuckDBPyConnection:
    return duckdb.connect(str(DUCKDB_PATH), read_only=True)


def _load(table: str):
    return _con().execute(f"SELECT * FROM {table}").fetchdf()


def _graph_figure(nodes, edges, leadlag) -> go.Figure:
    g = nx.DiGraph()
    for _, n in nodes.iterrows():
        g.add_node(n["id"], label=n["name"], stage=n["stage"])
    for _, e in edges.iterrows():
        g.add_edge(e["from_id"], e["to_id"])
    pos = nx.spring_layout(g, seed=7)
    edge_x, edge_y = [], []
    for u, v in g.edges():
        edge_x += [pos[u][0], pos[v][0], None]
        edge_y += [pos[u][1], pos[v][1], None]
    node_x = [pos[n][0] for n in g.nodes()]
    node_y = [pos[n][1] for n in g.nodes()]
    labels = [g.nodes[n]["label"] for n in g.nodes()]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=edge_x, y=edge_y, mode="lines",
                             line=dict(width=1, color="#888"), hoverinfo="none"))
    fig.add_trace(go.Scatter(x=node_x, y=node_y, mode="markers+text", text=labels,
                             textposition="top center", marker=dict(size=18)))
    fig.update_layout(showlegend=False, margin=dict(l=10, r=10, t=10, b=10))
    return fig


st.title("Atlas — AI Value-Chain Research Engine")
st.caption("Descriptive lead/lag relationships, not trading signals. Correlation ≠ causation.")

if not Path(DUCKDB_PATH).exists():
    st.warning("No database found. Run `make all` to build it.")
    st.stop()

tab_map, tab_dash, tab_report = st.tabs(["Value-chain map", "Dashboard", "Report"])

with tab_map:
    nodes, edges, leadlag = _load("graph_nodes"), _load("graph_edges"), _load("leadlag")
    st.plotly_chart(_graph_figure(nodes, edges, leadlag), use_container_width=True)
    st.subheader("Measured lead/lag (FDR-significant flagged)")
    st.dataframe(leadlag)

with tab_dash:
    returns = _load("returns")
    st.line_chart(returns.pivot_table(index="date", columns="ticker", values="log_return").cumsum())

with tab_report:
    rp = Path(__file__).resolve().parent.parent / "reports" / "report.md"
    st.markdown(rp.read_text() if rp.exists() else "Report not yet generated.")
