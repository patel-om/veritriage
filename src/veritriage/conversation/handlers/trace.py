"""Trace and compare: the joins the report performs and then discards.

``TRACE`` walks a recommendation or plan step back to the artifact it came
from, across layers, which is the four-call manual correlation this milestone
exists to remove. ``COMPARE`` puts this run beside another session or a
historical regression.
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
)


@register_handler
class TraceHandler(QuestionHandler):
    """Where a recommendation came from, layer by layer."""

    intent = Intent.TRACE

    def answer(self, question, context, navigation):
        report = context.report
        target = question.target or navigation.plan_step_id

        step = context.plan_step(target) if target else None
        if step is None and report.plan is not None and report.plan.steps:
            step = report.plan.steps[0]

        if step is None:
            return self._trace_recommendation(question, context, navigation)

        sections = [
            AnswerSection(
                heading="The step",
                statements=[step.action, step.purpose],
                references=[context.plan_ref(step)],
            ),
            AnswerSection(
                heading="Where it came from",
                statements=[
                    f"Derived from {step.derived_from}.",
                    *step.valuation.terms,
                ],
            ),
        ]

        # Cross-layer join: the artifact named in derived_from, resolved.
        origin = step.derived_from.split(":")
        kind = origin[0] if origin else ""
        if kind == "knowledge" and report.knowledge is not None:
            pattern_id = origin[2].split("#")[0] if len(origin) > 2 else ""
            matched = [
                p
                for p in report.knowledge.patterns
                if p.playbook is not None and p.playbook.playbook_id == pattern_id
            ]
            if matched:
                sections.append(
                    AnswerSection(
                        heading="The curated pattern behind it",
                        statements=[f"{p.name} ({p.pack}): {p.summary}" for p in matched],
                        references=[context.knowledge_ref(p) for p in matched],
                    )
                )
        elif kind == "agent" and report.agents is not None:
            agent = context.agent(origin[1]) if len(origin) > 1 else None
            if agent is not None:
                sections.append(
                    AnswerSection(
                        heading="The specialist that proposed it",
                        statements=[o.statement for o in agent.observations[:3]],
                        references=[context.agent_ref(agent)],
                    )
                )

        if step.addresses:
            addressed = [
                context.hypothesis(c.value)
                for c in step.addresses
            ]
            resolved = [h for h in addressed if h is not None]
            if resolved:
                sections.append(
                    AnswerSection(
                        heading="What it would settle",
                        statements=[
                            f"{h.title}, currently {h.confidence:.0%}." for h in resolved
                        ],
                        references=[context.hypothesis_ref(h) for h in resolved],
                    )
                )

        return (
            Answer(
                intent=Intent.TRACE,
                question=question.text or f"trace {step.step_id}",
                summary=(
                    f"'{step.action}' traces back to {step.derived_from} and bears on "
                    f"{len(step.addresses)} hypothesis(es)."
                ),
                sections=sections,
                references=[r for s in sections for r in s.references]
                + context.evidence_refs(step.evidence_ids, limit=5),
                followups=[
                    Question(intent=Intent.EXPLAIN, target=step.step_id),
                    Question(intent=Intent.SUMMARIZE, target="plan"),
                ],
            ),
            navigation.model_copy(update={"plan_step_id": step.step_id}),
        )

    @staticmethod
    def _trace_recommendation(question, context, navigation):
        reasoning = context.report.reasoning
        if reasoning is None or not reasoning.recommendations:
            return (
                Answer(
                    intent=Intent.TRACE,
                    question=question.text or "trace",
                    summary="There is nothing to trace.",
                    limitations=["This run produced no plan and no recommendations."],
                    resolved=False,
                ),
                navigation,
            )
        steps = reasoning.recommendations
        return (
            Answer(
                intent=Intent.TRACE,
                question=question.text or "trace the recommendations",
                summary=f"{len(steps)} recommendation(s), each carrying its rationale.",
                sections=[
                    AnswerSection(
                        heading="Recommendations and why",
                        statements=[f"{s.action} - {s.rationale}" for s in steps],
                        references=context.evidence_refs(
                            [i for s in steps for i in s.evidence_ids]
                        ),
                    )
                ],
                references=context.evidence_refs([i for s in steps for i in s.evidence_ids]),
                followups=[Question(intent=Intent.SUMMARIZE, target="plan")],
            ),
            navigation,
        )


@register_handler
class CompareHandler(QuestionHandler):
    """This run beside a historical regression."""

    intent = Intent.COMPARE

    def answer(self, question, context, navigation):
        history = context.report.history
        target = (question.target or "").strip()

        if history is None or not history.similar:
            return (
                Answer(
                    intent=Intent.COMPARE,
                    question=question.text or "compare",
                    summary="There is nothing recorded to compare against.",
                    limitations=[
                        "This run was not recorded in the regression database, or no "
                        "similar prior regression was found."
                    ],
                    followups=[Question(intent=Intent.SUMMARIZE, target="history")],
                    resolved=False,
                ),
                navigation,
            )

        similar = history.similar
        chosen = next((s for s in similar if s.regression_id == target), None) if target else None
        if target and chosen is None:
            return (
                Answer(
                    intent=Intent.COMPARE,
                    question=question.text or f"compare with {target}",
                    summary=f"Regression {target!r} is not among the similar runs found.",
                    sections=[
                        AnswerSection(
                            heading="Available comparisons",
                            statements=[
                                f"{s.regression_id} ({s.score:.0%} similar)" for s in similar
                            ],
                            references=[context.history_ref(s) for s in similar],
                        )
                    ],
                    references=[context.history_ref(s) for s in similar],
                    limitations=[
                        "Comparison is limited to regressions the similarity engine "
                        "already surfaced for this run."
                    ],
                    resolved=False,
                ),
                navigation,
            )

        chosen = chosen or similar[0]
        classification = context.report.classification
        sections = [
            AnswerSection(
                heading="This run",
                statements=[
                    f"{classification.category.display_name} at "
                    f"{classification.confidence}% (rule {classification.rule_name})."
                ],
            ),
            AnswerSection(
                heading=f"Regression {chosen.regression_id}",
                statements=[
                    f"Classified {chosen.classification}.",
                    f"Root cause recorded as: {chosen.root_cause}",
                    (
                        "Failure signatures are identical."
                        if chosen.signature_match
                        else f"Similarity {chosen.score:.0%}, signatures differ."
                    ),
                ],
                references=[context.history_ref(chosen)],
            ),
        ]
        return (
            Answer(
                intent=Intent.COMPARE,
                question=question.text or f"compare with {chosen.regression_id}",
                summary=(
                    f"This run resembles {chosen.regression_id} at {chosen.score:.0%}"
                    + (" with an identical signature." if chosen.signature_match else ".")
                ),
                sections=sections,
                references=[r for s in sections for r in s.references],
                followups=[
                    Question(intent=Intent.SUMMARIZE, target="history"),
                    Question(intent=Intent.WHY, target=None),
                ],
            ),
            navigation,
        )
