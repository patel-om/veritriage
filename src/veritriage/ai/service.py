"""AIService: select a provider, render a view, degrade gracefully.

The one place generation is invoked. It builds a prompt from structured
objects, hands it to the selected provider, enforces grounding on whatever comes
back, and returns a :class:`GeneratedView` carrying both the prose and its
provenance.

Every failure mode ends the same way: the structured object is unaffected and
the caller is told what happened. A provider that raises, hangs on nonsense,
invents citations, or is not installed at all costs prose and nothing else.
"""

from __future__ import annotations

from veritriage.ai import grounding
from veritriage.ai.prompt import (
    BUILT_IN_TEMPLATES,
    PromptBuilder,
    PromptContext,
    PromptTemplate,
)
from veritriage.ai.provider import LLMProvider
from veritriage.ai.registry import (
    DEFAULT_PROVIDER,
    available_llm_providers,
    get_llm_provider,
)
from veritriage.models import (
    GeneratedView,
    GenerationRequest,
    Prompt,
    ProviderStatus,
    RenderStyle,
)


class AIService:
    """Provider selection, capability discovery, and grounded rendering."""

    def __init__(self, provider: LLMProvider | str | None = None) -> None:
        if isinstance(provider, str) or provider is None:
            self._provider = get_llm_provider(provider)
        else:
            self._provider = provider

    @property
    def provider(self) -> LLMProvider:
        return self._provider

    @property
    def provider_name(self) -> str:
        return getattr(self._provider, "name", "unknown")

    # --- Discovery ----------------------------------------------------------

    def status(self) -> list[ProviderStatus]:
        """Every registered provider, its capabilities, and whether it is active."""
        found: list[ProviderStatus] = []
        for name in sorted(available_llm_providers()):
            try:
                capabilities = get_llm_provider(name).capabilities()
                found.append(
                    ProviderStatus(
                        name=name,
                        available=True,
                        active=name == self.provider_name,
                        capabilities=capabilities,
                    )
                )
            except Exception as exc:  # a broken provider must not hide the others
                found.append(
                    ProviderStatus(
                        name=name,
                        available=False,
                        active=name == self.provider_name,
                        error=f"{type(exc).__name__}: {exc}",
                    )
                )
        return found

    # --- Prompting ----------------------------------------------------------

    @staticmethod
    def build_prompt(template: PromptTemplate | str, context: PromptContext) -> Prompt:
        """Assemble the prompt without generating anything.

        Exposed so a caller can audit exactly what a provider would be asked
        before asking it. Pure function of the context.
        """
        resolved = (
            BUILT_IN_TEMPLATES[template] if isinstance(template, str) else template
        )
        return PromptBuilder(resolved).build(context)

    # --- Generation ---------------------------------------------------------

    def render(
        self,
        template: PromptTemplate | str,
        context: PromptContext,
        max_output_chars: int = 4_000,
    ) -> GeneratedView:
        """Build, generate, enforce grounding, and return prose plus provenance."""
        try:
            prompt = self.build_prompt(template, context)
        except Exception as exc:  # a prompt that cannot be built is not a crash
            return GeneratedView(
                style=RenderStyle.ENGINEER,
                provider=self.provider_name,
                limitations=[
                    f"The prompt could not be assembled ({type(exc).__name__}); the "
                    "structured intelligence is unaffected."
                ],
            )

        capabilities = self._capabilities()
        if capabilities is not None and not capabilities.generates:
            return GeneratedView(
                style=prompt.style,
                provider=self.provider_name,
                prompt_id=prompt.template_id,
                limitations=[
                    f"The {self.provider_name!r} provider does not generate text. "
                    "Structured intelligence is returned unchanged."
                ],
            )
        if capabilities is not None and prompt.size > capabilities.max_prompt_chars:
            return GeneratedView(
                style=prompt.style,
                provider=self.provider_name,
                prompt_id=prompt.template_id,
                limitations=[
                    f"The prompt is {prompt.size} characters, over this provider's "
                    f"budget of {capabilities.max_prompt_chars}. Nothing was generated."
                ],
            )

        try:
            response = self._provider.generate(
                GenerationRequest(prompt=prompt, max_output_chars=max_output_chars)
            )
        except Exception as exc:  # belt and braces: BaseProvider already catches
            return GeneratedView(
                style=prompt.style,
                provider=self.provider_name,
                prompt_id=prompt.template_id,
                limitations=[
                    f"Generation failed ({type(exc).__name__}); the structured "
                    "intelligence is unaffected."
                ],
            )

        if response.failed:
            return GeneratedView(
                style=prompt.style,
                provider=self.provider_name,
                prompt_id=prompt.template_id,
                limitations=[
                    f"Generation failed: {response.error or 'no reason given'}. The "
                    "structured intelligence is unaffected."
                ],
            )

        cleaned, used, stripped = grounding.enforce(response.text, prompt)
        limitations: list[str] = []
        if stripped:
            limitations.append(
                f"{len(stripped)} citation(s) the provider invented were removed: "
                f"{', '.join(stripped)}. Treat this provider's output with care."
            )
        return GeneratedView(
            style=prompt.style,
            prose=cleaned,
            provider=response.provider or self.provider_name,
            grounded=not stripped,
            citations=used,
            stripped_citations=stripped,
            prompt_id=prompt.template_id,
            limitations=limitations,
        )

    def _capabilities(self):
        try:
            return self._provider.capabilities()
        except Exception:
            return None


def default_service() -> AIService:
    """An AIService on the default (null) provider: generation off."""
    return AIService(DEFAULT_PROVIDER)
