"""The Evidence Graph: TraceIQ's single source of truth.

Parsers emit :class:`GraphFragment`s; :class:`GraphBuilder` merges and
correlates them into an :class:`EvidenceGraph`; the rule engine classifies
from it and the AI layer reasons over its bounded ``to_reasoning_view()``
and nothing else. See docs/EVIDENCE_GRAPH.md for the design rationale.
"""

from traceiq.graph.builder import GraphBuilder, GraphFragment
from traceiq.graph.graph import EvidenceGraph, GraphStats
from traceiq.graph.model import (
    ArtifactType,
    EvidenceEdge,
    EvidenceNode,
    RelationType,
    make_node_id,
)

__all__ = [
    "ArtifactType",
    "EvidenceEdge",
    "EvidenceGraph",
    "EvidenceNode",
    "GraphBuilder",
    "GraphFragment",
    "GraphStats",
    "RelationType",
    "make_node_id",
]
