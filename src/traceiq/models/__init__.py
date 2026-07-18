"""Strongly-typed data models shared by every TraceIQ layer.

Parsers produce these models; the rule engine consumes and enriches them;
report generators render them. Nothing downstream of a parser ever touches
raw log text again — the models are the single source of truth.
"""

from traceiq.models.events import Severity, SimulationEvent
from traceiq.models.evidence import Evidence
from traceiq.models.failure import AssertionFailure, Failure, FailureCategory
from traceiq.models.report import (
    AnalysisReport,
    ClassificationResult,
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
    "LogSummary",
    "Recommendation",
    "Severity",
    "SimulationEvent",
]
