"""Context provider registry: pluggable engineering-system discovery.

Same shape as the parser, knowledge-pack, and waveform-adapter registries. A
new engineering system is one ``@register_provider`` decorated class;
discovery, collection, and the ``context`` CLI listing all flow through this
table with no other change.
"""

from __future__ import annotations

from pathlib import Path
from typing import TypeVar

from veritriage.engineering.model import EngineeringContext
from veritriage.engineering.providers.base import ContextProvider

_P = TypeVar("_P", bound=type[ContextProvider])

_REGISTRY: dict[str, type[ContextProvider]] = {}


def register_provider(provider_cls: _P) -> _P:
    """Class decorator adding a context provider to the global registry.

    Raises:
        ValueError: If another provider already registered the same name.
    """
    existing = _REGISTRY.get(provider_cls.name)
    if existing is not None and existing is not provider_cls:
        raise ValueError(
            f"Context provider name {provider_cls.name!r} is already registered by {existing!r}"
        )
    _REGISTRY[provider_cls.name] = provider_cls
    return provider_cls


def unregister_provider(name: str) -> None:
    """Remove a provider (used by tests to clean up throwaway providers)."""
    _REGISTRY.pop(name, None)


def available_providers() -> dict[str, type[ContextProvider]]:
    """All registered providers, keyed by name (built-ins ensured loaded)."""
    _ensure_builtin_providers()
    return dict(_REGISTRY)


def collect_context(root: Path, max_commits: int = 10) -> EngineeringContext:
    """Merge context from every provider that declares itself available.

    Providers run in sorted-name order for determinism. A provider that raises
    is skipped (context gathering must never break an analysis); a root where
    nothing is available yields an empty context.
    """
    _ensure_builtin_providers()
    merged = EngineeringContext()
    for name in sorted(_REGISTRY):
        provider_cls = _REGISTRY[name]
        try:
            if not provider_cls.available(root):
                continue
            merged = merged.merge(provider_cls().collect(root, max_commits=max_commits))
        except Exception:  # noqa: BLE001 - context is auxiliary, never fatal
            continue
    return merged


def _ensure_builtin_providers() -> None:
    """Import the built-in provider modules so their decorators run."""
    from veritriage.engineering import providers  # noqa: F401  (import for side effect)
