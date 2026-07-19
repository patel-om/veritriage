"""Knowledge inference: how structured knowledge reaches reasoning and reports.

Two integration surfaces, both additive:

1. **Reasoning signals.** ``knowledge_reasoning_rules()`` wraps every failure
   pattern in a standard :class:`ReasoningRule`, so matched knowledge
   contributes ranking weight through the exact same interface as the
   built-in rules. The reasoning engine does not know knowledge exists; it
   just receives more rules. Knowledge is evidence, not hidden prompt text.

2. **Report context.** ``KnowledgeEngine.analyze()`` produces the
   :class:`KnowledgeContext` embedded in the report: matched patterns with
   causes/ownership/signals/references, matched concepts, the state-machine
   projection, and the suggested playbooks.

Nothing here touches an LLM: the module imports no AI code, performs no I/O,
and is fully deterministic.
"""

from __future__ import annotations

from veritriage.graph.graph import EvidenceGraph
from veritriage.knowledge.graph import KnowledgeGraph
from veritriage.knowledge.matcher import (
    PatternMatch,
    best_projection,
    match_concepts,
    match_patterns,
)
from veritriage.models import (
    HypothesisCategory,
    KnowledgeContext,
    KnowledgeReference,
    MatchedConcept,
    MatchedPattern,
    PlaybookStepView,
    PlaybookView,
    ReasoningSignal,
    WorkingSet,
)
from veritriage.reasoning.signals import ReasoningRule

#: Ownership -> the hypothesis category it corroborates (for display only;
#: ranking weights come from each pattern's explicit confidence_modifiers).
_OWNERSHIP_LABEL = {
    "design": "design (RTL)",
    "testbench": "testbench / verification environment",
    "infrastructure": "infrastructure / compute environment",
    "build": "build / compile flow",
}


class KnowledgePatternRule(ReasoningRule):
    """Adapter: one failure pattern exposed as a standard reasoning rule.

    When the pattern matches the working set's evidence, it emits one signal
    whose weights are the pattern's confidence modifiers and whose evidence
    IDs are the nodes that satisfied the clauses. Signals never conclude;
    like every other rule, knowledge only shifts hypothesis ranking.
    """

    def __init__(self, knowledge: KnowledgeGraph, pattern_id: str) -> None:
        self._knowledge = knowledge
        self._pattern_id = pattern_id
        self.name = f"knowledge:{pattern_id}"

    def evaluate(self, graph: EvidenceGraph, working_set: WorkingSet) -> ReasoningSignal | None:
        match = next(
            (
                m
                for m in match_patterns(self._knowledge, graph)
                if m.pattern.id == self._pattern_id
            ),
            None,
        )
        if match is None or not match.pattern.confidence_modifiers:
            return None
        weights = {
            HypothesisCategory(category): weight
            for category, weight in match.pattern.confidence_modifiers.items()
        }
        evidence_ids = sorted({i for ids in match.matched_evidence.values() for i in ids})
        return ReasoningSignal(
            name=self.name,
            description=(
                f"Known verification pattern '{match.pattern.name}' "
                f"({match.pack.name} pack): {match.pattern.summary}"
            ),
            evidence_ids=evidence_ids,
            weights=weights,
            confidence=match.score,
        )


def knowledge_reasoning_rules(knowledge: KnowledgeGraph | None = None) -> list[ReasoningRule]:
    """One reasoning rule per known failure pattern, in deterministic order."""
    knowledge = knowledge or KnowledgeGraph.build()
    return [
        KnowledgePatternRule(knowledge, pattern.id)
        for _, pattern in sorted(knowledge.patterns(), key=lambda pair: pair[1].id)
    ]


class KnowledgeEngine:
    """Builds the report-facing knowledge context for one Evidence Graph."""

    def __init__(self, knowledge: KnowledgeGraph | None = None) -> None:
        self.knowledge = knowledge or KnowledgeGraph.build()

    def analyze(self, graph: EvidenceGraph) -> KnowledgeContext:
        matches = match_patterns(self.knowledge, graph)
        concepts = match_concepts(self.knowledge, graph)
        projection = best_projection(self.knowledge, graph)
        return KnowledgeContext(
            pack_versions=self.knowledge.pack_versions(),
            concepts=[
                MatchedConcept(
                    concept_id=c.concept.id,
                    name=c.concept.name,
                    pack=c.pack.id,
                    summary=c.concept.summary,
                    evidence_ids=c.evidence_ids[:6],
                )
                for c in concepts
            ],
            patterns=[self._pattern_view(m) for m in matches],
            state_projection=projection,
        )

    def _pattern_view(self, match: PatternMatch) -> MatchedPattern:
        playbook = None
        resolved = self.knowledge.playbook_for(match.pattern.id)
        if resolved is not None:
            pack, pb = resolved
            playbook = PlaybookView(
                playbook_id=pb.id,
                name=pb.name,
                pack=pack.id,
                steps=[
                    PlaybookStepView(
                        order=i, action=step.action, detail=step.detail, signals=step.signals
                    )
                    for i, step in enumerate(pb.steps, start=1)
                ],
            )
        return MatchedPattern(
            pattern_id=match.pattern.id,
            name=match.pattern.name,
            pack=match.pack.id,
            pack_version=match.pack.version,
            score=match.score,
            summary=match.pattern.summary,
            matched_evidence=match.matched_evidence,
            typical_causes=match.pattern.typical_causes,
            ownership=_OWNERSHIP_LABEL.get(match.pattern.ownership, match.pattern.ownership),
            suggested_signals=match.pattern.suggested_signals,
            references=[
                KnowledgeReference(source=r.source, section=r.section, note=r.note)
                for r in match.pattern.references
            ],
            playbook=playbook,
        )
