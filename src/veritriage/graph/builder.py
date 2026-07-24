"""Graph assembly: merge parser fragments, then correlate across artifacts.

Correlation is deterministic and rule-shaped, like the classification rules:
each correlation pass is a pure function of the graph, and every edge it adds
carries a rationale. New artifact types add new correlation passes here; the
rule engine and AI layer are untouched.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from veritriage.graph.graph import EvidenceGraph
from veritriage.graph.model import ArtifactType, EvidenceEdge, EvidenceNode, RelationType


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
        _link_waveform_observations_to_failures(self._graph)
        _link_engineering_changes_to_failures(self._graph)
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


def _link_waveform_observations_to_failures(graph: EvidenceGraph) -> None:
    """A waveform observation in the same scope as a failure corroborates it.

    This is the payoff of M5's ``suggested_signals``: a waveform observation
    about a signal in a failing module now links to the failure, so the report
    can point from "outstanding transaction never retired" straight to the log
    failure it explains. Scope match is conservative: a hierarchy segment of the
    observation's scope (length 3 or more) must appear in the failing node's
    module path or source file, and observations never link to themselves or to
    other waveform nodes.
    """
    observations = [
        n for n in graph.nodes_of_type(ArtifactType.WAVEFORM_METADATA) if n.module
    ]
    if not observations:
        return
    failing = [
        n for n in graph.failing() if n.artifact_type != ArtifactType.WAVEFORM_METADATA
    ]
    if not failing:
        return
    for observation in observations:
        segments = [
            seg.lower() for seg in (observation.module or "").split(".") if len(seg) >= 3
        ]
        if not segments:
            continue
        for node in failing:
            haystack = f"{node.module or ''} {node.attributes.get('source_file') or ''}".lower()
            matched = next((seg for seg in segments if seg in haystack), None)
            if matched is not None:
                graph.add_edge(
                    EvidenceEdge(
                        source_id=observation.id,
                        target_id=node.id,
                        relation=RelationType.CORRELATES_WITH,
                        rationale=(
                            f"Waveform observation in scope '{matched}' matches the scope of "
                            f"this failure."
                        ),
                        confidence=0.6,
                    )
                )


def _link_engineering_changes_to_failures(graph: EvidenceGraph) -> None:
    """A recent change touching the failing scope corroborates the failure.

    This is the "what changed?" edge: a commit whose changed files map to
    modules (or path tokens) appearing in a failing node's module path or
    source file gets a CORRELATES_WITH edge to that failure. Matching is
    conservative (tokens of length 3 or more, exact substring), commits never
    link to other engineering nodes, and the edge carries the overlapping
    token in its rationale so the report can show exactly why the change is
    suspected.
    """
    commits = [
        n
        for n in graph.nodes_of_type(ArtifactType.ENGINEERING_CHANGE)
        if n.attributes.get("kind") == "commit"
    ]
    if not commits:
        return
    failing = [
        n
        for n in graph.failing()
        if n.artifact_type != ArtifactType.ENGINEERING_CHANGE
    ]
    if not failing:
        return
    for commit in commits:
        modules = [m for m in commit.attributes.get("modules", []) if len(str(m)) >= 3]
        stems = [
            stem
            for path in commit.attributes.get("files", [])
            for stem in [str(path).rsplit("/", maxsplit=1)[-1].rsplit(".", maxsplit=1)[0].lower()]
            if len(stem) >= 3
        ]
        tokens = list(dict.fromkeys([*(str(m).lower() for m in modules), *stems]))
        if not tokens:
            continue
        for node in failing:
            haystack = f"{node.module or ''} {node.attributes.get('source_file') or ''}".lower()
            matched = next((t for t in tokens if t in haystack), None)
            if matched is not None:
                graph.add_edge(
                    EvidenceEdge(
                        source_id=commit.id,
                        target_id=node.id,
                        relation=RelationType.CORRELATES_WITH,
                        rationale=(
                            f"Recent change touching '{matched}' matches the scope of this failure."
                        ),
                        confidence=0.6,
                    )
                )
