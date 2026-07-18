"""The EvidenceGraph container: storage, queries, stats, and the AI view."""

from __future__ import annotations

from typing import Any, Iterable

from pydantic import BaseModel, Field

from veritriage.graph.model import ArtifactType, EvidenceEdge, EvidenceNode
from veritriage.models.events import Severity
from veritriage.models.report import GraphStats


class EvidenceGraph(BaseModel):
    """Normalized evidence from every parsed artifact, plus their relationships.

    Nodes preserve insertion order (parse order per artifact, artifacts in the
    order given), so all queries are deterministic. Edges may only reference
    nodes that exist; `add_edge` enforces it.
    """

    schema_version: str = "1"
    nodes: dict[str, EvidenceNode] = Field(default_factory=dict)
    edges: list[EvidenceEdge] = Field(default_factory=list)

    # --- Construction ------------------------------------------------------

    def add_node(self, node: EvidenceNode) -> EvidenceNode:
        """Add a node; an identical re-add is a no-op (IDs are content-derived).

        Raises:
            ValueError: If a different node already uses the same ID.
        """
        existing = self.nodes.get(node.id)
        if existing is not None and existing != node:
            raise ValueError(f"Node ID collision for {node.id}: differing content")
        self.nodes[node.id] = node
        return node

    def add_edge(self, edge: EvidenceEdge) -> EvidenceEdge:
        """Add an edge between two existing nodes.

        Raises:
            KeyError: If either endpoint is not in the graph.
        """
        for endpoint in (edge.source_id, edge.target_id):
            if endpoint not in self.nodes:
                raise KeyError(f"Edge references unknown node {endpoint!r}")
        if edge not in self.edges:
            self.edges.append(edge)
        return edge

    def merge(self, nodes: Iterable[EvidenceNode], edges: Iterable[EvidenceEdge]) -> None:
        """Add a batch of nodes, then edges (so edges can reference the batch)."""
        for node in nodes:
            self.add_node(node)
        for edge in edges:
            self.add_edge(edge)

    # --- Queries (all deterministic) ---------------------------------------

    def nodes_of_type(self, *artifact_types: ArtifactType) -> list[EvidenceNode]:
        """Nodes of the given artifact types, in insertion order."""
        wanted = set(artifact_types)
        return [n for n in self.nodes.values() if n.artifact_type in wanted]

    def failing(self) -> list[EvidenceNode]:
        """Error/fatal nodes in insertion order."""
        return [n for n in self.nodes.values() if n.is_failing]

    def with_severity(self, severity: Severity) -> list[EvidenceNode]:
        """Nodes carrying exactly the given severity."""
        return [n for n in self.nodes.values() if n.severity == severity]

    def edges_from(self, node_id: str) -> list[EvidenceEdge]:
        return [e for e in self.edges if e.source_id == node_id]

    def edges_to(self, node_id: str) -> list[EvidenceEdge]:
        return [e for e in self.edges if e.target_id == node_id]

    def neighbors(self, node_id: str) -> list[EvidenceNode]:
        """Nodes connected to ``node_id`` by any edge, in edge order."""
        seen: dict[str, EvidenceNode] = {}
        for edge in self.edges:
            other = None
            if edge.source_id == node_id:
                other = edge.target_id
            elif edge.target_id == node_id:
                other = edge.source_id
            if other is not None and other not in seen:
                seen[other] = self.nodes[other]
        return list(seen.values())

    def stats(self) -> GraphStats:
        """Aggregate counts by artifact type and relation."""
        by_type: dict[str, int] = {}
        for node in self.nodes.values():
            key = node.artifact_type.value
            by_type[key] = by_type.get(key, 0) + 1
        by_relation: dict[str, int] = {}
        for edge in self.edges:
            key = edge.relation.value
            by_relation[key] = by_relation.get(key, 0) + 1
        return GraphStats(
            node_count=len(self.nodes),
            edge_count=len(self.edges),
            nodes_by_type=by_type,
            edges_by_relation=by_relation,
        )

    # --- The AI boundary ---------------------------------------------------

    def to_reasoning_view(
        self, max_nodes: int = 60, node_ids: set[str] | None = None
    ) -> dict[str, Any]:
        """The ONLY payload the AI layer is allowed to consume.

        A bounded, normalized projection of the graph: failing evidence first,
        then non-message context (coverage, test metadata), then the edges
        among the included nodes. Raw artifacts never appear here, so any AI
        claim is checkable against node IDs and their artifact locations.
        """
        ordered: list[EvidenceNode] = []
        seen: set[str] = set()
        for group in (
            self.failing(),
            self.nodes_of_type(ArtifactType.TEST_METADATA, ArtifactType.COVERAGE),
            self.with_severity(Severity.WARNING),
        ):
            for node in group:
                if node_ids is not None and node.id not in node_ids:
                    continue
                if node.id not in seen:
                    seen.add(node.id)
                    ordered.append(node)
                if len(ordered) >= max_nodes:
                    break
            if len(ordered) >= max_nodes:
                break

        included = {n.id for n in ordered}
        return {
            "nodes": [
                {
                    "id": n.id,
                    "artifact_type": n.artifact_type.value,
                    "description": n.description,
                    "severity": n.severity.value if n.severity else None,
                    "confidence": n.confidence,
                    "sim_time": n.sim_time,
                    "source": {"path": n.source_path, "line": n.line_number},
                    "module": n.module,
                }
                for n in ordered
            ],
            "edges": [
                {
                    "source": e.source_id,
                    "target": e.target_id,
                    "relation": e.relation.value,
                    "rationale": e.rationale,
                }
                for e in self.edges
                if e.source_id in included and e.target_id in included
            ],
        }
