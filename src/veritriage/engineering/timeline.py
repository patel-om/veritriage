"""The engineering timeline: a pure, read-only projection of the Evidence Graph.

Orders the run's evidence along the engineering axis:

    commits -> CI run -> compile diagnostics -> simulation failures
            -> waveform observations -> knowledge matches

Wall-clock timestamps order the engineering phase; artifact/sim order (already
deterministic in the graph) orders everything downstream. The projection never
mutates the graph (``test_projections_do_not_mutate`` pins it) and every entry
cites the node it came from.
"""

from __future__ import annotations

from veritriage.graph.graph import EvidenceGraph
from veritriage.graph.model import ArtifactType, EvidenceNode
from veritriage.models import AnalysisReport
from veritriage.models.engineering import TimelineEventView

#: Cap per phase, keeping the report's timeline readable on chatty runs.
_MAX_PER_PHASE = 6


def _event(phase: str, node: EvidenceNode, when: str | None) -> TimelineEventView:
    return TimelineEventView(
        phase=phase,
        label=node.description[:160],
        node_id=node.id,
        when=when,
    )


def build_timeline(graph: EvidenceGraph, report: AnalysisReport) -> list[TimelineEventView]:
    """Assemble the ordered timeline from graph evidence plus knowledge matches."""
    events: list[TimelineEventView] = []

    engineering = graph.nodes_of_type(ArtifactType.ENGINEERING_CHANGE)
    commits = [n for n in engineering if n.attributes.get("kind") == "commit"]
    commits.sort(key=lambda n: (n.attributes.get("timestamp") is None, n.attributes.get("timestamp") or ""))
    for node in commits[-_MAX_PER_PHASE:]:
        events.append(_event("change", node, node.attributes.get("timestamp")))

    for node in engineering:
        if node.attributes.get("kind") == "ci_run":
            events.append(_event("ci", node, node.attributes.get("timestamp")))

    compile_failing = [n for n in graph.nodes_of_type(ArtifactType.COMPILE_LOG) if n.is_failing]
    for node in compile_failing[:_MAX_PER_PHASE]:
        events.append(_event("compile", node, None))

    sim_failing = [
        n
        for n in graph.failing()
        if n.artifact_type in (ArtifactType.SIMULATION_LOG, ArtifactType.ASSERTION)
    ]
    for node in sim_failing[:_MAX_PER_PHASE]:
        events.append(_event("simulation", node, node.sim_time))

    for node in graph.nodes_of_type(ArtifactType.WAVEFORM_METADATA)[:_MAX_PER_PHASE]:
        events.append(_event("waveform", node, node.sim_time))

    if report.knowledge is not None:
        for pattern in report.knowledge.patterns[:_MAX_PER_PHASE]:
            cited = sorted({i for ids in pattern.matched_evidence.values() for i in ids})
            events.append(
                TimelineEventView(
                    phase="knowledge",
                    label=f"Known pattern matched: {pattern.name} ({pattern.pack} pack)",
                    node_id=cited[0] if cited else None,
                    when=None,
                )
            )

    return events
