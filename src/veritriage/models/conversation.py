"""Conversation vocabulary (Milestone 16).

The structured question-and-answer objects the Conversation Engine exchanges.
Like every model in this package these are plain data importing nothing from
the graph or engine layers.

The canonical question is a structured object, never a sentence. A language
model may later translate prose into one of these and render one of these back
into prose, but it never owns either: answers are assembled from artifacts that
already exist, and every statement carries references that resolve.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Intent(str, Enum):
    """The finite set of things that can be asked."""

    EXPLAIN = "explain"
    WHY = "why"
    WHY_NOT = "why_not"
    SHOW_EVIDENCE = "show_evidence"
    FILTER = "filter"
    COMPARE = "compare"
    TRACE = "trace"
    NAVIGATE = "navigate"
    SUMMARIZE = "summarize"
    HELP = "help"

    @property
    def display_name(self) -> str:
        return self.value.replace("_", " ").title()


class ReferenceKind(str, Enum):
    """What layer a reference points into.

    A client can follow any reference without knowing which subsystem produced
    it, which is what makes cross-layer navigation possible.
    """

    EVIDENCE = "evidence"
    HYPOTHESIS = "hypothesis"
    KNOWLEDGE = "knowledge"
    DESIGN = "design"
    AGENT = "agent"
    LEARNING = "learning"
    PLAN = "plan"
    HISTORY = "history"
    SIGNAL = "signal"
    RECOMMENDATION = "recommendation"


class Reference(BaseModel):
    """A typed pointer at an artifact that already exists."""

    kind: ReferenceKind
    ref_id: str = Field(description="The artifact's real ID in its own layer.")
    label: str = Field(description="Human-readable name, taken from the artifact.")
    detail: str | None = Field(
        default=None, description="One line of context, quoted from the artifact."
    )


class Question(BaseModel):
    """The canonical form of something a user wants to know."""

    intent: Intent
    target: str | None = Field(
        default=None, description="What the question is about: an ID, name, or scope."
    )
    filter: str | None = Field(
        default=None, description="Narrowing term, e.g. an artifact type or severity."
    )
    text: str | None = Field(
        default=None, description="The original phrasing, when one was parsed."
    )


class AnswerSection(BaseModel):
    """One part of an answer: statements, and what backs them."""

    heading: str
    statements: list[str] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)


class Answer(BaseModel):
    """A structured response assembled from existing artifacts.

    ``followups`` is what makes navigation possible without parsing prose: each
    answer names the questions it has made available.
    """

    intent: Intent
    question: str = Field(description="The question, as asked or as reconstructed.")
    summary: str = Field(description="The one-line answer.")
    sections: list[AnswerSection] = Field(default_factory=list)
    references: list[Reference] = Field(
        default_factory=list, description="Union of every reference cited."
    )
    followups: list[Question] = Field(
        default_factory=list, description="What can usefully be asked next."
    )
    limitations: list[str] = Field(
        default_factory=list,
        description="What this answer could not establish, and why. Honest gaps, "
        "never silence.",
    )
    resolved: bool = Field(
        default=True, description="False when the question could not be answered."
    )


class NavigationContext(BaseModel):
    """Where the user currently is. Never where the analysis is.

    Carries only navigation state: changing it changes what is shown, never
    what the platform concluded.
    """

    hypothesis_id: str | None = None
    module: str | None = None
    protocol: str | None = None
    agent_id: str | None = None
    plan_step_id: str | None = None
    design_node_id: str | None = None
    evidence_filter: str | None = Field(
        default=None, description="Active artifact-type or severity filter."
    )

    @property
    def is_empty(self) -> bool:
        return not any(self.model_dump().values())

    def describe(self) -> str:
        """A printable statement of where the user is."""
        parts = [
            f"{key.replace('_', ' ')}={value}"
            for key, value in sorted(self.model_dump().items())
            if value
        ]
        return ", ".join(parts) if parts else "nothing selected"


class ConversationTurn(BaseModel):
    """One question and the answer it produced."""

    index: int = Field(ge=0)
    question: Question
    answer: Answer
    context_after: NavigationContext = Field(default_factory=NavigationContext)


class ConversationSession(BaseModel):
    """An ordered exchange plus the navigation state it accumulated.

    Serializable so a client (an IDE, a Slack thread, a CLI loop) can persist
    it however it likes. The platform stores nothing: navigation state is not
    intelligence, and it does not belong in a database.
    """

    session_id: str = Field(description="The investigation this conversation is about.")
    turns: list[ConversationTurn] = Field(default_factory=list)
    context: NavigationContext = Field(default_factory=NavigationContext)

    @property
    def turn_count(self) -> int:
        return len(self.turns)

    def last_answer(self) -> Answer | None:
        return self.turns[-1].answer if self.turns else None
