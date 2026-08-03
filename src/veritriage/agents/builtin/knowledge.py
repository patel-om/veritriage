"""Knowledge Agent: what does the accumulated verification knowledge say?

The other specialists each read one slice of the Knowledge Graph. This agent
reads all of it at once and answers the consolidation question: across every
pack that matched, weighted by match strength, who owns this failure class and
which playbook should be worked first?
"""

from __future__ import annotations

from veritriage.agents.base import Agent
from veritriage.agents.context import OWNERSHIP_CATEGORY, AgentContext
from veritriage.agents.registry import register_agent
from veritriage.models import (
    AgentDomain,
    AgentHypothesis,
    AgentObservation,
    AgentRecommendation,
    AgentResult,
    HypothesisCategory,
)


@register_agent
class KnowledgeAgent(Agent):
    """The consolidated verification-knowledge specialist."""

    agent_id = "knowledge"
    domain = AgentDomain.KNOWLEDGE

    def applies_to(self, context: AgentContext) -> bool:
        return bool(context.matched_patterns())

    def assess(self, context: AgentContext) -> AgentResult:
        patterns = context.matched_patterns()
        observations: list[AgentObservation] = []
        hypotheses: list[AgentHypothesis] = []
        recommendations: list[AgentRecommendation] = []
        limitations: list[str] = []

        packs = sorted({m.pack for m in patterns})
        observations.append(
            AgentObservation(
                statement=(
                    f"{len(patterns)} known failure pattern(s) matched across "
                    f"{len(packs)} pack(s): {', '.join(packs[:5])}."
                ),
                evidence_ids=sorted({i for m in patterns for i in context.pattern_evidence(m)}),
                knowledge_ids=[m.pattern_id for m in patterns],
            )
        )

        # Weighted ownership vote: each pattern votes for its owning category
        # with its match score, so a strong match outweighs several weak ones.
        votes: dict[HypothesisCategory, float] = {}
        evidence_by_category: dict[HypothesisCategory, set[str]] = {}
        knowledge_by_category: dict[HypothesisCategory, set[str]] = {}
        for matched in patterns:
            ownership = context.pattern_ownership(matched.pattern_id)
            category_value = OWNERSHIP_CATEGORY.get(ownership or "")
            if category_value is None:
                continue
            category = HypothesisCategory(category_value)
            votes[category] = votes.get(category, 0.0) + matched.score
            evidence_by_category.setdefault(category, set()).update(
                context.pattern_evidence(matched)
            )
            knowledge_by_category.setdefault(category, set()).add(matched.pattern_id)

        if votes:
            total = sum(votes.values())
            leader = max(sorted(votes), key=lambda c: votes[c])
            share = votes[leader] / total if total else 0.0
            evidence = sorted(evidence_by_category.get(leader, set()))
            if evidence:
                hypotheses.append(
                    AgentHypothesis(
                        category=leader,
                        statement=(
                            f"Weighted across every matched pattern, the accumulated "
                            f"verification knowledge attributes this failure class to "
                            f"{leader.display_name.lower()} "
                            f"({share:.0%} of the matched-pattern weight)."
                        ),
                        confidence=round(min(0.75, 0.35 + 0.40 * share), 4),
                        evidence_ids=evidence,
                        knowledge_ids=sorted(knowledge_by_category.get(leader, set())),
                    )
                )
        else:
            limitations.append(
                "No matched pattern declared an ownership class, so knowledge contributes "
                "playbooks here rather than an attribution."
            )

        playbooked = [m for m in patterns if m.playbook is not None]
        if playbooked:
            best = max(playbooked, key=lambda m: (m.score, m.pattern_id))
            assert best.playbook is not None
            observations.append(
                AgentObservation(
                    statement=(
                        f"The strongest match carries the '{best.playbook.name}' playbook "
                        f"({len(best.playbook.steps)} deterministic step(s))."
                    ),
                    evidence_ids=context.pattern_evidence(best),
                    knowledge_ids=[best.playbook.playbook_id],
                )
            )
            for step in best.playbook.steps[:3]:
                recommendations.append(
                    AgentRecommendation(
                        action=step.action,
                        rationale=(
                            f"Step {step.order} of '{best.playbook.name}', the playbook for "
                            f"the highest-scoring matched pattern"
                            + (
                                f"; pull up {', '.join(step.signals[:3])}"
                                if step.signals
                                else ""
                            )
                            + "."
                        ),
                        priority=step.order,
                        evidence_ids=context.pattern_evidence(best)[:3],
                    )
                )
        else:
            limitations.append(
                "No matched pattern carries a debug playbook, so no fixed debug sequence "
                "could be recommended."
            )

        references = [r for m in patterns for r in m.references]
        if references:
            cited = ", ".join(
                sorted({f"{r.source}{' ' + r.section if r.section else ''}" for r in references})[:3]
            )
            observations.append(
                AgentObservation(
                    statement=f"Matched patterns cite specification references: {cited}.",
                    evidence_ids=[],
                    knowledge_ids=[m.pattern_id for m in patterns],
                )
            )
        else:
            limitations.append(
                "No matched pattern carries a specification reference, so no authoritative "
                "document could be pointed at."
            )
        return self.build(
            context,
            observations=observations,
            hypotheses=hypotheses,
            recommendations=recommendations,
            limitations=limitations,
        )
