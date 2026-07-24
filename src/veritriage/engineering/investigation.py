"""The investigation view: how the conclusion hangs together, as a projection.

Deliberately NOT a new graph. The Evidence Graph is the single source of
truth; this module groups its nodes into intelligence layers (engineering,
artifacts, waveform, knowledge-cited, hypotheses) and lists the cross-layer
edges among them, producing the substrate a future interactive visualization
renders. Building the view never mutates the graph
(``test_projections_do_not_mutate`` pins it).
"""

from __future__ import annotations

from veritriage.graph.graph import EvidenceGraph
from veritriage.graph.model import ArtifactType
from veritriage.models import AnalysisReport
from veritriage.models.engineering import (
    InvestigationEdgeView,
    InvestigationLayerView,
    InvestigationView,
)

#: Artifact types grouped into each investigation layer, in display order.
_LAYER_TYPES: tuple[tuple[str, tuple[ArtifactType, ...]], ...] = (
    ("engineering", (ArtifactType.ENGINEERING_CHANGE,)),
    (
        "artifacts",
        (
            ArtifactType.COMPILE_LOG,
            ArtifactType.SIMULATION_LOG,
            ArtifactType.ASSERTION,
            ArtifactType.COVERAGE,
            ArtifactType.TEST_METADATA,
        ),
    ),
    ("waveform", (ArtifactType.WAVEFORM_METADATA,)),
)

#: Bound per layer, keeping the projection summary-sized.
_MAX_PER_LAYER = 12


def build_investigation(graph: EvidenceGraph, report: AnalysisReport) -> InvestigationView:
    """Group the interesting evidence by layer and collect cross-layer edges.

    "Interesting" means: in the reasoning working set, cited by a signal or
    hypothesis, or an engineering/waveform node - the evidence an engineer
    would actually walk when auditing the conclusion.
    """
    interesting: set[str] = set()
    if report.reasoning is not None:
        interesting.update(report.reasoning.working_set.node_ids)
        for signal in report.reasoning.signals:
            interesting.update(signal.evidence_ids)
        for hypothesis in report.reasoning.hypotheses:
            interesting.update(hypothesis.evidence_ids)
    for artifact_type in (ArtifactType.ENGINEERING_CHANGE, ArtifactType.WAVEFORM_METADATA):
        interesting.update(n.id for n in graph.nodes_of_type(artifact_type))

    layers: list[InvestigationLayerView] = []
    node_layer: dict[str, str] = {}
    for name, types in _LAYER_TYPES:
        ids = [
            n.id for n in graph.nodes_of_type(*types) if n.id in interesting
        ][:_MAX_PER_LAYER]
        for node_id in ids:
            node_layer[node_id] = name
        layers.append(InvestigationLayerView(name=name, node_ids=ids))

    # Knowledge and hypotheses are conclusions over evidence, not evidence
    # nodes themselves; their layers list the evidence they cite.
    if report.knowledge is not None and report.knowledge.patterns:
        cited = sorted(
            {
                i
                for p in report.knowledge.patterns
                for ids in p.matched_evidence.values()
                for i in ids
            }
        )[:_MAX_PER_LAYER]
        layers.append(InvestigationLayerView(name="knowledge", node_ids=cited))
    if report.reasoning is not None and report.reasoning.hypotheses:
        top = report.reasoning.hypotheses[0]
        layers.append(
            InvestigationLayerView(
                name="hypotheses", node_ids=sorted(top.evidence_ids)[:_MAX_PER_LAYER]
            )
        )

    cross_edges = [
        InvestigationEdgeView(
            source_id=edge.source_id,
            target_id=edge.target_id,
            relation=edge.relation.value,
            rationale=edge.rationale,
        )
        for edge in graph.edges
        if node_layer.get(edge.source_id)
        and node_layer.get(edge.target_id)
        and node_layer[edge.source_id] != node_layer[edge.target_id]
    ]

    return InvestigationView(layers=layers, cross_edges=cross_edges)
