"""Prompt construction: structured objects in, a frozen inspectable Prompt out.

Never string concatenation over free text. A :class:`PromptBuilder` consumes
platform objects, collects the citations they carry, and produces a frozen
:class:`Prompt`. Building is a pure function of its input, so the same
structured objects always produce the same prompt, and what a provider is about
to be asked can be audited before it is asked.

The citation set is assembled here, and it is the whole grounding mechanism:
whatever ends up in ``Prompt.citations`` is exactly what a response is permitted
to reference. Everything else is stripped downstream.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from veritriage.models import (
    Answer,
    AnalysisReport,
    Citation,
    Prompt,
    PromptSection,
    RenderStyle,
)

#: The hard rules every prompt carries. Versioned, so a change to what a
#: provider is told is a visible change rather than a silent one.
SYSTEM_TEMPLATE_VERSION = "1"

_SYSTEM = """\
You are rendering the findings of a deterministic semiconductor verification
platform into prose for a design verification engineer.

Everything below was established deterministically before you were called. Your
only job is to communicate it clearly.

Hard rules:
- Never state a conclusion that is not present in the material below.
- Never invent a module, signal, time, confidence, or cause.
- Cite artifacts using the exact tokens provided. Do not invent tokens.
- If the material does not answer something, say that it does not.
- Do not speculate about root causes beyond what the hypotheses state."""


class PromptTemplate(BaseModel):
    """A versioned recipe: what a provider is told, and what it is asked for."""

    model_config = ConfigDict(frozen=True)

    template_id: str
    version: str = SYSTEM_TEMPLATE_VERSION
    system: str = _SYSTEM
    task: str
    style: RenderStyle = RenderStyle.ENGINEER


class PromptContext(BaseModel):
    """The structured material a prompt is built from.

    Every field is an existing platform object. There is no field for free
    text, which is what stops a caller from smuggling ungrounded content into a
    prompt.
    """

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    report: AnalysisReport | None = None
    answer: Answer | None = None
    extra_sections: tuple[PromptSection, ...] = Field(
        default=(),
        description="Pre-built sections from a caller that already assembled objects.",
    )


class PromptBuilder:
    """Turns structured platform objects into a frozen, inspectable prompt."""

    def __init__(self, template: PromptTemplate) -> None:
        self._template = template

    def build(self, context: PromptContext) -> Prompt:
        """Assemble the prompt. Pure function of the context."""
        sections: list[PromptSection] = []
        citations: dict[str, Citation] = {}

        def cite(kind: str, ref_id: str, label: str) -> Citation:
            citation = Citation(kind=kind, ref_id=ref_id, label=label[:120])
            citations.setdefault(citation.token, citation)
            return citation

        if context.report is not None:
            sections.extend(self._report_sections(context.report, cite))
        if context.answer is not None:
            sections.extend(self._answer_sections(context.answer, cite))
        sections.extend(context.extra_sections)
        for section in context.extra_sections:
            for citation in section.citations:
                citations.setdefault(citation.token, citation)

        return Prompt(
            template_id=self._template.template_id,
            template_version=self._template.version,
            style=self._template.style,
            system=self._template.system,
            task=self._template.task,
            sections=tuple(s for s in sections if s.lines),
            citations=tuple(citations[token] for token in sorted(citations)),
        )

    # --- Section builders ---------------------------------------------------

    @staticmethod
    def _report_sections(report: AnalysisReport, cite) -> list[PromptSection]:
        sections: list[PromptSection] = []
        classification = report.classification

        verdict_citations = [
            cite("evidence", e.node_id, e.description)
            for e in classification.evidence
            if e.node_id
        ]
        sections.append(
            PromptSection(
                heading="Verdict",
                lines=(
                    f"Classified {classification.category.display_name} at "
                    f"{classification.confidence}% confidence by rule "
                    f"{classification.rule_name}.",
                    classification.summary,
                ),
                citations=tuple(verdict_citations),
            )
        )

        if report.reasoning is not None and report.reasoning.hypotheses:
            lines: list[str] = []
            hypothesis_citations: list[Citation] = []
            for hypothesis in report.reasoning.hypotheses:
                token = cite("hypothesis", hypothesis.id, hypothesis.title)
                hypothesis_citations.append(token)
                lines.append(
                    f"{token.token} {hypothesis.title} at {hypothesis.confidence:.0%}: "
                    f"{hypothesis.statement}"
                )
            sections.append(
                PromptSection(
                    heading="Ranked hypotheses",
                    lines=tuple(lines),
                    citations=tuple(hypothesis_citations),
                )
            )
            if report.reasoning.signals:
                sections.append(
                    PromptSection(
                        heading="Deterministic signals that fired",
                        lines=tuple(
                            f"{s.name}: {s.description}" for s in report.reasoning.signals
                        ),
                    )
                )

        if report.knowledge is not None and report.knowledge.patterns:
            lines = []
            pattern_citations = []
            for pattern in report.knowledge.patterns:
                token = cite("knowledge", pattern.pattern_id, pattern.name)
                pattern_citations.append(token)
                lines.append(
                    f"{token.token} {pattern.name} ({pattern.pack}, {pattern.score:.0%} "
                    f"match): {pattern.summary}"
                )
            sections.append(
                PromptSection(
                    heading="Known verification patterns matched",
                    lines=tuple(lines),
                    citations=tuple(pattern_citations),
                )
            )

        if report.agents is not None and report.agents.findings:
            lines = []
            agent_citations = []
            for finding in report.agents.findings:
                lines.append(
                    f"{finding.category.display_name} at {finding.confidence:.0%} "
                    f"({finding.consensus.value}, supported by "
                    f"{', '.join(finding.supporting_agents)})."
                )
            for result in report.agents.results:
                if result.applicable and result.hypotheses:
                    agent_citations.append(
                        cite("agent", result.agent_id, f"{result.agent_id} specialist")
                    )
            if report.agents.conflicts:
                lines.extend(c.note for c in report.agents.conflicts[:3])
            sections.append(
                PromptSection(
                    heading="Domain specialist findings",
                    lines=tuple(lines),
                    citations=tuple(agent_citations),
                )
            )

        if report.plan is not None and report.plan.steps:
            lines = []
            plan_citations = []
            for step in report.plan.steps:
                token = cite("plan", step.step_id, step.action)
                plan_citations.append(token)
                lines.append(f"{token.token} {step.action}. {step.purpose}")
            sections.append(
                PromptSection(
                    heading="Recommended investigation",
                    lines=(report.plan.objective, *lines),
                    citations=tuple(plan_citations),
                )
            )

        if report.design is not None and report.design.affected_region:
            sections.append(
                PromptSection(
                    heading="Affected design region",
                    lines=tuple(
                        f"{n.name} ({n.kind})" for n in report.design.affected_region
                    ),
                    citations=tuple(
                        cite("design", n.node_id, n.name)
                        for n in report.design.affected_region
                    ),
                )
            )

        if report.history is not None:
            lines = [
                (
                    f"This signature has been seen {report.history.times_seen} time(s) before."
                    if report.history.seen_before
                    else "This failure signature is new."
                )
            ]
            history_citations = []
            for similar in report.history.similar[:3]:
                token = cite("history", similar.regression_id, similar.root_cause)
                history_citations.append(token)
                lines.append(
                    f"{token.token} {similar.regression_id} at {similar.score:.0%} "
                    f"similarity: {similar.root_cause}"
                )
            sections.append(
                PromptSection(
                    heading="Regression history",
                    lines=tuple(lines),
                    citations=tuple(history_citations),
                )
            )

        if report.learning is not None and report.learning.hints:
            sections.append(
                PromptSection(
                    heading="What prior investigations suggest",
                    lines=tuple(h.statement for h in report.learning.hints),
                    citations=tuple(
                        cite("learning", h.artifact_id, h.statement)
                        for h in report.learning.hints
                    ),
                )
            )

        return sections

    @staticmethod
    def _answer_sections(answer: Answer, cite) -> list[PromptSection]:
        """Sections from a conversation answer: the structured object to restate."""
        sections = [
            PromptSection(
                heading="Question asked",
                lines=(answer.question, f"Answer: {answer.summary}"),
            )
        ]
        for part in answer.sections:
            sections.append(
                PromptSection(
                    heading=part.heading,
                    lines=tuple(part.statements),
                    citations=tuple(
                        cite(r.kind.value, r.ref_id, r.label) for r in part.references
                    ),
                )
            )
        for reference in answer.references:
            cite(reference.kind.value, reference.ref_id, reference.label)
        if answer.limitations:
            sections.append(
                PromptSection(
                    heading="What could not be established",
                    lines=tuple(answer.limitations),
                )
            )
        return sections


# --- The built-in templates --------------------------------------------------

EXECUTIVE_SUMMARY = PromptTemplate(
    template_id="executive-summary",
    style=RenderStyle.EXECUTIVE,
    task=(
        "Write three to five sentences for an engineering manager: what failed, how "
        "confident the platform is, who most likely owns it, and what happens next. "
        "No jargon that a manager would not use."
    ),
)

ENGINEER_SUMMARY = PromptTemplate(
    template_id="engineer-summary",
    style=RenderStyle.ENGINEER,
    task=(
        "Write a short brief for the DV engineer who will debug this: the failure, the "
        "leading explanation and its competition, and the first thing to look at. Cite "
        "the artifacts you rely on."
    ),
)

REGRESSION_DIGEST = PromptTemplate(
    template_id="regression-digest",
    style=RenderStyle.DIGEST,
    task=(
        "Write a two to three sentence digest line suitable for a daily regression "
        "report: the classification, whether it is a recurrence, and the single most "
        "useful next action."
    ),
)

HYPOTHESIS_EXPLANATION = PromptTemplate(
    template_id="hypothesis-explanation",
    style=RenderStyle.EXPLANATION,
    task=(
        "Explain why the leading hypothesis is leading, walking through the signals "
        "that moved its confidence and naming what would change the picture."
    ),
)

PLAN_EXPLANATION = PromptTemplate(
    template_id="plan-explanation",
    style=RenderStyle.EXPLANATION,
    task=(
        "Explain the recommended investigation as a sequence: what to do first, what "
        "each step would tell you, and how the branch points work."
    ),
)

DESIGN_WALKTHROUGH = PromptTemplate(
    template_id="design-walkthrough",
    style=RenderStyle.WALKTHROUGH,
    task=(
        "Walk through where this failure sits in the design: the affected region, how "
        "those elements relate, and which verification components observe them."
    ),
)

CONVERSATION_ANSWER = PromptTemplate(
    template_id="conversation-answer",
    style=RenderStyle.ENGINEER,
    task=(
        "Restate the structured answer above as two to four sentences of prose, "
        "preserving every citation. Add no information that is not already present."
    ),
)

BUILT_IN_TEMPLATES = {
    t.template_id: t
    for t in (
        EXECUTIVE_SUMMARY,
        ENGINEER_SUMMARY,
        REGRESSION_DIGEST,
        HYPOTHESIS_EXPLANATION,
        PLAN_EXPLANATION,
        DESIGN_WALKTHROUGH,
        CONVERSATION_ANSWER,
    )
}
