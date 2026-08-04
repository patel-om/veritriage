"""Explanation handlers: what something is, why it holds, why the rival lost.

Every statement here is assembled from a trace another layer already recorded:
`ConfidenceTrace.contributions` for hypotheses, `AgentContribution` for merged
findings, `StepValuation.terms` for plan steps. Nothing is computed and nothing
is phrased freely. If a layer did not record why, this says so instead.
"""

from __future__ import annotations

from veritriage.conversation.context import ConversationContext
from veritriage.conversation.registry import QuestionHandler, register_handler
from veritriage.models import (
    Answer,
    AnswerSection,
    Intent,
    NavigationContext,
    Question,
    Reference,
)


def _miss(question: Question, summary: str, limitation: str) -> Answer:
    """An honest miss: what was asked, why it could not be answered."""
    return Answer(
        intent=question.intent,
        question=question.text or f"{question.intent.value} {question.target or ''}".strip(),
        summary=summary,
        limitations=[limitation],
        resolved=False,
    )


@register_handler
class ExplainHandler(QuestionHandler):
    """What a hypothesis, agent, plan step, or classification actually is."""

    intent = Intent.EXPLAIN

    def answer(self, question, context, navigation):
        target = question.target or navigation.hypothesis_id
        report = context.report

        agent = context.agent(target) if target else None
        if agent is not None:
            return self._explain_agent(question, context, navigation, agent)

        hypothesis = context.hypothesis(target)
        if hypothesis is not None:
            return self._explain_hypothesis(question, context, navigation, hypothesis)

        step = context.plan_step(target) if target else None
        if step is not None:
            return self._explain_step(question, context, navigation, step)

        classification = report.classification
        sections = [
            AnswerSection(
                heading="Classification",
                statements=[
                    f"{classification.summary} (rule {classification.rule_name}, "
                    f"{classification.confidence}% confidence)."
                ],
                references=context.evidence_refs(
                    [e.node_id for e in classification.evidence if e.node_id]
                ),
            )
        ]
        answer = Answer(
            intent=Intent.EXPLAIN,
            question=question.text or "explain this run",
            summary=(
                f"This run was classified as {classification.category.display_name} "
                f"at {classification.confidence}% confidence."
            ),
            sections=sections,
            references=[r for s in sections for r in s.references],
            followups=[
                Question(intent=Intent.WHY, target=None),
                Question(intent=Intent.SHOW_EVIDENCE),
                Question(intent=Intent.SUMMARIZE, target="agents"),
            ],
            limitations=(
                []
                if target is None
                else [f"Nothing named {target!r} was found, so the run itself is described."]
            ),
        )
        return answer, navigation

    def _explain_hypothesis(self, question, context, navigation, hypothesis):
        trace = hypothesis.confidence_trace
        sections = [
            AnswerSection(
                heading="What this says",
                statements=[hypothesis.statement],
                references=[context.hypothesis_ref(hypothesis)],
            ),
            AnswerSection(
                heading="Supporting evidence",
                statements=[
                    f"{len(hypothesis.evidence_ids)} evidence node(s) support this."
                ],
                references=context.evidence_refs(hypothesis.evidence_ids),
            ),
        ]
        if trace.contributions:
            sections.append(
                AnswerSection(
                    heading="How the confidence was reached",
                    statements=[
                        f"Base {trace.base:.2f}.",
                        *[
                            f"{c.delta:+.3f} from {c.source}: {c.reason}"
                            for c in trace.contributions
                        ],
                        f"Multiplied by evidence factor {trace.evidence_factor:.2f} "
                        f"to give {trace.final:.2f}.",
                    ],
                    references=[
                        context.signal_ref(s)
                        for s in (context.report.reasoning.signals if context.report.reasoning else [])
                        if any(c.source == s.name for c in trace.contributions)
                    ],
                )
            )
        return (
            Answer(
                intent=Intent.EXPLAIN,
                question=question.text or f"explain {hypothesis.id}",
                summary=(
                    f"{hypothesis.title} at {hypothesis.confidence:.0%} confidence, "
                    f"generated by {hypothesis.generated_by}."
                ),
                sections=sections,
                references=[r for s in sections for r in s.references],
                followups=[
                    Question(intent=Intent.WHY, target=hypothesis.id),
                    Question(intent=Intent.WHY_NOT, target=hypothesis.id),
                    Question(intent=Intent.SHOW_EVIDENCE, target=hypothesis.id),
                ],
            ),
            navigation.model_copy(update={"hypothesis_id": hypothesis.id}),
        )

    def _explain_agent(self, question, context, navigation, agent):
        sections = [
            AnswerSection(
                heading="Position",
                statements=(
                    [h.statement for h in agent.hypotheses]
                    if agent.hypotheses
                    else ["This specialist formed no position."]
                ),
                references=[context.agent_ref(agent)],
            ),
            AnswerSection(
                heading="What it observed",
                statements=[o.statement for o in agent.observations] or ["Nothing recorded."],
                references=context.evidence_refs(agent.evidence_ids),
            ),
        ]
        if agent.limitations:
            sections.append(
                AnswerSection(
                    heading="What it could not determine",
                    statements=list(agent.limitations),
                )
            )
        return (
            Answer(
                intent=Intent.EXPLAIN,
                question=question.text or f"explain the {agent.agent_id} specialist",
                summary=(
                    f"The {agent.agent_id} specialist "
                    + (
                        f"leads with {agent.hypotheses[0].category.display_name} at "
                        f"{agent.confidence:.0%} confidence."
                        if agent.hypotheses
                        else ("abstained." if agent.abstained else "was not applicable.")
                    )
                ),
                sections=sections,
                references=[r for s in sections for r in s.references],
                followups=[
                    Question(intent=Intent.WHY_NOT, target=agent.agent_id),
                    Question(intent=Intent.SHOW_EVIDENCE, target=agent.agent_id),
                    Question(intent=Intent.SUMMARIZE, target="agents"),
                ],
            ),
            navigation.model_copy(update={"agent_id": agent.agent_id}),
        )

    def _explain_step(self, question, context, navigation, step):
        sections = [
            AnswerSection(
                heading="What to do and why",
                statements=[step.action, step.purpose],
                references=[context.plan_ref(step)],
            ),
            AnswerSection(
                heading="Why it sits where it does",
                statements=list(step.valuation.terms),
            ),
        ]
        if step.expected_observations:
            sections.append(
                AnswerSection(
                    heading="What you might see",
                    statements=list(step.expected_observations),
                )
            )
        return (
            Answer(
                intent=Intent.EXPLAIN,
                question=question.text or f"explain {step.step_id}",
                summary=f"{step.action} ({step.kind.value}, derived from {step.derived_from}).",
                sections=sections,
                references=[r for s in sections for r in s.references]
                + context.evidence_refs(step.evidence_ids),
                followups=[
                    Question(intent=Intent.TRACE, target=step.step_id),
                    Question(intent=Intent.SUMMARIZE, target="plan"),
                ],
            ),
            navigation.model_copy(update={"plan_step_id": step.step_id}),
        )


