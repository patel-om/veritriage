"""Strongly-typed data models shared by every TraceIQ layer.

Parsers produce these models; the rule engine consumes and enriches them;
report generators render them. Nothing downstream of a parser ever touches
raw artifact text again. Note: this package must never import
``traceiq.graph`` at runtime (the graph imports these models).
"""

from traceiq.models.events import Severity, SimulationEvent
from traceiq.models.evidence import Evidence
from traceiq.models.failure import AssertionFailure, Failure, FailureCategory
from traceiq.models.report import (
    AnalysisReport,
    ClassificationResult,
    GraphStats,
    LogSummary,
    Recommendation,
)

__all__ = [
    "AnalysisReport",
    "AssertionFailure",
    "ClassificationResult",
    "Evidence",
    "Failure",
    "FailureCategory",
    "GraphStats",
    "LogSummary",
    "Recommendation",
    "Severity",
    "SimulationEvent",
]
