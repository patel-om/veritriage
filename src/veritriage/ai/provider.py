"""The LLM provider boundary.

One interface, shaped like a **vendor** rather than like a use case: a frozen
prompt goes in, text comes out. That shape is what lets a single registration
serve agent narration, conversation rendering, summaries, and every renderer
added later.

What a provider is handed is exhaustively described by
:class:`GenerationRequest`: a frozen :class:`Prompt` built from cited platform
objects. It receives no path, no store, no service, no graph, and no report, so
"providers are read-only" holds by construction. A provider that wanted to
mutate platform state would have nothing to mutate it with.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from veritriage.models import (
    GenerationRequest,
    GenerationResponse,
    ProviderCapabilities,
)


@runtime_checkable
class LLMProvider(Protocol):
    """The seam every generative integration implements.

    Two methods. ``capabilities`` is declared rather than discovered, so a
    caller can degrade visibly instead of silently getting worse output;
    ``generate`` is the only place text is ever produced.
    """

    name: str

    def capabilities(self) -> ProviderCapabilities:
        """What this provider can do. Declared honestly, including what it cannot."""
        ...

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        """Render the prompt as prose. Must not raise: signal with ``failed``."""
        ...


class BaseProvider:
    """Convenience base: declares capabilities and never raises.

    Implementations may ignore this and satisfy the Protocol directly; it
    exists so a vendor integration gets the failure contract right by default.
    A provider that raises is caught by the service anyway, but a provider that
    *returns* its failure gives the caller a usable error message.
    """

    name: str = "base"
    model: str | None = None

    def capabilities(self) -> ProviderCapabilities:  # pragma: no cover - overridden
        return ProviderCapabilities(name=self.name)

    def generate(self, request: GenerationRequest) -> GenerationResponse:
        try:
            return self._generate(request)
        except Exception as exc:  # a provider failure costs prose and nothing else
            return GenerationResponse(
                provider=self.name,
                model=self.model,
                failed=True,
                error=f"{type(exc).__name__}: {exc}",
            )

    def _generate(self, request: GenerationRequest) -> GenerationResponse:
        raise NotImplementedError