@register_handler
class WhyHandler(QuestionHandler):
    """Why a conclusion holds, from the trace the reasoning engine recorded."""

    intent = Intent.WHY

    def answer(self, question, context, navigation):
        hypothesis = context.hypothesis(question.target or navigation.hypothesis_id)
        if hypothesis is None:
            return (
                _miss(
                    question,
                    "There is no ranked hypothesis to explain.",
                    "This run produced no reasoning result, so there is no confidence "
                    "trace to walk.",
                ),
                navigation,
            )

        trace = hypothesis.confidence_trace
        sections = [
            AnswerSection(
                heading="The claim",
                statements=[hypothesis.statement],
                references=[context.hypothesis_ref(hypothesis)],
            )
        ]
        if trace.contributions:
            sections.append(
                AnswerSection(
                    heading="What moved the confidence",
                    statements=[
                        f"{c.delta:+.3f} from {c.source}: {c.reason}"
                        for c in trace.contributions
                    ],
                )
            )
        else:
            sections.append(
                AnswerSection(
                    heading="What moved the confidence",
                    statements=[
                        f"Nothing did: this rests on its base plausibility of "
                        f"{trace.base:.2f} and the quality of its evidence."
                    ],
                )
            )

        agents = context.report.agents
        if agents is not None:
            backing = [
                r
                for r in agents.results
                if r.hypotheses and r.hypotheses[0].category == hypothesis.category
            ]
            if backing:
                sections.append(
                    AnswerSection(
                        heading="Which specialists agree",
                        statements=[
                            f"{r.agent_id} leads with the same category at "
                            f"{r.confidence:.0%}."
                            for r in backing
                        ],
                        references=[context.agent_ref(r) for r in backing],
                    )
                )

        return (
            Answer(
                intent=Intent.WHY,
                question=question.text or f"why {hypothesis.id}",
                summary=(
                    f"{hypothesis.title} reached {hypothesis.confidence:.0%} from a base of "
                    f"{trace.base:.2f} adjusted by {len(trace.contributions)} signal(s)."
                ),
                sections=sections,
                references=[r for s in sections for r in s.references]
                + context.evidence_refs(hypothesis.evidence_ids, limit=5),
                followups=[
                    Question(intent=Intent.WHY_NOT, target=hypothesis.id),
                    Question(intent=Intent.SHOW_EVIDENCE, target=hypothesis.id),
                    Question(intent=Intent.TRACE, target=None),
                ],
            ),
            navigation.model_copy(update={"hypothesis_id": hypothesis.id}),
        )


