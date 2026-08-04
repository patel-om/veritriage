"""Renderers: the named views generation is actually useful for.

Each is a thin pairing of a built-in template with the structured objects it
restates. They exist so a caller asks for "an executive summary of this
investigation" rather than assembling a prompt by hand, and so the set of
things generation is used for is enumerable rather than open-ended.

Every renderer returns a :class:`GeneratedView`, which always carries the prose
*and* its provenance. The structured object it restates was never at risk.
"""

from __future__ import annotations

from veritriage.ai.prompt import (
    CONVERSATION_ANSWER,
    DESIGN_WALKTHROUGH,
    ENGINEER_SUMMARY,
    EXECUTIVE_SUMMARY,
    HYPOTHESIS_EXPLANATION,
    PLAN_EXPLANATION,
    REGRESSION_DIGEST,
    PromptContext,
)
from veritriage.ai.service import AIService
from veritriage.models import AnalysisReport, Answer, GeneratedView

#: Renderer name -> the template it uses. Enumerable on purpose: the set of
#: things generation is used for is a closed list, not an open invitation.
RENDERERS = {
    "executive-summary": EXECUTIVE_SUMMARY,
    "engineer-summary": ENGINEER_SUMMARY,
    "regression-digest": REGRESSION_DIGEST,
    "hypothesis-explanation": HYPOTHESIS_EXPLANATION,
    "plan-explanation": PLAN_EXPLANATION,
    "design-walkthrough": DESIGN_WALKTHROUGH,
    "conversation-answer": CONVERSATION_ANSWER,
}


def available_renderers() -> list[str]:
    """Every named view generation can produce."""
    return sorted(RENDERERS)


def render_report(
    service: AIService, report: AnalysisReport, renderer: str = "engineer-summary"
) -> GeneratedView:
    """Render one investigation in a named style.

    Raises:
        KeyError: If the renderer is not one of the named views.
    """
    if renderer not in RENDERERS:
        known = ", ".join(available_renderers())
        raise KeyError(f"Unknown renderer {renderer!r}. Available: {known}")
    return service.render(RENDERERS[renderer], PromptContext(report=report))


def render_answer(service: AIService, answer: Answer) -> GeneratedView:
    """Render a conversation answer as prose, preserving its citations.

    The conversation layer stays AI-free: it produced the structured answer,
    and this restates it. Drop the provider and the answer is unchanged.
    """
    return service.render(CONVERSATION_ANSWER, PromptContext(answer=answer))


def render_explanation(
    service: AIService, report: AnalysisReport, subject: str = "hypothesis"
) -> GeneratedView:
    """Explain one aspect of an investigation: hypothesis, plan, or design."""
    template = {
        "hypothesis": HYPOTHESIS_EXPLANATION,
        "plan": PLAN_EXPLANATION,
        "design": DESIGN_WALKTHROUGH,
    }.get(subject, HYPOTHESIS_EXPLANATION)
    return service.render(template, PromptContext(report=report))
