"""Steps restated from the reasoning engine and the agent specialists.

Agent integration lives here, and it required no change to the `Agent` ABC:
agents already emit `AgentRecommendation`, and the Coordinator already merges
and deduplicates them across specialists. Planning reads that merged list. A
specialist proposes; the Coordinator merges; the Planner arranges. No agent
owns a plan, and none was rewritten to support one.

The reasoning source picks up `EngineeringRecommendation`s, which by the time
planning runs also include the historical precedent step appended by
`HistoryEngine.augment`, so regression precedent reaches the plan without a
dedicated source.
"""

from __future__ import annotations

from veritriage.models import HypothesisCategory, StepKind
from veritriage.planning.context import PlanningContext, StepCandidate
from veritriage.planning.registry import StepSource, register_source

#: EngineeringRecommendation effort labels -> the plan's 1..3 scale.
EFFORT = {"low": 1, "medium": 2, "high": 3}

#: Verbs that hint at what kind of action a restated recommendation is.
_KIND_HINTS = (
    (("inspect", "waveform", "open", "walk", "look"), StepKind.INSPECT),
    (("compare", "diff", "against"), StepKind.COMPARE),
    (("re-run", "rerun", "reproduce"), StepKind.REPRODUCE),
    (("collect", "capture", "dump", "obtain"), StepKind.COLLECT),
)


def _kind_of(action: str) -> StepKind:
    lowered = action.lower()
    for hints, kind in _KIND_HINTS:
        if any(hint in lowered for hint in hints):
            return kind
    return StepKind.VERIFY


@register_source
class ReasoningRecommendationSource(StepSource):
    """The deterministic engine's own next steps, restated as plan candidates."""

    source_id = "reasoning-recommendations"
    rank = 30

    def applies_to(self, context: PlanningContext) -> bool:
        reasoning = context.report.reasoning
        return reasoning is not None and bool(reasoning.recommendations)

    def propose(self, context: PlanningContext) -> list[StepCandidate]:
        reasoning = context.report.reasoning
        if reasoning is None:
            return []
        candidates: list[StepCandidate] = []
        for recommendation in reasoning.recommendations:
            category = self._category_for(recommendation, context)
            candidates.append(
                StepCandidate(
                    kind=_kind_of(recommendation.action),
                    action=recommendation.action,
                    purpose=recommendation.rationale,
                    derived_from=f"reasoning:recommendation:{recommendation.priority}",
                    addresses=[category] if category else [],
                    expected_observations=[
                        "A result consistent with the rationale supports this explanation",
                        "An inconsistent result weakens it and promotes the alternatives",
                    ],
                    module=recommendation.module,
                    effort=EFFORT.get(recommendation.effort, 2),
                    evidence_ids=context.resolve(list(recommendation.evidence_ids)),
                )
            )
        return candidates

    @staticmethod
    def _category_for(recommendation, context: PlanningContext) -> HypothesisCategory | None:
        """Attribute a recommendation to the hypothesis whose evidence it cites."""
        cited = set(recommendation.evidence_ids)
        for hypothesis in context.hypotheses:
            if cited & set(hypothesis.evidence_ids):
                return hypothesis.category
        leading = context.leading
        return leading.category if leading is not None else None


@register_source
class AgentRecommendationSource(StepSource):
    """What the domain specialists proposed, already merged by the Coordinator."""

    source_id = "agent-recommendations"
    rank = 20  # a specialist's suggestion outranks a generic template

    def applies_to(self, context: PlanningContext) -> bool:
        agents = context.report.agents
        return agents is not None and bool(agents.recommendations)

    def propose(self, context: PlanningContext) -> list[StepCandidate]:
        agents = context.report.agents
        if agents is None:
            return []
        # Which specialist proposed what, so provenance names a real agent.
        proposer: dict[str, str] = {}
        for result in agents.results:
            for recommendation in result.recommendations:
                proposer.setdefault(recommendation.action, result.agent_id)

        candidates: list[StepCandidate] = []
        for recommendation in agents.recommendations:
            agent_id = proposer.get(recommendation.action, "coordinator")
            category = self._category_for(agent_id, agents)
            candidates.append(
                StepCandidate(
                    kind=_kind_of(recommendation.action),
                    action=recommendation.action,
                    purpose=recommendation.rationale,
                    derived_from=f"agent:{agent_id}:recommendation",
                    addresses=[category] if category else [],
                    expected_observations=[
                        f"Confirmation strengthens the {agent_id} specialist's position",
                        "A negative result is itself informative: it removes one explanation",
                    ],
                    module=context.failing_scope(),
                    # Specialists propose focused actions; treat them as medium
                    # unless the Coordinator ranked them first.
                    effort=1 if recommendation.priority <= 1 else 2,
                    evidence_ids=context.resolve(list(recommendation.evidence_ids)),
                    bonus=0.3,
                    bonus_reason=f"proposed by the {agent_id} specialist",
                )
            )
        return candidates

    @staticmethod
    def _category_for(agent_id: str, agents) -> HypothesisCategory | None:
        for result in agents.results:
            if result.agent_id == agent_id:
                return result.leading_category
        return agents.top_category
