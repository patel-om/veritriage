"""Data models for the reasoning engine.

These models are the vocabulary of the reasoning pipeline: what evidence was
selected, which deterministic signals fired, which hypotheses compete, how
confident we are in each (and why, step by step), and what the engineer
should do next. This module imports nothing outside pydantic so every layer
can depend on it without cycles.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class HypothesisCategory(str, Enum):
    """The competing explanation classes the reasoning engine considers."""

    RTL_BUG = "rtl_bug"
    TESTBENCH_ISSUE = "testbench_issue"
    INFRASTRUCTURE_ISSUE = "infrastructure_issue"
    BUILD_ISSUE = "build_issue"

    @property
    def display_name(self) -> str:
        return self.value.replace("_", " ").title().replace("Rtl", "RTL")


class SelectedEvidence(BaseModel):
    """One node admitted to the working set, with the reason it was selected."""

    node_id: str
    reason: str = Field(description="Why the selector included this node.")


class WorkingSet(BaseModel):
    """The focused evidence subset a reasoning run operates on.

    The selector reduces a potentially huge graph to this set; every later
    stage (signals, hypotheses, AI) sees only these nodes.
    """

    items: list[SelectedEvidence] = Field(default_factory=list)

    @property
    def node_ids(self) -> list[str]:
        return [item.node_id for item in self.items]

    def __len__(self) -> int:  # pragma: no cover - trivial
        return len(self.items)


class ReasoningSignal(BaseModel):
    """Output of one deterministic reasoning rule.

    Signals never conclude anything; they only shift the ranking of
    hypotheses via per-category weights, and they always cite evidence.
    """

    name: str
    description: str = Field(description="What the rule observed, in engineering terms.")
    evidence_ids: list[str] = Field(default_factory=list)
    weights: dict[HypothesisCategory, float] = Field(
        default_factory=dict,
        description="Confidence deltas this signal contributes per hypothesis category.",
    )
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Rule confidence multiplier.")


class ConfidenceContribution(BaseModel):
    """One traceable step in a hypothesis's confidence computation."""

    source: str = Field(description="Signal or factor name that adjusted confidence.")
    delta: float = Field(description="Additive contribution (may be negative).")
    reason: str


class ConfidenceTrace(BaseModel):
    """Full provenance of a confidence value: base -> signals -> evidence factor.

    final = clamp01(base + sum(contribution deltas)) * evidence_factor
    """

    base: float = Field(ge=0.0, le=1.0)
    contributions: list[ConfidenceContribution] = Field(default_factory=list)
    evidence_factor: float = Field(
        ge=0.0, le=1.0, description="Mean extraction confidence of the cited evidence nodes."
    )
    final: float = Field(ge=0.0, le=1.0)


class Hypothesis(BaseModel):
    """One competing, evidence-backed explanation for the failure."""

    id: str = Field(description="Stable ID, e.g. 'hyp-rtl_bug'.")
    category: HypothesisCategory
    title: str
    statement: str = Field(description="The explanation, written like a DV engineer would.")
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(description="Graph nodes supporting this hypothesis; never empty.")
    confidence_trace: ConfidenceTrace
    generated_by: str = Field(description="Name of the generator that produced this hypothesis.")
    ai_note: str | None = Field(
        default=None, description="Optional AI refinement; cites node IDs, never new facts."
    )


class EngineeringRecommendation(BaseModel):
    """A concrete next debugging step, categorized for planning."""

    action: str
    rationale: str
    priority: int = Field(ge=1, description="1 = do first.")
    effort: Literal["low", "medium", "high"] = Field(description="Expected debugging effort.")
    confidence: float = Field(ge=0.0, le=1.0, description="Propagated from the driving hypothesis.")
    module: str | None = Field(default=None, description="Affected design/testbench scope, if known.")
    evidence_ids: list[str] = Field(default_factory=list)


class AIReview(BaseModel):
    """Structured output of the optional AI reasoning stage."""

    narrative: str = Field(description="Engineer-style walkthrough of the failure; cites node IDs.")
    missing_evidence: list[str] = Field(
        default_factory=list,
        description="Artifacts or observations that would discriminate between hypotheses.",
    )
    hypothesis_notes: dict[str, str] = Field(
        default_factory=dict, description="Per-hypothesis refinement, keyed by hypothesis ID."
    )


class ReasoningResult(BaseModel):
    """Everything one reasoning run produced, embedded in the AnalysisReport."""

    working_set: WorkingSet
    signals: list[ReasoningSignal] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(
        default_factory=list, description="Ranked, highest confidence first."
    )
    recommendations: list[EngineeringRecommendation] = Field(default_factory=list)
    ai_review: AIReview | None = None
