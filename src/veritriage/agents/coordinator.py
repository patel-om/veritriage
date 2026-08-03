"""The Agent Coordinator: invoke, collect, merge, cross-examine.

    Evidence Graph -> Reasoning Engine -> Agent Coordinator -> Specialist Agents
        -> Combined Findings -> Prioritized Root Causes -> Recommendations

The Coordinator is a scheduler and an arbiter, not a reasoner. It contributes
no observation, no hypothesis, and no confidence of its own: everything in an
:class:`AgentAssessment` traces to an agent that cited evidence.

The load-bearing law, restated here because this is the module where it could
be broken: **agents form a second opinion, never a replacement verdict.** The
Coordinator reads the finished deterministic :class:`ReasoningResult` and
records whether it agrees, and nothing is reordered as a consequence of
disagreement.
"""

from __future__ import annotations

from veritriage.agents.base import Agent
from veritriage.agents.context import AgentContext
from veritriage.agents.providers import (
    NullProvider,
    ReasoningProvider,
    build_request,
)
from veritriage.agents.registry import default_agents
from veritriage.models import (
    AgentAssessment,
    AgentConflict,
    AgentContribution,
    AgentFinding,
    AgentRecommendation,
    AgentResult,
    ConsensusState,
    HypothesisCategory,
)

#: Confidence added for each agent beyond the first that independently
#: supports a category, and the cap on that corroboration.
CORROBORATION_STEP = 0.05
CORROBORATION_CAP = 0.15

#: Confidence removed once when another agent leads a different category.
CONTEST_PENALTY = 0.10

#: The agent layer never claims certainty. Unanimous specialists still leave
#: room for the evidence to be incomplete, matching every other confidence
#: ceiling in the platform (knowledge patterns cap at 0.90, rule verdicts at 95).
MERGED_CEILING = 0.95


class AgentCoordinator:
    """Runs the registered agents over one context and merges their positions."""

    def __init__(
        self,
        agents: list[Agent] | None = None,
        provider: ReasoningProvider | None = None,
    ) -> None:
        self._agents = agents  # None -> registry defaults, resolved per run
        self._provider = provider or NullProvider()

    def coordinate(self, context: AgentContext) -> AgentAssessment:
        """Invoke every applicable agent and merge what they concluded."""
        agents = self._agents if self._agents is not None else default_agents()
        agents = sorted(agents, key=lambda a: a.agent_id)

        results: list[AgentResult] = []
        invoked: list[str] = []
        not_applicable: list[str] = []
        abstained: list[str] = []

        for agent in agents:
            result = self._run_one(agent, context)
            results.append(result)
            if not result.applicable:
                not_applicable.append(agent.agent_id)
                continue
            invoked.append(agent.agent_id)
            if result.abstained:
                abstained.append(agent.agent_id)

        findings = _merge_findings(results)
        conflicts = _detect_conflicts(results)
        top = findings[0].category if findings else None
        reasoning_top = (
            context.reasoning.hypotheses[0].category
            if context.reasoning.hypotheses
            else None
        )
        return AgentAssessment(
            agents_invoked=invoked,
            agents_not_applicable=not_applicable,
            agents_abstained=abstained,
            results=results,
            findings=findings,
            conflicts=conflicts,
            recommendations=_merge_recommendations(results),
            limitations=sorted({limit for r in results for limit in r.limitations}),
            top_category=top,
            reasoning_top_category=reasoning_top,
            agrees_with_reasoning=(
                None if (top is None or reasoning_top is None) else top == reasoning_top
            ),
        )

    def _run_one(self, agent: Agent, context: AgentContext) -> AgentResult:
        """Assess with one agent, isolating failures like the orchestrator does."""
        try:
            if not agent.applies_to(context):
                return agent.not_applicable(
                    f"The {agent.domain.value} specialist had nothing in scope for this run."
                )
            result = agent.assess(context)
        except Exception as exc:  # one broken agent must not fail an investigation
            return AgentResult(
                agent_id=agent.agent_id,
                domain=agent.domain,
                applicable=False,
                limitations=[
                    f"The {agent.domain.value} specialist could not complete its "
                    f"assessment ({type(exc).__name__}); its perspective is missing "
                    "from this investigation."
                ],
            )
        return self._narrate(result)

    def _narrate(self, result: AgentResult) -> AgentResult:
        """Attach optional provider prose. Only narrative and provider apply."""
        if result.abstained or not result.hypotheses:
            return result
        try:
            response = self._provider.elaborate(build_request(result))
        except Exception:  # a provider failure never costs a conclusion
            return result
        if response is None:
            return result
        # Deliberately field by field: nothing else in a response is read, so a
        # provider cannot alter a hypothesis, a confidence, or a citation.
        return result.model_copy(
            update={
                "narrative": response.narrative,
                "provider": getattr(self._provider, "name", None),
            }
        )


