"""The M12 bridge: one vendor registry serves both seams.

`agents.ReasoningProvider` (M12) is frozen and stays exactly as it is. It is
agent-shaped, so it cannot carry summaries or design walkthroughs, but it is
also the documented seam for narrating an agent's position.

Rather than build a second vendor registry, this adapter satisfies the M12
interface by delegating to an :class:`LLMProvider`. Registering Anthropic once
in ``ai.registry`` therefore gives both agent narration and every renderer, and
no frozen contract moves.

The M12 laws still hold through the adapter: it may only populate ``narrative``,
it receives a deep-copied request it cannot mutate anything through, and a
failure costs prose and nothing else.
"""

from __future__ import annotations

from veritriage.agents.providers import ProviderRequest, ProviderResponse
from veritriage.ai.prompt import PromptBuilder, PromptContext, PromptTemplate
from veritriage.ai.service import AIService
from veritriage.models import Citation, PromptSection, RenderStyle

AGENT_NARRATION = PromptTemplate(
    template_id="agent-narration",
    style=RenderStyle.EXPLANATION,
    task=(
        "Restate this specialist's position in two or three sentences for a DV "
        "engineer: what it concluded, what it observed, and what it could not "
        "determine. Add nothing it did not say."
    ),
)


class LlmReasoningProvider:
    """An M12 ``ReasoningProvider`` backed by an M17 ``LLMProvider``.

    Satisfies the frozen M12 Protocol (``name`` plus ``elaborate``) while the
    actual vendor lives in the one registry that every other renderer uses.
    """

    name = "llm"

    def __init__(self, service: AIService | None = None) -> None:
        self._service = service or AIService()

    def elaborate(self, request: ProviderRequest) -> ProviderResponse | None:
        """Narrate one agent result. Returns None when nothing was generated."""
        context = PromptContext(extra_sections=_sections(request))
        view = self._service.render(AGENT_NARRATION, context)
        if view.is_empty:
            return None
        return ProviderResponse(narrative=view.prose)


def _sections(request: ProviderRequest) -> tuple[PromptSection, ...]:
    """Turn an M12 agent request into prompt sections, citations included."""
    citations = tuple(
        Citation(kind="evidence", ref_id=node_id, label="cited by this specialist")
        for node_id in request.evidence_ids[:12]
    ) + tuple(
        Citation(kind="knowledge", ref_id=item_id, label="knowledge consulted")
        for item_id in request.knowledge_ids[:8]
    )
    sections = [
        PromptSection(
            heading=f"The {request.domain} specialist's position",
            lines=tuple(
                f"{h.category.value} at {h.confidence:.0%}: {h.statement}"
                for h in request.hypotheses
            ),
            citations=citations,
        )
    ]
    if request.observations:
        sections.append(
            PromptSection(
                heading="What it observed",
                lines=tuple(o.statement for o in request.observations),
            )
        )
    if request.limitations:
        sections.append(
            PromptSection(
                heading="What it could not determine",
                lines=tuple(request.limitations),
            )
        )
    return tuple(sections)
