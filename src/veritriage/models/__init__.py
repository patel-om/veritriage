"""Strongly-typed data models shared by every VeriTriage layer.

Parsers produce these models; the rule engine consumes and enriches them;
report generators render them. Nothing downstream of a parser ever touches
raw artifact text again. Note: this package must never import
``veritriage.graph`` at runtime (the graph imports these models).
"""

from veritriage.models.events import Severity, SimulationEvent
from veritriage.models.evidence import Evidence
from veritriage.models.failure import AssertionFailure, Failure, FailureCategory
from veritriage.models.report import (
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
