"""Base class for classification rules."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from traceiq.models import (
    ClassificationResult,
    Evidence,
    FailureCategory,
    Recommendation,
    SimulationEvent,
)
from traceiq.parsers.base import ParseResult

#: Cap on evidence items per rule so reports stay readable on noisy logs.
MAX_EVIDENCE_ITEMS = 5


class Rule(ABC):
    """One deterministic classification heuristic.

    A rule either abstains (returns ``None``) or returns a verdict with
    confidence and evidence. Rules must be pure functions of the parse
    result — no I/O, no randomness — so a given log always classifies the
    same way.
    """

    #: Unique rule name recorded in the report for provenance.
    name: ClassVar[str]

    #: The failure category this rule can assign.
    category: ClassVar[FailureCategory]

    @abstractmethod
    def evaluate(self, parse_result: ParseResult) -> ClassificationResult | None:
        """Return a verdict for this parse result, or ``None`` to abstain."""
        raise NotImplementedError

    def _result(
        self,
        *,
        confidence: int,
        summary: str,
        events: list[SimulationEvent],
        recommendations: list[Recommendation],
    ) -> ClassificationResult:
        """Build a result from matched events, capping evidence for readability."""
        return ClassificationResult(
            category=self.category,
            confidence=confidence,
            rule_name=self.name,
            summary=summary,
            evidence=[Evidence.from_event(e) for e in events[:MAX_EVIDENCE_ITEMS]],
            recommendations=recommendations,
        )
