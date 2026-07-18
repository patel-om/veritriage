"""Strongly-typed data models shared by every VeriTriage layer.

Parsers produce these models; the rule and reasoning engines consume and
enrich them; report generators render them. Nothing downstream of a parser
ever touches raw artifact text again. Note: this package must never import
``veritriage.graph`` at runtime (the graph imports these models).
"""

from veritriage.models.events import Severity, SimulationEvent
from veritriage.models.evidence import Evidence
from veritriage.models.failure import AssertionFailure, Failure, FailureCategory
from veritriage.models.reasoning import (
    AIReview,
    ConfidenceContribution,
    ConfidenceTrace,
    EngineeringRecommendation,
    Hypothesis,
    HypothesisCategory,
    ReasoningResult,
    ReasoningSignal,
    SelectedEvidence,
    WorkingSet,
)
from veritriage.models.report import (
    AnalysisReport,
    ClassificationResult,
    GraphStats,
    LogSummary,
    Recommendation,
)

__all__ = [
    "AIReview",
    "AnalysisReport",
    "AssertionFailure",
    "ClassificationResult",
    "ConfidenceContribution",
    "ConfidenceTrace",
    "EngineeringRecommendation",
    "Evidence",
    "Failure",
    "FailureCategory",
    "GraphStats",
    "Hypothesis",
    "HypothesisCategory",
    "LogSummary",
    "Recommendation",
    "ReasoningResult",
    "ReasoningSignal",
    "SelectedEvidence",
    "Severity",
    "SimulationEvent",
    "WorkingSet",
]
