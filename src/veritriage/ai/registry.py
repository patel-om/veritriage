"""The LLM provider table: one registry for every vendor.

Deliberately named apart from ``agents.providers.register_provider`` (M12),
which registers *reasoning* providers. That seam stays frozen and is now a
consumer of this one through ``ai.adapters``, so a vendor is registered here
exactly once and both agent narration and every renderer gain it.

Adding OpenAI, Anthropic, Google, a local model, an MCP-hosted provider, or an
enterprise gateway is one class implementing :class:`LLMProvider` plus one
``@register_llm_provider`` call.
"""

from __future__ import annotations

from typing import TypeVar

from veritriage.ai.provider import LLMProvider

_P = TypeVar("_P", bound=type)

_REGISTRY: dict[str, type] = {}

#: The provider used when none is named. Generating nothing is the default
#: posture: the platform is complete without prose.
DEFAULT_PROVIDER = "null"


def register_llm_provider(provider_cls: _P) -> _P:
    """Class decorator adding a generative provider to the registry.

    Raises:
        ValueError: If another provider already registered the same name.
    """
    existing = _REGISTRY.get(provider_cls.name)
    if existing is not None and existing is not provider_cls:
        raise ValueError(
            f"LLM provider name {provider_cls.name!r} is already registered by {existing!r}"
        )
    _REGISTRY[provider_cls.name] = provider_cls
    return provider_cls


def unregister_llm_provider(name: str) -> None:
    """Remove a provider (used by tests to clean up throwaway providers)."""
    _REGISTRY.pop(name, None)


def available_llm_providers() -> dict[str, type]:
    """All registered generative providers, keyed by name."""
    return dict(_REGISTRY)


def get_llm_provider(name: str | None = None) -> LLMProvider:
    """Instantiate a registered provider, defaulting to the null provider.

    Raises:
        KeyError: If a name is given and nothing is registered under it.
    """
    wanted = name or DEFAULT_PROVIDER
    try:
        return _REGISTRY[wanted]()
    except KeyError:
        known = ", ".join(sorted(_REGISTRY)) or "<none>"
        raise KeyError(f"Unknown LLM provider {wanted!r}. Registered: {known}") from None
