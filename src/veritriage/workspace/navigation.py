"""Report navigation: every section of an investigation, individually
addressable.

Each getter answers "give me exactly one hypothesis / pattern / observation /
commit / timeline event" from a session, without regenerating anything: the
report is already typed models, so navigation is pure lookup. Unknown IDs
return None rather than raising, so clients (a tree view doing lazy
expansion, an MCP host probing) can query cheaply.

This is the exact surface a VS Code extension needs; it contains no rendering
and no analysis, only addressing.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from veritriage.graph.model import EvidenceEdge, EvidenceNode
from veritriage.models import (
    EngineeringRecommendation,
    Hypothesis,
    MatchedPattern,
    SimilarFailure,
    TimelineEventView,
    WaveformObservationView,
)
from veritriage.models.engineering import CommitView
from veritriage.workspace.session import InvestigationSession


class EvidenceDetail(BaseModel):
    """One evidence node with every edge that touches it."""

    node: EvidenceNode
    edges_out: list[EvidenceEdge] = Field(default_factory=list)
    edges_in: list[EvidenceEdge] = Field(default_factory=list)


def hypothesis(session: InvestigationSession, hypothesis_id: str) -> Hypothesis | None:
    """One ranked hypothesis by ID, with its full confidence trace."""
    if session.report.reasoning is None:
        return None
    for candidate in session.report.reasoning.hypotheses:
        if candidate.id == hypothesis_id:
            return candidate
    return None


def recommendation(
    session: InvestigationSession, index: int
) -> EngineeringRecommendation | None:
    """One next-step recommendation by zero-based index."""
    if session.report.reasoning is None:
        return None
    steps = session.report.reasoning.recommendations
    return steps[index] if 0 <= index < len(steps) else None


def knowledge_pattern(
    session: InvestigationSession, pattern_id: str
) -> MatchedPattern | None:
    """One matched verification pattern by ID, playbook included."""
    if session.report.knowledge is None:
        return None
    for pattern in session.report.knowledge.patterns:
        if pattern.pattern_id == pattern_id:
            return pattern
    return None


def waveform_observation(
    session: InvestigationSession, observation_id: str
) -> WaveformObservationView | None:
    """One waveform observation by its deterministic observation ID."""
    if session.report.waveform is None:
        return None
    for observation in session.report.waveform.observations:
        if observation.observation_id == observation_id:
            return observation
    return None


def engineering_commit(
    session: InvestigationSession, revision: str
) -> CommitView | None:
    """One engineering change by revision, with its correlated failures."""
    if session.report.engineering is None:
        return None
    for commit in session.report.engineering.commits:
        if commit.revision == revision or commit.revision.startswith(revision):
            return commit
    return None


def timeline_event(
    session: InvestigationSession, index: int
) -> TimelineEventView | None:
    """One engineering-timeline event by zero-based index."""
    if session.report.engineering is None:
        return None
    events = session.report.engineering.timeline
    return events[index] if 0 <= index < len(events) else None


def similar_regression(
    session: InvestigationSession, regression_id: str
) -> SimilarFailure | None:
    """One historical match by regression ID."""
    if session.report.history is None:
        return None
    for match in session.report.history.similar:
        if match.regression_id == regression_id:
            return match
    return None


def evidence_node(
    session: InvestigationSession, node_id: str
) -> EvidenceDetail | None:
    """One evidence node with its incident edges, for graph walking."""
    node = session.graph.nodes.get(node_id)
    if node is None:
        return None
    return EvidenceDetail(
        node=node,
        edges_out=session.graph.edges_from(node_id),
        edges_in=session.graph.edges_to(node_id),
    )
