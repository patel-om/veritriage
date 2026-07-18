"""Graph assembly: merge parser fragments, then correlate across artifacts.

Correlation is deterministic and rule-shaped, like the classification rules:
each correlation pass is a pure function of the graph, and every edge it adds
carries a rationale. New artifact types add new correlation passes here; the
rule engine and AI layer are untouched.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from traceiq.graph.graph import EvidenceGraph
from traceiq.graph.model import ArtifactType, EvidenceEdge, EvidenceNode, RelationType


class GraphFragment(BaseModel):
    """What one parser emits: its nodes plus intra-artifact edges."""

    nodes: list[EvidenceNode] = Field(default_factory=list)
    edges: list[EvidenceEdge] = Field(default_factory=list)


class GraphBuilder:
    """Accumulates fragments and produces a correlated EvidenceGraph."""

    def __init__(self) -> None:
        self._graph = EvidenceGraph()

    def add_fragment(self, fragment: GraphFragment) -> None:
        """Merge one parser's output into the graph under construction."""
        self._graph.merge(fragment.nodes, fragment.edges)

    def build(self) -> EvidenceGraph:
        """Run all correlation passes and return the finished graph."""
        _link_events_to_test_runs(self._graph)
        _link_coverage_holes_to_failures(self._graph)
        return self._graph


# --- Correlation passes ----------------------------------------------------


def _link_events_to_test_runs(graph: EvidenceGraph) -> None:
    """Failing evidence is PART_OF the test run described by test metadata."""
    test_nodes = graph.nodes_of_type(ArtifactType.TEST_METADATA)
    if not test_nodes:
        return
    run = test_nodes[0]
    for node in graph.failing():
        graph.add_edge(
            EvidenceEdge(
                source_id=node.id,
                target_id=run.id,
                relation=RelationType.PART_OF,
                rationale="Failure occurred in the run described by this test metadata.",
            )
        )


def _link_coverage_holes_to_failures(graph: EvidenceGraph) -> None:
    """A coverage hole in the same scope as a failure is worth surfacing.

    Scope match is deliberately conservative: the hole's last hierarchy
    segment must appear in the failing node's module path or source file.
    """
    holes = [
        n
        for n in graph.nodes_of_type(ArtifactType.COVERAGE)
        if bool(n.attributes.get("is_hole"))
    ]
    if not holes:
        return
    failing = graph.failing()
    for hole in holes:
        segment = (hole.module or "").rsplit(".", maxsplit=1)[-1].lower()
        if not segment:
            continue
        for node in failing:
            haystack = f"{node.module or ''} {node.attributes.get('source_file') or ''}".lower()
            if segment in haystack:
                graph.add_edge(
                    EvidenceEdge(
                        source_id=hole.id,
                        target_id=node.id,
                        relation=RelationType.CORRELATES_WITH,
                        rationale=(
                            f"Coverage hole in scope '{segment}' matches the scope of this failure."
                        ),
                        confidence=0.7,
                    )
                )
