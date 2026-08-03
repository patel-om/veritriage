"""Agent Framework vocabulary (Milestone 12).

The layer-neutral models the Agent Coordinator produces and the report
carries. Like every model in this package these are plain data: they import
nothing from the graph or engine layers, so `models` stays below everything
that produces them (the same precedent as the waveform, engineering, project,
and orchestration views).

Agent hypotheses deliberately reuse :class:`HypothesisCategory` from the
reasoning vocabulary rather than inventing a taxonomy. That is what makes an
agent position directly comparable to a deterministic hypothesis, and it is
what the Coordinator's cross-check against the reasoning engine depends on.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from veritriage.models.reasoning import HypothesisCategory


class AgentDomain(str, Enum):
    """The verification domain one agent is responsible for."""

    PROTOCOL = "protocol"
    RTL = "rtl"
    TESTBENCH = "testbench"
    COVERAGE = "coverage"
    REGRESSION = "regression"
    FORMAL = "formal"
    PROJECT = "project"
    KNOWLEDGE = "knowledge"

    @property
    def display_name(self) -> str:
        return self.value.replace("_", " ").title().replace("Rtl", "RTL")


class ConsensusState(str, Enum):
    """How much independent support one merged finding has."""

    #: Two or more agents independently support this category.
    AGREEMENT = "agreement"
    #: Exactly one agent supports it.
    SINGLE_SOURCE = "single_source"
    #: Supported here while another agent leads a different category.
    CONTESTED = "contested"


class AgentObservation(BaseModel):
    """One thing an agent noticed, always tied to evidence.

    An observation states a fact that is already in the evidence; it never
    concludes. Conclusions are hypotheses, which is a separate field on
    purpose.
    """

    statement: str = Field(description="What the agent observed, in engineering terms.")
    evidence_ids: list[str] = Field(
        default_factory=list, description="Evidence Graph nodes supporting this observation."
    )
    knowledge_ids: list[str] = Field(
        default_factory=list, description="Knowledge items (pattern/concept/playbook IDs) consulted."
    )


class AgentHypothesis(BaseModel):
    """One agent's evidence-backed position on what explains the failure."""

    category: HypothesisCategory
    statement: str = Field(description="The position, written like a DV engineer would.")
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(
        min_length=1, description="Supporting graph nodes; an agent with none must abstain."
    )
    knowledge_ids: list[str] = Field(default_factory=list)


class AgentRecommendation(BaseModel):
    """A next debugging step an agent proposes from its own position."""

    action: str
    rationale: str
    priority: int = Field(default=1, ge=1, description="1 = do first.")
    evidence_ids: list[str] = Field(default_factory=list)


class AgentResult(BaseModel):
    """The standardized output contract every agent returns.

    Reusable by every future agent without modification: a new domain
    specialist fills the same fields, and the Coordinator merges it with no
    knowledge of what the agent does.
    """

    agent_id: str
    domain: AgentDomain
    applicable: bool = Field(description="Whether this agent had anything in scope to assess.")
    abstained: bool = Field(
        default=False,
        description="True when the agent was applicable but could not cite evidence.",
    )
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="The agent's confidence in its own leading position."
    )
    observations: list[AgentObservation] = Field(default_factory=list)
    hypotheses: list[AgentHypothesis] = Field(
        default_factory=list, description="Ranked, highest confidence first."
    )
    recommendations: list[AgentRecommendation] = Field(default_factory=list)
    evidence_ids: list[str] = Field(
        default_factory=list, description="Union of every evidence node this agent cited."
    )
    knowledge_ids: list[str] = Field(
        default_factory=list, description="Union of every knowledge item this agent consulted."
    )
    limitations: list[str] = Field(
        default_factory=list,
        description="What this agent could not determine, and why. Never silently empty "
        "when an analysis was skipped for lack of data.",
    )
    narrative: str | None = Field(
        default=None,
        description="Optional provider-supplied prose. Never load-bearing: no conclusion, "
        "confidence, or citation is derived from it.",
    )
    provider: str | None = Field(
        default=None, description="Reasoning provider that produced the narrative, if any."
    )

    @property
    def leading_category(self) -> HypothesisCategory | None:
        """The category of this agent's strongest hypothesis, if it has one."""
        return self.hypotheses[0].category if self.hypotheses else None


class AgentContribution(BaseModel):
    """One traceable term in a merged finding's confidence computation."""

    agent_id: str
    delta: float = Field(description="Additive contribution (may be negative).")
    reason: str


class AgentFinding(BaseModel):
    """One merged position, with every agent that supports it and why.

    final = clamp01(base + corroboration + contest), where base is the
    strongest single agent confidence for this category, corroboration adds
    for each additional independent supporter, and contest subtracts once
    when another agent leads elsewhere.
    """

    category: HypothesisCategory
    statement: str = Field(description="The strongest supporting agent's statement.")
    confidence: float = Field(ge=0.0, le=1.0)
    consensus: ConsensusState
    supporting_agents: list[str] = Field(default_factory=list)
    contributions: list[AgentContribution] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    knowledge_ids: list[str] = Field(default_factory=list)


class AgentConflict(BaseModel):
    """Two agents whose leading positions differ.

    Surfaced, never suppressed: a deterministic engine and a panel of domain
    specialists disagreeing is diagnostic information for the engineer.
    """

    agent_a: str
    agent_b: str
    category_a: HypothesisCategory
    category_b: HypothesisCategory
    note: str


class AgentAssessment(BaseModel):
    """Everything the Agent Coordinator produced for one analysis.

    Embedded in :class:`AnalysisReport` as the ``agents`` field. It sits
    beside the deterministic ``reasoning`` field and never replaces it:
    ``agrees_with_reasoning`` records whether the two agree, and nothing is
    reordered as a consequence of disagreement.
    """

    coordinator_version: str = Field(
        default="1", description="Merge-semantics version; bumps if the formula changes."
    )
    agents_invoked: list[str] = Field(
        default_factory=list, description="Agents that ran, in deterministic order."
    )
    agents_not_applicable: list[str] = Field(default_factory=list)
    agents_abstained: list[str] = Field(default_factory=list)
    results: list[AgentResult] = Field(default_factory=list)
    findings: list[AgentFinding] = Field(
        default_factory=list, description="Merged positions, highest confidence first."
    )
    conflicts: list[AgentConflict] = Field(default_factory=list)
    recommendations: list[AgentRecommendation] = Field(
        default_factory=list, description="Merged, deduplicated, priority-ordered."
    )
    limitations: list[str] = Field(
        default_factory=list, description="Union of every agent's declared limitations."
    )
    top_category: HypothesisCategory | None = Field(
        default=None, description="The agent layer's leading category."
    )
    reasoning_top_category: HypothesisCategory | None = Field(
        default=None, description="The deterministic engine's leading hypothesis category."
    )
    agrees_with_reasoning: bool | None = Field(
        default=None,
        description="Whether the agent layer's leading category matches the reasoning "
        "engine's. Recorded for the engineer; never acted upon.",
    )

    @property
    def is_empty(self) -> bool:
        return not (self.findings or self.results)
