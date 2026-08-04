"""Navigation, summary, and help.

Navigation is the whole point of the milestone: moving between layers while
every transition stays a resolvable reference. Summaries are bounded views of
one layer. Help declares the vocabulary, so a user is never left guessing what
the platform can be asked.
"""

from __future__ import annotations

from veritriage.conversation.context import ConversationContext
from veritriage.conversation.parse import vocabulary
from veritriage.conversation.registry import QuestionHandler, register_handler
from veritriage.models import (
    Answer,
    AnswerSection,
    Intent,
    NavigationContext,
    Question,
    Reference,
    ReferenceKind,
)

#: Layers a summary can be asked for.
SUMMARISABLE = (
    "evidence",
    "reasoning",
    "agents",
    "knowledge",
    "learning",
    "plan",
    "design",
    "history",
)


@register_handler
class NavigateHandler(QuestionHandler):
    """Move to a module, agent, hypothesis, or design node."""

    intent = Intent.NAVIGATE

    def answer(self, question, context, navigation):
        target = (question.target or "").strip()
        if not target:
            return (
                Answer(
                    intent=Intent.NAVIGATE,
                    question=question.text or "navigate",
                    summary=f"Currently at: {navigation.describe()}.",
                    followups=[Question(intent=Intent.HELP)],
                    limitations=["No destination was named."],
                    resolved=False,
                ),
                navigation,
            )

        agent = context.agent(target)
        if agent is not None:
            return (
                self._moved(
                    question,
                    f"the {agent.agent_id} specialist",
                    [context.agent_ref(agent)],
                    [
                        Question(intent=Intent.EXPLAIN, target=agent.agent_id),
                        Question(intent=Intent.SHOW_EVIDENCE, target=agent.agent_id),
                    ],
                ),
                navigation.model_copy(update={"agent_id": agent.agent_id}),
            )

        hypothesis = context.hypothesis(target)
        if hypothesis is not None:
            return (
                self._moved(
                    question,
                    hypothesis.title,
                    [context.hypothesis_ref(hypothesis)],
                    [
                        Question(intent=Intent.WHY, target=hypothesis.id),
                        Question(intent=Intent.WHY_NOT, target=hypothesis.id),
                    ],
                ),
                navigation.model_copy(update={"hypothesis_id": hypothesis.id}),
            )

        design = context.report.design
        if design is not None:
            node = next(
                (
                    n
                    for n in design.affected_region
                    if n.name.lower() == target.lower() or n.node_id == target
                ),
                None,
            )
            if node is not None:
                return (
                    self._moved(
                        question,
                        f"{node.name} ({node.kind})",
                        [context.design_ref(node)],
                        [
                            Question(intent=Intent.EXPLAIN, target=node.name),
                            Question(intent=Intent.SUMMARIZE, target="design"),
                        ],
                    ),
                    navigation.model_copy(
                        update={"design_node_id": node.node_id, "module": node.name}
                    ),
                )

        scoped = [n for n in context.graph.nodes.values() if n.module and target.lower() in n.module.lower()]
        if scoped:
            return (
                self._moved(
                    question,
                    f"scope {target}",
                    context.evidence_refs([n.id for n in scoped], limit=6),
                    [
                        Question(intent=Intent.SHOW_EVIDENCE, target=None),
                        Question(intent=Intent.SUMMARIZE, target="design"),
                    ],
                ),
                navigation.model_copy(update={"module": target}),
            )

        return (
            Answer(
                intent=Intent.NAVIGATE,
                question=question.text or f"go to {target}",
                summary=f"Nothing named {target!r} exists in this investigation.",
                limitations=[
                    "Navigation targets are agents, hypotheses, design elements, or "
                    "module scopes present in this run. Ask 'help' for the full list."
                ],
                followups=[Question(intent=Intent.HELP)],
                resolved=False,
            ),
            navigation,
        )

    @staticmethod
    def _moved(question, where, references, followups) -> Answer:
        return Answer(
            intent=Intent.NAVIGATE,
            question=question.text or f"go to {where}",
            summary=f"Now looking at {where}.",
            sections=[AnswerSection(heading="Selected", statements=[where], references=references)],
            references=references,
            followups=followups,
        )


