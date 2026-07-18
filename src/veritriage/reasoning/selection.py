"""Evidence Selection: reduce the graph to a focused working set.

Given a failure, the selector gathers only the evidence a DV engineer would
pull up first: the failing messages, everything linked to them by graph
edges, the run's metadata, coverage context, compile diagnostics, and
warnings in the failing scopes. Thousands of nodes reduce to a bounded,
ordered working set that every later reasoning stage operates on.

Selection is deterministic: same graph in, same working set out.
"""

from __future__ import annotations

from veritriage.graph.graph import EvidenceGraph
from veritriage.graph.model import ArtifactType, EvidenceNode
from veritriage.models import SelectedEvidence, WorkingSet


class EvidenceSelector:
    """Builds the working set for one reasoning run."""

    def __init__(self, max_nodes: int = 40) -> None:
        self.max_nodes = max_nodes

    def select(self, graph: EvidenceGraph) -> WorkingSet:
        """Select the relevant evidence subset, in priority order.

        Priority: failing evidence, then edge-linked neighbors, then run
        metadata, coverage context, compile diagnostics, and warnings in
        failing scopes. Bounded by ``max_nodes``.
        """
        picked: dict[str, SelectedEvidence] = {}

        def admit(node: EvidenceNode, reason: str) -> None:
            if node.id not in picked and len(picked) < self.max_nodes:
                picked[node.id] = SelectedEvidence(node_id=node.id, reason=reason)

        failing = graph.failing()
        for node in failing:
            admit(node, "failing evidence")

        # One hop along every edge touching failing evidence: causal chains,
        # temporal neighbors, correlated coverage, run membership.
        for node in failing:
            for edge in graph.edges:
                if edge.source_id == node.id and edge.target_id in graph.nodes:
                    admit(graph.nodes[edge.target_id], f"linked by {edge.relation.value}")
                elif edge.target_id == node.id and edge.source_id in graph.nodes:
                    admit(graph.nodes[edge.source_id], f"linked by {edge.relation.value}")

        for node in graph.nodes_of_type(ArtifactType.TEST_METADATA):
            admit(node, "test run context")

        for node in graph.nodes_of_type(ArtifactType.COVERAGE):
            if bool(node.attributes.get("is_hole")):
                admit(node, "coverage hole context")

        for node in graph.nodes_of_type(ArtifactType.COMPILE_LOG):
            if node.is_failing:
                admit(node, "compile diagnostics")

        failing_modules = {n.module for n in failing if n.module}
        for node in graph.nodes.values():
            if (
                node.severity is not None
                and node.severity.value == "warning"
                and node.module in failing_modules
            ):
                admit(node, "warning in failing scope")

        return WorkingSet(items=list(picked.values()))