@register_handler
class WhyNotHandler(QuestionHandler):
    """Why the alternatives lost, term by term."""

    intent = Intent.WHY_NOT

    def answer(self, question, context, navigation):
        report = context.report
        if report.reasoning is None or len(report.reasoning.hypotheses) < 2:
            return (
                _miss(
                    question,
                    "There were no competing explanations to rule out.",
                    "Fewer than two hypotheses were generated, so nothing lost.",
                ),
                navigation,
            )

        ranked = report.reasoning.hypotheses
        leader = ranked[0]
        named = context.hypothesis(question.target) if question.target else None
        losers = [h for h in ranked[1:] if named is None or h.id == named.id]
        if not losers:
            losers = ranked[1:]

        sections: list[AnswerSection] = []
        for loser in losers[:3]:
            gap = leader.confidence - loser.confidence
            statements = [
                f"{loser.title} reached {loser.confidence:.0%}, "
                f"{gap:.0%} behind {leader.title}."
            ]
            negatives = [c for c in loser.confidence_trace.contributions if c.delta < 0]
            positives = [c for c in leader.confidence_trace.contributions if c.delta > 0]
            statements += [f"{c.delta:+.3f} against it from {c.source}: {c.reason}" for c in negatives]
            if not negatives and positives:
                statements.append(
                    "Nothing argued against it directly; it simply gathered less support "
                    f"than {leader.title}."
                )
            sections.append(
                AnswerSection(
                    heading=f"Why not {loser.title}",
                    statements=statements,
                    references=[context.hypothesis_ref(loser)],
                )
            )

        agents = report.agents
        if agents is not None and agents.conflicts:
            sections.append(
                AnswerSection(
                    heading="Where the specialists disagreed",
                    statements=[c.note for c in agents.conflicts[:4]],
                    references=[
                        context.agent_ref(r)
                        for r in agents.results
                        if r.agent_id in {c.agent_a for c in agents.conflicts}
                        | {c.agent_b for c in agents.conflicts}
                    ],
                )
            )

        return (
            Answer(
                intent=Intent.WHY_NOT,
                question=question.text or "why not the alternatives",
                summary=(
                    f"{len(ranked) - 1} alternative explanation(s) were considered and "
                    f"ranked below {leader.title}."
                ),
                sections=sections,
                references=[r for s in sections for r in s.references],
                followups=[
                    Question(intent=Intent.WHY, target=leader.id),
                    Question(intent=Intent.SHOW_EVIDENCE, target=losers[0].id if losers else None),
                    Question(intent=Intent.SUMMARIZE, target="agents"),
                ],
            ),
            navigation,
        )
