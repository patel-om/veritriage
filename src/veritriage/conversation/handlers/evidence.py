"""Evidence handlers: show what backs a claim, and narrow the view.

Filtering is navigation state, never analysis. Applying a filter changes what
the next answer shows and nothing about what the platform concluded, which is
why the filter lives in :class:`NavigationContext` rather than anywhere near a
report field.
"""

from __future__ import annotations

from veritriage.conversation.context import ConversationContext
from veritriage.conversation.registry import QuestionHandler, register_handler
from veritriage.graph.model import ArtifactType
from veritriage.models import (
    Answer,
    AnswerSection,
    Intent,
    NavigationContext,
    Question,
)

#: How many evidence nodes one answer shows before it stops being readable.
MAX_SHOWN = 12


def _matches(node, filter_term: str | None) -> bool:
    """Whether a node survives the active filter.

    A filter may name an artifact type, a severity, or a module. All three are
    fields the node already carries; nothing is inferred.
    """
    if not filter_term:
        return True
    term = filter_term.strip().lower()
    if node.artifact_type.value == term or node.artifact_type.value.replace("_", " ") == term:
        return True
    if node.severity is not None and node.severity.value == term:
        return True
    if node.module and term in node.module.lower():
        return True
    # A protocol filter matches the pack a scope or description names.
    return term in node.description.lower()


@register_handler
class ShowEvidenceHandler(QuestionHandler):
    """The evidence behind the current or named subject."""

    intent = Intent.SHOW_EVIDENCE

    def answer(self, question, context, navigation):
        target = question.target or navigation.hypothesis_id
        subject = "this run"
        node_ids: list[str] = []

        hypothesis = context.hypothesis(target) if target else None
        agent = context.agent(target) if target else None
        if agent is not None:
            node_ids = list(agent.evidence_ids)
            subject = f"the {agent.agent_id} specialist"
        elif hypothesis is not None:
            node_ids = list(hypothesis.evidence_ids)
            subject = hypothesis.title
        else:
            node_ids = [n.id for n in context.graph.failing()]
            subject = "this run's failing evidence"

        active_filter = question.filter or navigation.evidence_filter
        nodes = [
            context.graph.nodes[i]
            for i in node_ids
            if i in context.graph.nodes and _matches(context.graph.nodes[i], active_filter)
        ]

        references = context.evidence_refs([n.id for n in nodes], limit=MAX_SHOWN)
        sections = [
            AnswerSection(
                heading="Evidence",
                statements=[
                    f"{n.description}"
                    + (f"  [{n.module}]" if n.module else "")
                    + (f"  t={n.sim_time}" if n.sim_time else "")
                    for n in nodes[:MAX_SHOWN]
                ]
                or ["Nothing matched."],
                references=references,
            )
        ]
        limitations = []
        if len(nodes) > MAX_SHOWN:
            limitations.append(
                f"{len(nodes) - MAX_SHOWN} further node(s) matched and are not shown; "
                "narrow the view with a filter."
            )
        if active_filter and not nodes:
            limitations.append(
                f"No evidence matched the filter {active_filter!r}. "
                "Filters match artifact type, severity, or module."
            )

        return (
            Answer(
                intent=Intent.SHOW_EVIDENCE,
                question=question.text or f"show evidence for {subject}",
                summary=(
                    f"{len(nodes)} evidence node(s) support {subject}"
                    + (f", filtered by {active_filter!r}" if active_filter else "")
                    + "."
                ),
                sections=sections,
                references=references,
                followups=[
                    Question(intent=Intent.FILTER, filter="error"),
                    Question(intent=Intent.WHY, target=hypothesis.id if hypothesis else None),
                    Question(intent=Intent.TRACE, target=None),
                ],
                limitations=limitations,
            ),
            navigation,
        )


@register_handler
class FilterHandler(QuestionHandler):
    """Narrow the view. Navigation state only; conclusions are untouched."""

    intent = Intent.FILTER

    def answer(self, question, context, navigation):
        term = (question.filter or question.target or "").strip()
        if not term or term in {"all", "everything", "none", "off"}:
            cleared = navigation.model_copy(update={"evidence_filter": None})
            return (
                Answer(
                    intent=Intent.FILTER,
                    question=question.text or "clear the filter",
                    summary="Filter cleared; every evidence node is in view again.",
                    followups=[Question(intent=Intent.SHOW_EVIDENCE)],
                ),
                cleared,
            )

        matching = [n for n in context.graph.nodes.values() if _matches(n, term)]
        known_types = sorted({n.artifact_type.value for n in context.graph.nodes.values()})
        limitations = []
        if not matching:
            limitations.append(
                f"Nothing in this run matches {term!r}. Available artifact types: "
                f"{', '.join(known_types)}."
            )

        return (
            Answer(
                intent=Intent.FILTER,
                question=question.text or f"show only {term}",
                summary=(
                    f"Filter set to {term!r}: {len(matching)} of "
                    f"{len(context.graph.nodes)} evidence node(s) remain in view."
                ),
                sections=[
                    AnswerSection(
                        heading="In view",
                        statements=[n.description for n in matching[:MAX_SHOWN]] or ["Nothing."],
                        references=context.evidence_refs(
                            [n.id for n in matching], limit=MAX_SHOWN
                        ),
                    )
                ],
                references=context.evidence_refs([n.id for n in matching], limit=MAX_SHOWN),
                followups=[
                    Question(intent=Intent.SHOW_EVIDENCE),
                    Question(intent=Intent.FILTER, filter="all"),
                ],
                limitations=limitations,
                resolved=bool(matching),
            ),
            navigation.model_copy(update={"evidence_filter": term}),
        )
