"""The normalized Verification Knowledge schema.

Everything the platform knows about verification lives in these models:
concepts, protocol signals, state machines, failure patterns, debug
playbooks, and references. Every item is versioned (via its pack), carries
metadata, and serializes to JSON. None of it depends on any AI: knowledge is
structured data consumed through interfaces, never prompt text.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

#: Who typically owns a failure class. Values align with hypothesis
#: categories so pattern confidence modifiers map directly onto ranking.
Ownership = Literal["design", "testbench", "infrastructure", "build"]


class Reference(BaseModel):
    """A pointer into a specification, guideline, or engineering note.

    External documentation systems (company wikis, spec databases) plug in
    later by minting References with their own ``source``/``uri``.
    """

    source: str = Field(description="Document or standard, e.g. 'AMBA AXI Specification'.")
    section: str | None = Field(default=None, description="Section or rule, e.g. 'A3.2.1'.")
    note: str | None = Field(default=None, description="Why this reference matters here.")
    uri: str | None = Field(default=None, description="Optional link into external documentation.")


class Concept(BaseModel):
    """One verification concept a pack teaches (a protocol, mechanism, or idea)."""

    id: str
    name: str
    summary: str = Field(description="One-paragraph engineer-level explanation.")
    markers: list[str] = Field(
        default_factory=list,
        description="Case-insensitive regex fragments whose presence in evidence "
        "indicates this concept is in play.",
    )
    references: list[Reference] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProtocolSignal(BaseModel):
    """A named interface signal and its role in the protocol."""

    name: str
    role: str = Field(description="What the signal does, e.g. 'read address valid'.")
    channel: str | None = Field(default=None, description="Channel/group, e.g. 'AR'.")
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProtocolState(BaseModel):
    """One stage in a protocol/transaction state machine."""

    name: str
    description: str | None = None
    markers: list[str] = Field(
        default_factory=list,
        description="Regex fragments in evidence that show this stage was reached.",
    )


class StateMachine(BaseModel):
    """An ordered expected sequence; evidence is projected onto it.

    States are listed in protocol order; the projection walks them in order
    and reports the first expected stage the evidence never reached.
    """

    id: str
    name: str
    states: list[ProtocolState] = Field(min_length=2)
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceClause(BaseModel):
    """One matchable requirement of a failure pattern.

    Clauses are the deterministic vocabulary patterns are written in: a
    regex over normalized evidence descriptions, optionally narrowed by
    artifact type or failure status. No clause ever reads a raw file; it
    matches Evidence Graph nodes only.
    """

    name: str = Field(description="Short label, e.g. 'timeout observed'.")
    pattern: str = Field(description="Case-insensitive regex matched against node descriptions.")
    artifact_types: list[str] | None = Field(
        default=None, description="Restrict to these artifact-type values; None = any."
    )
    must_fail: bool = Field(
        default=False, description="Only error/fatal evidence may satisfy this clause."
    )


class PlaybookStep(BaseModel):
    """One deterministic debugging action."""

    action: str
    detail: str | None = None
    signals: list[str] = Field(
        default_factory=list, description="Signals worth inspecting during this step."
    )


class DebugPlaybook(BaseModel):
    """A fixed, ordered debug sequence for a failure class. No AI involved."""

    id: str
    name: str
    steps: list[PlaybookStep] = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FailurePattern(BaseModel):
    """A known verification failure mode, matchable against evidence.

    A pattern matches when every ``required`` clause is satisfied and no
    ``forbidden`` clause is; ``optional_`` clauses sharpen the match score.
    Patterns are protocol-reusable: they speak in clauses, not in any one
    pack's signal names.
    """

    id: str
    name: str
    summary: str = Field(description="What this failure mode is, in engineering terms.")
    required: list[EvidenceClause] = Field(min_length=1)
    optional_: list[EvidenceClause] = Field(default_factory=list, alias="optional")
    forbidden: list[EvidenceClause] = Field(
        default_factory=list,
        description="Clauses that must NOT match (e.g. 'no assertion fired').",
    )
    typical_causes: list[str] = Field(default_factory=list)
    ownership: Ownership
    suggested_signals: list[str] = Field(default_factory=list)
    playbook_id: str | None = None
    confidence_modifiers: dict[str, float] = Field(
        default_factory=dict,
        description="Hypothesis-category value -> ranking weight this match contributes.",
    )
    references: list[Reference] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class KnowledgePack(BaseModel):
    """A versioned bundle teaching VeriTriage one verification domain."""

    id: str
    name: str
    version: str
    domain: str = Field(description="e.g. 'protocol', 'methodology', 'clocking'.")
    summary: str
    concepts: list[Concept] = Field(default_factory=list)
    signals: list[ProtocolSignal] = Field(default_factory=list)
    state_machines: list[StateMachine] = Field(default_factory=list)
    patterns: list[FailurePattern] = Field(default_factory=list)
    playbooks: list[DebugPlaybook] = Field(default_factory=list)
    references: list[Reference] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
