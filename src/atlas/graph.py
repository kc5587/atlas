"""Validated, immutable value-chain graph primitives."""

from dataclasses import dataclass


VALID_STAGES = frozenset(
    {"compute", "semiconductor", "network", "power", "software", "applications"}
)


class GraphValidationError(ValueError):
    """Raised when a value-chain graph violates a domain invariant."""


@dataclass(frozen=True, slots=True)
class GraphNode:
    """A named entity in the value chain."""

    id: str
    name: str
    stage: str
    ticker: str | None = None


@dataclass(frozen=True, slots=True)
class GraphEdge:
    """A directed relationship between two graph nodes."""

    source: str
    target: str
    relationship: str = "related"


@dataclass(frozen=True, slots=True)
class ValueChainGraph:
    """An immutable graph whose structure has passed domain validation."""

    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]

    @classmethod
    def build(
        cls, nodes: tuple[GraphNode, ...], edges: tuple[GraphEdge, ...]
    ) -> "ValueChainGraph":
        normalized_nodes = tuple(nodes)
        normalized_edges = tuple(edges)
        node_ids = _validate_nodes(normalized_nodes)
        _validate_edges(normalized_edges, node_ids)
        _validate_acyclic(normalized_edges, node_ids)
        return cls(nodes=normalized_nodes, edges=normalized_edges)

    @property
    def node_ids(self) -> tuple[str, ...]:
        """Return node IDs in their declared, stable order."""

        return tuple(node.id for node in self.nodes)


def _validate_nodes(nodes: tuple[GraphNode, ...]) -> frozenset[str]:
    seen: set[str] = set()
    for graph_node in nodes:
        if graph_node.id in seen:
            raise GraphValidationError(f"duplicate node id: {graph_node.id}")
        if graph_node.stage not in VALID_STAGES:
            raise GraphValidationError(f"invalid stage: {graph_node.stage}")
        seen.add(graph_node.id)
    return frozenset(seen)


def _validate_edges(edges: tuple[GraphEdge, ...], node_ids: frozenset[str]) -> None:
    for edge in edges:
        if edge.source not in node_ids:
            raise GraphValidationError(f"unknown edge source: {edge.source}")
        if edge.target not in node_ids:
            raise GraphValidationError(f"unknown edge target: {edge.target}")
        if edge.source == edge.target:
            raise GraphValidationError(f"self-loop: {edge.source}")


def _validate_acyclic(edges: tuple[GraphEdge, ...], node_ids: frozenset[str]) -> None:
    adjacency = {node_id: set() for node_id in node_ids}
    indegree = dict.fromkeys(node_ids, 0)
    for edge in edges:
        if edge.target not in adjacency[edge.source]:
            adjacency[edge.source].add(edge.target)
            indegree[edge.target] += 1

    ready = [node_id for node_id, degree in indegree.items() if degree == 0]
    visited = 0
    while ready:
        current = ready.pop()
        visited += 1
        for target in adjacency[current]:
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)

    if visited != len(node_ids):
        raise GraphValidationError("graph contains a cycle")
