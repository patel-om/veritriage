"""Protocol Agent: where in the protocol did progress stop?

Aggregates every matched failure pattern from a wire-protocol pack into one
protocol position, instead of the 92 independent pattern rules the reasoning
engine already applies. This is the aggregation unit the platform lacked: AXI
speaks once, as the AXI view of this failure.
"""

from __future__ import annotations

from veritriage.agents.base import Agent
from veritriage.agents.context import (
    OWNERSHIP_CATEGORY,
    PROTOCOL_DOMAINS,
    AgentContext,
)
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
class ProtocolAgent(Agent):
    """The protocol specialist: pattern matches plus state-machine progress."""

    agent_id = "protocol"
    domain = AgentDomain.PROTOCOL

    def applies_to(self, context: AgentContext) -> bool:
        if context.patterns_in_domains(PROTOCOL_DOMAINS):
            return True
        return bool(context.knowledge and context.knowledge.state_projection)

    def assess(self, context: AgentContext) -> AgentResult:
        patterns = context.patterns_in_domains(PROTOCOL_DOMAINS)
        observations: list[AgentObservation] = []
        recommendations: list[AgentRecommendation] = []
        limitations: list[str] = []

        for matched in patterns:
            evidence = context.pattern_evidence(matched)
            observations.append(
                AgentObservation(
                    statement=(
                        f"Known {matched.pack} pattern '{matched.name}' matched at "
                        f"score {matched.score:.2f}: {matched.summary}"
                    ),
                    evidence_ids=evidence,
                    knowledge_ids=[matched.pattern_id],
                )
            )
            if matched.playbook is not None:
                for step in matched.playbook.steps[:2]:
                    recommendations.append(
                        AgentRecommendation(
                            action=step.action,
                            rationale=(
                                f"Step {step.order} of the '{matched.playbook.name}' "
                                f"playbook for the matched {matched.pack} pattern."
                            ),
                            priority=step.order,
                            evidence_ids=evidence[:3],
                        )
                    )

        projection = context.knowledge.state_projection if context.knowledge else None
        if projection is not None and projection.stopped_at:
            reached = [s for s in projection.states if s.reached]
            observations.append(
                AgentObservation(
                    statement=(
                        f"Projected onto the {projection.name} state machine, the "
                        f"evidence never reached '{projection.stopped_at}': forward "
                        "progress stopped there."
                    ),
                    evidence_ids=sorted({i for s in reached for i in s.evidence_ids}),
                    knowledge_ids=[projection.machine_id],
                )
            )
        elif projection is None:
            limitations.append(
                "No protocol state machine matched this evidence, so the point where "
                "protocol progress stopped could not be located."
            )

        hypotheses = self._positions(context, patterns)
        if not patterns:
            limitations.append(
                "No wire-protocol failure pattern matched, so this assessment rests on "
                "state-machine progress alone."
            )
        return self.build(
            context,
            observations=observations,
            hypotheses=hypotheses,
            recommendations=recommendations,
            limitations=limitations,
        )

    @staticmethod
    def _positions(context: AgentContext, patterns) -> list[AgentHypothesis]:
        """One position per ownership class the matched patterns implicate."""
        strongest: dict[HypothesisCategory, tuple[float, object]] = {}
        for matched in patterns:
            ownership = context.pattern_ownership(matched.pattern_id)
            category_value = OWNERSHIP_CATEGORY.get(ownership or "")
            if category_value is None:
                continue
            category = HypothesisCategory(category_value)
            current = strongest.get(category)
            if current is None or matched.score > current[0]:
                strongest[category] = (matched.score, matched)

        positions: list[AgentHypothesis] = []
        for category, (score, matched) in strongest.items():
            evidence = context.pattern_evidence(matched)
            if not evidence:
                continue
            positions.append(
                AgentHypothesis(
                    category=category,
                    statement=(
                        f"The {matched.pack} pattern '{matched.name}' is a known "
                        f"{category.display_name.lower()} signature; its typical causes are "
                        f"{', '.join(matched.typical_causes[:2]) or 'documented in the pack'}."
                    ),
                    # A perfect clause match is strong but never certain: cap at 0.90.
                    confidence=round(min(0.90, 0.45 + 0.45 * score), 4),
                    evidence_ids=evidence,
                    knowledge_ids=[matched.pattern_id],
                )
            )
        return positions
