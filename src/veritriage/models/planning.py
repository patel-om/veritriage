"""Planning Engine vocabulary (Milestone 14).

The artifacts the Planner derives from a finished analysis. Like every model in
this package these are plain data importing nothing from the graph or engine
layers.

Deliberately named apart from the M9 orchestration vocabulary
(``InvestigationPlan`` / ``PlanStep`` / ``InvestigationStep``), which describes
*what the platform will run*. These describe *what the engineer should do*.
Machine workflow and human debug strategy are different things and keep
different words.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from veritriage.models.reasoning import HypothesisCategory


class StepKind(str, Enum):
    """What sort of debugging action a step is."""

    #: Look at something that already exists (a waveform, a log, a diff).
    INSPECT = "inspect"
    #: Check a claim against a specification or a reference.
    VERIFY = "verify"
    #: Compare this run against another run or a golden reference.
    COMPARE = "compare"
    #: Re-run something to separate signal from noise.
    REPRODUCE = "reproduce"
    #: Obtain information the platform does not currently have.
    COLLECT = "collect"

    @property
    def display_name(self) -> str:
        return self.value.title()


class ConditionKind(str, Enum):
    """How a decision point's question gets answered."""

    #: Evaluated deterministically against evidence already in the graph.
    AUTO = "auto"
    #: Requires a human observation; rendered as an open question.
    ASK = "ask"


class StepValuation(BaseModel):
    """Why a step sits where it does in the plan.

    priority_score = value / effort

    Recorded term by term so a step's position is readable line by line,
    exactly like a ConfidenceTrace or an AgentContribution.
    """

    value: float = Field(ge=0.0, description="Expected information gain.")
    effort: int = Field(ge=1, le=3, description="1 low, 2 medium, 3 high.")
    priority_score: float = Field(ge=0.0)
    terms: list[str] = Field(
        default_factory=list, description="Plain-language arithmetic behind the value."
    )


class EvidenceRequest(BaseModel):
    """Information the platform does not have, and why it matters."""

    request_id: str
    what: str = Field(description="The artifact or observation needed.")
    why: str = Field(description="What it would settle, in engineering terms.")
    would_discriminate: list[HypothesisCategory] = Field(
        default_factory=list, description="Hypotheses this evidence would separate."
    )
    satisfied_by: list[str] = Field(
        default_factory=list,
        description="Artifact types that would satisfy it, e.g. 'waveform_metadata'.",
    )
    evidence_ids: list[str] = Field(
        default_factory=list, description="Existing nodes that motivated the request."
    )


class PlanBranch(BaseModel):
    """The steps taken when one outcome of a decision point holds."""

    outcome: str = Field(description="The observation this branch responds to.")
    rationale: str = Field(description="Why this outcome implies these steps.")
    steps: list["DebugStep"] = Field(default_factory=list)


class DecisionPoint(BaseModel):
    """A branching question, with what to do for each answer.

    ``AUTO`` conditions are settled by evidence already in the graph, so the
    Planner resolves them deterministically. ``ASK`` conditions await a human
    observation and stay open. Nothing here is ever executed.
    """

    decision_id: str
    question: str
    condition: ConditionKind = ConditionKind.ASK
    resolved_outcome: str | None = Field(
        default=None, description="Set when this run's evidence already settled it."
    )
    resolved_because: str | None = None
    branches: list[PlanBranch] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class DebugStep(BaseModel):
    """One action in the plan, always derived from an existing artifact."""

    step_id: str
    kind: StepKind
    action: str = Field(description="What to do.")
    purpose: str = Field(description="What this would tell you.")
    derived_from: str = Field(
        description="The artifact this came from, e.g. 'knowledge:playbook:pb-axi-stall#1'. "
        "The Planner contributes structure, never content."
    )
    addresses: list[HypothesisCategory] = Field(
        default_factory=list, description="Hypotheses this step bears on."
    )
    required_evidence: list[str] = Field(
        default_factory=list, description="What must be available to take this step."
    )
    expected_observations: list[str] = Field(
        default_factory=list, description="What you might see, and what each would mean."
    )
    signals: list[str] = Field(
        default_factory=list, description="Waveform/RTL signals worth pulling up."
    )
    module: str | None = None
    valuation: StepValuation
    evidence_ids: list[str] = Field(default_factory=list)
    decision: DecisionPoint | None = Field(
        default=None, description="The branch this step opens, when it has one."
    )


class CompletionCondition(BaseModel):
    """How an engineer knows the investigation is finished."""

    statement: str
    satisfied: bool = Field(
        default=False, description="Whether this run's evidence already satisfies it."
    )
    evidence_ids: list[str] = Field(default_factory=list)


class PlanProgress(BaseModel):
    """How far along an investigation is, computed from the current graph.

    A pure function of a plan plus a graph: no persistent state, nothing
    recorded between runs.
    """

    total_steps: int = 0
    satisfied_requests: list[str] = Field(default_factory=list)
    outstanding_requests: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    completion: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Fraction of evidence requests satisfied."
    )


class DebugPlan(BaseModel):
    """A structured, branching investigation plan for one analysis.

    Derived deterministically from a finished AnalysisReport: the same report
    always produces a byte-identical plan, including ``plan_id``, which is a
    content digest. Planning consumes conclusions and never changes them.
    """

    schema_version: str = "1"
    plan_id: str = Field(description="Content digest of the plan's structure.")
    objective: str = Field(description="What this investigation is trying to establish.")
    strategy: str = Field(
        description="The shape of the approach, adapted to the project and the evidence."
    )
    steps: list[DebugStep] = Field(
        default_factory=list, description="Root steps, highest priority first."
    )
    evidence_requests: list[EvidenceRequest] = Field(default_factory=list)
    completion_conditions: list[CompletionCondition] = Field(default_factory=list)
    estimated_effort: int = Field(
        default=0, ge=0, description="Sum of root-step effort; a relative unit, not minutes."
    )
    confidence_target: HypothesisCategory | None = Field(
        default=None, description="The hypothesis the plan is built to confirm or reject."
    )
    risks: list[str] = Field(
        default_factory=list, description="What could make this plan mislead."
    )
    historical_success: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
        description="How often this plan's leading approach worked before, when history knows.",
    )
    sources: list[str] = Field(
        default_factory=list, description="Step sources that contributed, in run order."
    )

    @property
    def is_empty(self) -> bool:
        return not self.steps

    def all_steps(self) -> list[DebugStep]:
        """Every step in the tree, depth first, in plan order."""
        found: list[DebugStep] = []

        def walk(steps: list[DebugStep]) -> None:
            for step in steps:
                found.append(step)
                if step.decision is not None:
                    for branch in step.decision.branches:
                        walk(branch.steps)

        walk(self.steps)
        return found


PlanBranch.model_rebuild()
DebugStep.model_rebuild()
