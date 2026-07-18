"""Base class for classification rules (graph-native since v2)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from traceiq.graph.graph import EvidenceGraph
from traceiq.graph.model import EvidenceNode
from traceiq.models import ClassificationResult, Evidence, FailureCategory, Recommendation

#: Cap on evidence items per rule so reports stay readable on noisy logs.
MAX_EVIDENCE_ITEMS = 5


class Rule(ABC):
    """One deterministic classification heuristic over the Evidence Graph.

    A rule either abstains (returns ``None``) or returns a verdict with
    confidence and evidence. Rules must be pure functions of the graph -
    no I/O, no randomness - so a given set of artifacts always classifies
    the same way. Rules query the graph only; they never see raw files.
    """

    #: Unique rule name recorded in the report for provenance.
    name: ClassVar[str]

    #: The failure category this rule can assign.
    category: ClassVar[FailureCategory]

    @abstractmethod
    def evaluate(self, graph: EvidenceGraph) -> ClassificationResult | None:
        """Return a verdict for this graph, or ``None`` to abstain."""
        raise NotImplementedError

    def _result(
        self,
        *,
        confidence: int,
        summary: str,
        nodes: list[EvidenceNode],
        recommendations: list[Recommendation],
    ) -> ClassificationResult:
        """Build a result from matched nodes, capping evidence for readability."""
        return ClassificationResult(
            category=self.category,
            confidence=confidence,
            rule_name=self.name,
            summary=summary,
            evidence=[Evidence.from_node(n) for n in nodes[:MAX_EVIDENCE_ITEMS]],
            recommendations=recommendations,
        )
