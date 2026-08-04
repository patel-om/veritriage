"""ConversationContext: the finished investigation a handler may read.

Everything a handler is allowed to see, and nothing else: one completed report,
the Evidence Graph it came from, and optionally the Design Graph. No path, no
store, no service. Conversation is a pure function of a finished investigation.

This module also holds the reference builders. Every reference a handler emits
goes through one of them, so a reference can only ever be minted from an
artifact that was actually found: citing something that does not exist requires
going around this file, which the guard tests notice.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from veritriage.graph.graph import EvidenceGraph
from veritriage.models import (
    AgentResult,
    AnalysisReport,
    Hypothesis,
    Reference,
    ReferenceKind,
)


class ConversationContext(BaseModel):
    """One finished investigation, frozen, as a handler sees it."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    session_id: str = ""
    report: AnalysisReport
    graph: EvidenceGraph
    #: The Design Graph, when the caller has one. Structural navigation
    #: degrades to the report's design view without it, and says so.
    design: object | None = None

    # --- Resolution ---------------------------------------------------------

    def hypothesis(self, hypothesis_id: str | None) -> Hypothesis | None:
        """One hypothesis by ID, or the leading one when no ID is given."""
        if self.report.reasoning is None or not self.report.reasoning.hypotheses:
            return None
        if hypothesis_id is None:
            return self.report.reasoning.hypotheses[0]
        lowered = hypothesis_id.lower()
        for candidate in self.report.reasoning.hypotheses:
            if candidate.id.lower() == lowered or candidate.category.value == lowered:
                return candidate
        return None

    def agent(self, agent_id: str) -> AgentResult | None:
        if self.report.agents is None:
            return None
        lowered = agent_id.lower()
        return next(
            (r for r in self.report.agents.results if r.agent_id.lower() == lowered), None
        )

    def plan_step(self, step_id: str):
        if self.report.plan is None:
            return None
        return next((s for s in self.report.plan.all_steps() if s.step_id == step_id), None)

    def has_node(self, node_id: str) -> bool:
        return node_id in self.graph.nodes

    # --- Reference builders -------------------------------------------------
    #
    # The only sanctioned way to mint a reference. Each returns None when the
    # artifact does not exist, so an unresolvable citation cannot be emitted.

    def evidence_ref(self, node_id: str) -> Reference | None:
        node = self.graph.nodes.get(node_id)
        if node is None:
            return None
        where = f"{node.source_path}:{node.line_number}" if node.line_number else node.source_path
        return Reference(
            kind=ReferenceKind.EVIDENCE,
            ref_id=node.id,
            label=node.description[:100],
            detail=f"{node.artifact_type.value} at {where}",
        )

    def evidence_refs(self, node_ids: list[str], limit: int = 8) -> list[Reference]:
        found: list[Reference] = []
        for node_id in node_ids:
            reference = self.evidence_ref(node_id)
            if reference is not None:
                found.append(reference)
            if len(found) >= limit:
                break
        return found

    def hypothesis_ref(self, hypothesis: Hypothesis) -> Reference:
        return Reference(
            kind=ReferenceKind.HYPOTHESIS,
            ref_id=hypothesis.id,
            label=hypothesis.title,
            detail=f"confidence {hypothesis.confidence:.0%}, from {hypothesis.generated_by}",
        )

    def agent_ref(self, result: AgentResult) -> Reference:
        position = (
            result.hypotheses[0].category.display_name
            if result.hypotheses
            else ("abstained" if result.abstained else "not applicable")
        )
        return Reference(
            kind=ReferenceKind.AGENT,
            ref_id=result.agent_id,
            label=f"{result.agent_id} specialist",
            detail=f"{position} at confidence {result.confidence:.0%}",
        )

    def knowledge_ref(self, pattern) -> Reference:
        return Reference(
            kind=ReferenceKind.KNOWLEDGE,
            ref_id=pattern.pattern_id,
            label=pattern.name,
            detail=f"{pattern.pack} pack, {pattern.score:.0%} match",
        )

    def design_ref(self, node) -> Reference:
        return Reference(
            kind=ReferenceKind.DESIGN,
            ref_id=node.node_id if hasattr(node, "node_id") else node.id,
            label=node.name,
            detail=node.kind if isinstance(node.kind, str) else node.kind.value,
        )

    def plan_ref(self, step) -> Reference:
        return Reference(
            kind=ReferenceKind.PLAN,
            ref_id=step.step_id,
            label=step.action,
            detail=f"{step.kind.value}, value/effort {step.valuation.priority_score:.2f}",
        )

    def learning_ref(self, hint) -> Reference:
        return Reference(
            kind=ReferenceKind.LEARNING,
            ref_id=hint.artifact_id,
            label=hint.statement[:100],
            detail=f"learned from {len(hint.supporting_regressions)} prior investigation(s)",
        )

    def history_ref(self, similar) -> Reference:
        return Reference(
            kind=ReferenceKind.HISTORY,
            ref_id=similar.regression_id,
            label=similar.root_cause[:100],
            detail=f"{similar.score:.0%} similar, classified {similar.classification}",
        )

    def signal_ref(self, signal) -> Reference:
        return Reference(
            kind=ReferenceKind.SIGNAL,
            ref_id=signal.name,
            label=signal.name,
            detail=signal.description[:140],
        )
