"""The Evidence Graph: VeriTriage's single source of truth.

Parsers emit :class:`GraphFragment`s; :class:`GraphBuilder` merges and
correlates them into an :class:`EvidenceGraph`; the rule engine classifies
from it and the AI layer reasons over its bounded ``to_reasoning_view()``
and nothing else. See docs/EVIDENCE_GRAPH.md for the design rationale.
"""

from veritriage.graph.builder import GraphBuilder, GraphFragment
from veritriage.graph.graph import EvidenceGraph, GraphStats
from veritriage.graph.model import (
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
