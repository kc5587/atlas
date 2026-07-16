import pytest

from atlas.graph import GraphEdge, GraphNode, GraphValidationError, ValueChainGraph


def node(node_id: str, stage: str = "compute") -> GraphNode:
    return GraphNode(id=node_id, name=node_id.upper(), stage=stage)


def test_builds_valid_graph_and_exposes_stable_ids() -> None:
    graph = ValueChainGraph.build(
        nodes=(node("chip"), node("model", "software")),
        edges=(GraphEdge(source="chip", target="model", relationship="supplies"),),
    )

    assert graph.node_ids == ("chip", "model")
    assert graph.edges[0].relationship == "supplies"


def test_rejects_duplicate_node_ids() -> None:
    with pytest.raises(GraphValidationError, match="duplicate node id: chip"):
        ValueChainGraph.build(nodes=(node("chip"), node("chip")), edges=())


def test_rejects_edges_to_unknown_nodes() -> None:
    with pytest.raises(GraphValidationError, match="unknown edge target: model"):
        ValueChainGraph.build(
            nodes=(node("chip"),),
            edges=(GraphEdge(source="chip", target="model"),),
        )


def test_rejects_self_loops() -> None:
    with pytest.raises(GraphValidationError, match="self-loop: chip"):
        ValueChainGraph.build(
            nodes=(node("chip"),),
            edges=(GraphEdge(source="chip", target="chip"),),
        )


def test_rejects_invalid_stages() -> None:
    with pytest.raises(GraphValidationError, match="invalid stage: unknown"):
        ValueChainGraph.build(nodes=(node("chip", "unknown"),), edges=())


def test_rejects_cycles() -> None:
    edges = (
        GraphEdge(source="chip", target="model"),
        GraphEdge(source="model", target="app"),
        GraphEdge(source="app", target="chip"),
    )

    with pytest.raises(GraphValidationError, match="graph contains a cycle"):
        ValueChainGraph.build(
            nodes=(node("chip"), node("model", "software"), node("app", "applications")),
            edges=edges,
        )
