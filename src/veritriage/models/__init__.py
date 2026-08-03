"""Strongly-typed data models shared by every VeriTriage layer.

Parsers produce these models; the rule and reasoning engines consume and
enrich them; report generators render them. Nothing downstream of a parser
ever touches raw artifact text again. Note: this package must never import
``veritriage.graph`` at runtime (the graph imports these models).
"""

from veritriage.models.agents import (
    AgentAssessment,
    AgentConflict,
    AgentContribution,
    AgentDomain,
    AgentFinding,
    AgentHypothesis,
    AgentObservation,
    AgentRecommendation,
    AgentResult,
    ConsensusState,
)
from veritriage.models.engineering import (
    EngineeringContextView,
    ImpactedTestView,
    InvestigationView,
    TimelineEventView,
)
from veritriage.models.orchestration import (
    InvestigationPlan,
    InvestigationTrace,
    PlanStep,
    StepStatus,
    StepTrace,
    SubsystemAttribution,
)
from veritriage.models.events import Severity, SimulationEvent
from veritriage.models.evidence import Evidence
from veritriage.models.failure import AssertionFailure, Failure, FailureCategory
from veritriage.models.history import HistoricalContext, SimilarFailure
from veritriage.models.knowledge import (
    KnowledgeContext,
    KnowledgeReference,
    MatchedConcept,
    MatchedPattern,
    PlaybookStepView,
    PlaybookView,
    StateProgress,
    StateProjection,
)
from veritriage.models.project import (
    DutModuleView,
    DutTopologyView,
    IdentifiedProtocol,
    InterfaceView,
    LifecycleProjection,
    LogAnnotationView,
    ProjectContext,
    ProjectSummary,
    ResolvedScope,
    UvmComponentView,
    UvmTopologyView,
)
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
from veritriage.models.waveform import (
    WaveformCapabilityView,
    WaveformContext,
    WaveformObservationView,
    WaveformUnavailableView,
)

__all__ = [
    "AIReview",
    "AgentAssessment",
    "AgentConflict",
    "AgentContribution",
    "AgentDomain",
    "AgentFinding",
    "AgentHypothesis",
    "AgentObservation",
    "AgentRecommendation",
    "AgentResult",
    "AnalysisReport",
    "AssertionFailure",
    "ClassificationResult",
    "ConfidenceContribution",
    "ConfidenceTrace",
    "ConsensusState",
    "DutModuleView",
    "DutTopologyView",
    "EngineeringContextView",
    "EngineeringRecommendation",
    "Evidence",
    "Failure",
    "FailureCategory",
    "GraphStats",
    "HistoricalContext",
    "Hypothesis",
    "HypothesisCategory",
    "IdentifiedProtocol",
    "ImpactedTestView",
    "InterfaceView",
    "InvestigationPlan",
    "InvestigationTrace",
    "InvestigationView",
    "KnowledgeContext",
    "KnowledgeReference",
    "LifecycleProjection",
    "LogAnnotationView",
    "LogSummary",
    "MatchedConcept",
    "MatchedPattern",
    "PlanStep",
    "PlaybookStepView",
    "PlaybookView",
    "ProjectContext",
    "ProjectSummary",
    "Recommendation",
    "ResolvedScope",
    "ReasoningResult",
    "ReasoningSignal",
    "SelectedEvidence",
    "Severity",
    "SimilarFailure",
    "SimulationEvent",
    "StateProgress",
    "StateProjection",
    "StepStatus",
    "StepTrace",
    "SubsystemAttribution",
    "TimelineEventView",
    "UvmComponentView",
    "UvmTopologyView",
    "WaveformCapabilityView",
    "WaveformContext",
    "WaveformObservationView",
    "WaveformUnavailableView",
    "WorkingSet",
]
