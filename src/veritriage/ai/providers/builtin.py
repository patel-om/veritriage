"""The built-in providers. None calls an external API.

Four ship, and together they validate the architecture without a vendor
dependency:

* ``null`` is the default and generates nothing, because the platform is
  complete without prose.
* ``deterministic-echo`` assembles prose from the prompt's own sections, so an
  end-to-end rendering path can be pinned byte for byte in tests.
* ``mock`` returns scripted responses, including deliberately ungrounded ones,
  so grounding enforcement can be tested against a hostile provider.
* ``reference`` is what a vendor integration should be read against: correct
  citation behavior, honest capability declaration, and failure signalling that
  returns rather than raises.

A real vendor is one more class exactly like ``reference``, with ``_generate``
calling an API instead of assembling a string.
"""

from __future__ import annotations

from veritriage.ai.provider import BaseProvider
from veritriage.ai.registry import register_llm_provider
from veritriage.models import (
    GenerationRequest,
    GenerationResponse,
    ProviderCapabilities,
)


@register_llm_provider
class NullProvider(BaseProvider):
    """Generates nothing. The default, and the honest one."""

    name = "null"

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name=self.name,
            generates=False,
            deterministic=True,
            local=True,
            supports_citations=False,
            notes="No generation. Structured intelligence is returned unchanged.",
        )

    def _generate(self, request: GenerationRequest) -> GenerationResponse:
        return GenerationResponse(provider=self.name, text="")


@register_llm_provider
class DeterministicEchoProvider(BaseProvider):
    """Assembles prose from the prompt's own sections. No model involved.

    Every sentence it emits is a restatement of a line the prompt already
    contained, which makes it both a useful offline renderer and the strictest
    possible demonstration of the milestone's law: prose that adds nothing.
    """

    name = "deterministic-echo"

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name=self.name,
            generates=True,
            deterministic=True,
            local=True,
            notes="Restates prompt sections; adds no information whatsoever.",
        )

    def _generate(self, request: GenerationRequest) -> GenerationResponse:
        prompt = request.prompt
        parts: list[str] = []
        for section in prompt.sections:
            if not section.lines:
                continue
            body = " ".join(line.rstrip(".") + "." for line in section.lines[:4])
            parts.append(f"{section.heading}: {body}")
        text = " ".join(parts)[: request.max_output_chars]
        return GenerationResponse(provider=self.name, text=text)


@register_llm_provider
class MockProvider(BaseProvider):
    """Scripted responses for tests, including deliberately ungrounded ones.

    ``script`` is consumed in order; when it runs out the provider falls back to
    echoing the task. Setting ``invent_citations`` makes it cite artifacts it
    was never given, which is exactly what the grounding enforcement must catch.
    """

    name = "mock"

    #: Class-level so a test can script the provider the registry will construct.
    script: list[str] = []
    invent_citations: bool = False
    should_fail: bool = False

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name=self.name,
            generates=True,
            deterministic=True,
            local=True,
            notes="Test double. Never use outside tests.",
        )

    def _generate(self, request: GenerationRequest) -> GenerationResponse:
        if type(self).should_fail:
            raise RuntimeError("scripted provider failure")
        if type(self).script:
            text = type(self).script.pop(0)
        else:
            text = f"Mock rendering of {request.prompt.template_id}."
        if type(self).invent_citations:
            text += " Supported by [evidence:ev-invented] and [design:dn-fabricated]."
        return GenerationResponse(provider=self.name, text=text)

    @classmethod
    def reset(cls) -> None:
        cls.script = []
        cls.invent_citations = False
        cls.should_fail = False


@register_llm_provider
class ReferenceProvider(BaseProvider):
    """The reference implementation a vendor integration should be read against.

    Demonstrates the three things a real provider must get right: cite only the
    tokens it was handed, declare its capabilities honestly, and return its
    failures rather than raising them.
    """

    name = "reference"
    model = "reference-1"

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            name=self.name,
            version="1.0.0",
            generates=True,
            deterministic=True,
            local=True,
            max_prompt_chars=100_000,
            supports_citations=True,
            notes="Reference behaviour for vendor integrations. No network calls.",
        )

    def _generate(self, request: GenerationRequest) -> GenerationResponse:
        prompt = request.prompt
        if prompt.size > self.capabilities().max_prompt_chars:
            return GenerationResponse(
                provider=self.name,
                model=self.model,
                failed=True,
                error=(
                    f"Prompt of {prompt.size} characters exceeds this provider's "
                    f"budget of {self.capabilities().max_prompt_chars}."
                ),
            )

        headline = next(
            (s for s in prompt.sections if s.heading == "Verdict"), None
        )
        opening = (
            " ".join(headline.lines) if headline is not None else "This investigation completed."
        )
        # Cite only what the prompt authorized: the whole discipline in one line.
        cited = " ".join(c.token for c in prompt.citations[:4])
        closing = f" Supporting artifacts: {cited}." if cited else ""
        text = f"{opening}{closing}"
        return GenerationResponse(
            provider=self.name, model=self.model, text=text[: request.max_output_chars]
        )