@register_handler
class SummarizeHandler(QuestionHandler):
    """A bounded view of one intelligence layer."""

    intent = Intent.SUMMARIZE

    def answer(self, question, context, navigation):
        layer = (question.target or "").strip().lower()
        report = context.report
        if layer not in SUMMARISABLE:
            return (
                Answer(
                    intent=Intent.SUMMARIZE,
                    question=question.text or "summarize",
                    summary=f"This run is {report.classification.category.display_name}.",
                    sections=[
                        AnswerSection(
                            heading="Available summaries",
                            statements=[f"summarize {name}" for name in SUMMARISABLE],
                        )
                    ],
                    followups=[
                        Question(intent=Intent.SUMMARIZE, target=name)
                        for name in ("agents", "plan", "design")
                    ],
                    limitations=(
                        [] if not layer else [f"{layer!r} is not a summarisable layer."]
                    ),
                ),
                navigation,
            )

        builder = getattr(self, f"_{layer}")
        summary, sections, references = builder(context)
        return (
            Answer(
                intent=Intent.SUMMARIZE,
                question=question.text or f"summarize {layer}",
                summary=summary,
                sections=sections,
                references=references,
                followups=[
                    Question(intent=Intent.WHY, target=None),
                    Question(intent=Intent.SHOW_EVIDENCE),
                ],
                limitations=(
                    [] if sections else [f"This run carries no {layer} intelligence."]
                ),
                resolved=bool(sections),
            ),
            navigation,
        )

    @staticmethod
    def _evidence(context):
        stats = context.report.graph_stats
        failing = context.graph.failing()
        return (
            f"{stats.node_count} evidence node(s), {len(failing)} failing, "
            f"joined by {stats.edge_count} relationship(s).",
            [
                AnswerSection(
                    heading="Failing evidence",
                    statements=[n.description for n in failing[:8]],
                    references=context.evidence_refs([n.id for n in failing]),
                )
            ]
            if failing
            else [],
            context.evidence_refs([n.id for n in failing]),
        )

    @staticmethod
    def _reasoning(context):
        reasoning = context.report.reasoning
        if reasoning is None:
            return "No reasoning result.", [], []
        references = [context.hypothesis_ref(h) for h in reasoning.hypotheses]
        return (
            f"{len(reasoning.hypotheses)} ranked hypothesis(es) from "
            f"{len(reasoning.signals)} deterministic signal(s).",
            [
                AnswerSection(
                    heading="Ranked hypotheses",
                    statements=[
                        f"{h.title}: {h.confidence:.0%}" for h in reasoning.hypotheses
                    ],
                    references=references,
                ),
                AnswerSection(
                    heading="Signals that fired",
                    statements=[s.name for s in reasoning.signals],
                    references=[context.signal_ref(s) for s in reasoning.signals],
                ),
            ],
            references,
        )

    @staticmethod
    def _agents(context):
        agents = context.report.agents
        if agents is None:
            return "No agent assessment.", [], []
        references = [context.agent_ref(r) for r in agents.results if r.applicable]
        sections = [
            AnswerSection(
                heading="Merged findings",
                statements=[
                    f"{f.category.display_name}: {f.confidence:.0%} "
                    f"({f.consensus.value}, {', '.join(f.supporting_agents)})"
                    for f in agents.findings
                ],
                references=references,
            )
        ]
        if agents.conflicts:
            sections.append(
                AnswerSection(
                    heading="Disagreements",
                    statements=[c.note for c in agents.conflicts[:4]],
                )
            )
        return (
            f"{len(agents.agents_invoked)} specialist(s) consulted; "
            + (
                "they agree with the deterministic ranking."
                if agents.agrees_with_reasoning
                else "they diverge from the deterministic ranking."
            ),
            sections,
            references,
        )

    @staticmethod
    def _knowledge(context):
        knowledge = context.report.knowledge
        if knowledge is None or not knowledge.patterns:
            return "No known pattern matched.", [], []
        references = [context.knowledge_ref(p) for p in knowledge.patterns]
        return (
            f"{len(knowledge.patterns)} known verification pattern(s) matched.",
            [
                AnswerSection(
                    heading="Matched patterns",
                    statements=[
                        f"{p.name} ({p.pack}, {p.score:.0%}): {p.summary}"
                        for p in knowledge.patterns
                    ],
                    references=references,
                )
            ],
            references,
        )

    @staticmethod
    def _learning(context):
        learning = context.report.learning
        if learning is None:
            return "Nothing has been learned yet.", [], []
        references = [context.learning_ref(h) for h in learning.hints]
        return (
            f"Learned from {learning.corpus_size} prior investigation(s).",
            [
                AnswerSection(
                    heading="What history suggests",
                    statements=[h.statement for h in learning.hints],
                    references=references,
                )
            ],
            references,
        )

    @staticmethod
    def _plan(context):
        plan = context.report.plan
        if plan is None:
            return "No investigation plan.", [], []
        references = [context.plan_ref(s) for s in plan.steps]
        return (
            f"{plan.objective} Estimated effort {plan.estimated_effort}.",
            [
                AnswerSection(
                    heading="Recommended steps",
                    statements=[
                        f"{s.action} (value/effort {s.valuation.priority_score:.2f})"
                        for s in plan.steps
                    ],
                    references=references,
                ),
                AnswerSection(
                    heading="Evidence still needed",
                    statements=[f"{r.what}: {r.why}" for r in plan.evidence_requests],
                ),
            ],
            references,
        )

    @staticmethod
    def _design(context):
        design = context.report.design
        if design is None:
            return "No structural model was supplied.", [], []
        references = [context.design_ref(n) for n in design.affected_region]
        sections = [
            AnswerSection(
                heading="Affected design region",
                statements=[f"{n.name} ({n.kind})" for n in design.affected_region],
                references=references,
            )
        ]
        if design.clock_domains:
            sections.append(
                AnswerSection(
                    heading="Clock domains",
                    statements=[
                        f"{d.name}: {', '.join(d.modules) or 'no modules declared'}"
                        for d in design.clock_domains
                    ],
                )
            )
        return (
            f"{design.node_count} structural element(s) joined by "
            f"{design.edge_count} typed relationship(s).",
            sections,
            references,
        )

    @staticmethod
    def _history(context):
        history = context.report.history
        if history is None:
            return "This run was not recorded.", [], []
        references = [context.history_ref(s) for s in history.similar]
        return (
            (
                f"Seen {history.times_seen} time(s) before."
                if history.seen_before
                else "This failure signature is new."
            ),
            [
                AnswerSection(
                    heading="Similar regressions",
                    statements=[
                        f"{s.regression_id} ({s.score:.0%}): {s.root_cause}"
                        for s in history.similar
                    ],
                    references=references,
                )
            ]
            if history.similar
            else [],
            references,
        )


@register_handler
class HelpHandler(QuestionHandler):
    """What can be asked here, given where the user currently is."""

    intent = Intent.HELP

    def answer(self, question, context, navigation):
        report = context.report
        available = [
            name
            for name, present in (
                ("evidence", True),
                ("reasoning", report.reasoning is not None),
                ("agents", report.agents is not None),
                ("knowledge", report.knowledge is not None),
                ("learning", report.learning is not None),
                ("plan", report.plan is not None),
                ("design", report.design is not None),
                ("history", report.history is not None),
            )
            if present
        ]
        return (
            Answer(
                intent=Intent.HELP,
                question=question.text or "help",
                summary=(
                    f"This investigation carries {len(available)} layer(s) you can "
                    f"explore: {', '.join(available)}."
                ),
                sections=[
                    AnswerSection(heading="Phrasings understood", statements=vocabulary()),
                    AnswerSection(
                        heading="Where you are",
                        statements=[navigation.describe()],
                    ),
                ],
                followups=[
                    Question(intent=Intent.WHY, target=None),
                    Question(intent=Intent.SUMMARIZE, target="agents"),
                    Question(intent=Intent.SHOW_EVIDENCE),
                ],
            ),
            navigation,
        )