def _merge_findings(results: list[AgentResult]) -> list[AgentFinding]:
    """Group agent positions by category and compute traceable confidence.

    final = clamp(base + corroboration + contest, 0.0, MERGED_CEILING)

    base          the highest confidence any single agent assigned the category
    corroboration +CORROBORATION_STEP per additional independent supporter,
                  capped at CORROBORATION_CAP
    contest       -CONTEST_PENALTY once, when another agent leads elsewhere

    Unanimity is capped below certainty on purpose: agreeing specialists can
    still all be reading incomplete evidence.
    """
    contributing = [r for r in results if r.applicable and not r.abstained]
    leading = {r.leading_category for r in contributing if r.leading_category is not None}

    grouped: dict[HypothesisCategory, list[tuple[str, float, str, list[str], list[str]]]] = {}
    for result in contributing:
        for hypothesis in result.hypotheses:
            grouped.setdefault(hypothesis.category, []).append(
                (
                    result.agent_id,
                    hypothesis.confidence,
                    hypothesis.statement,
                    hypothesis.evidence_ids,
                    hypothesis.knowledge_ids,
                )
            )

    findings: list[AgentFinding] = []
    for category, entries in grouped.items():
        entries.sort(key=lambda e: (-e[1], e[0]))
        strongest = entries[0]
        supporters = sorted({e[0] for e in entries})

        contributions = [
            AgentContribution(
                agent_id=strongest[0],
                delta=round(strongest[1], 4),
                reason="Strongest single position for this category.",
            )
        ]
        extra = len(supporters) - 1
        corroboration = min(CORROBORATION_CAP, CORROBORATION_STEP * extra) if extra > 0 else 0.0
        if corroboration:
            for agent_id in supporters:
                if agent_id == strongest[0]:
                    continue
                contributions.append(
                    AgentContribution(
                        agent_id=agent_id,
                        delta=round(corroboration / extra, 4),
                        reason="Independent corroboration from another specialist.",
                    )
                )
        contested = bool(leading - {category}) and category not in leading
        penalty = -CONTEST_PENALTY if contested else 0.0
        if penalty:
            others = sorted(c.value for c in leading)
            contributions.append(
                AgentContribution(
                    agent_id="coordinator",
                    delta=penalty,
                    reason=(
                        "No specialist leads with this category; another leads with "
                        f"{', '.join(others)}."
                    ),
                )
            )

        final = round(
            max(0.0, min(MERGED_CEILING, strongest[1] + corroboration + penalty)), 4
        )
        if len(supporters) > 1:
            consensus = ConsensusState.AGREEMENT
        elif contested:
            consensus = ConsensusState.CONTESTED
        else:
            consensus = ConsensusState.SINGLE_SOURCE
        findings.append(
            AgentFinding(
                category=category,
                statement=strongest[2],
                confidence=final,
                consensus=consensus,
                supporting_agents=supporters,
                contributions=contributions,
                evidence_ids=sorted({i for e in entries for i in e[3]}),
                knowledge_ids=sorted({i for e in entries for i in e[4]}),
            )
        )
    # Stable, deterministic ordering: confidence first, category name on ties.
    findings.sort(key=lambda f: (-f.confidence, f.category.value))
    return findings


def _detect_conflicts(results: list[AgentResult]) -> list[AgentConflict]:
    """Pairwise disagreement between agents' leading positions.

    Conflicts are surfaced, never resolved by suppression: two specialists
    disagreeing is the moment an engineer should look closely.
    """
    leaders = sorted(
        (
            (r.agent_id, r.leading_category)
            for r in results
            if r.applicable and not r.abstained and r.leading_category is not None
        ),
        key=lambda pair: pair[0],
    )
    conflicts: list[AgentConflict] = []
    for index, (agent_a, category_a) in enumerate(leaders):
        for agent_b, category_b in leaders[index + 1 :]:
            if category_a == category_b:
                continue
            conflicts.append(
                AgentConflict(
                    agent_a=agent_a,
                    agent_b=agent_b,
                    category_a=category_a,
                    category_b=category_b,
                    note=(
                        f"The {agent_a} specialist leads with "
                        f"{category_a.display_name} while the {agent_b} specialist "
                        f"leads with {category_b.display_name}."
                    ),
                )
            )
    return conflicts


def _merge_recommendations(results: list[AgentResult]) -> list[AgentRecommendation]:
    """Union every agent's recommendations, deduplicated by action.

    The lowest priority number wins on a duplicate action, and the surviving
    entry keeps the union of both citations: two specialists proposing the same
    step is corroboration, not repetition.
    """
    merged: dict[str, AgentRecommendation] = {}
    for result in results:
        for recommendation in result.recommendations:
            existing = merged.get(recommendation.action)
            if existing is None:
                merged[recommendation.action] = recommendation
                continue
            merged[recommendation.action] = existing.model_copy(
                update={
                    "priority": min(existing.priority, recommendation.priority),
                    "evidence_ids": sorted(
                        set(existing.evidence_ids) | set(recommendation.evidence_ids)
                    ),
                }
            )
    ordered = sorted(merged.values(), key=lambda r: (r.priority, r.action))
    return ordered
