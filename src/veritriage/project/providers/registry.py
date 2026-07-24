"""Project provider registry: pluggable project-source discovery.

Same shape as the parser, knowledge-pack, waveform-adapter, and context-provider
registries. A new project source is one ``@register_project_provider`` decorated
class; discovery, collection, and the ``project`` CLI listing all flow through
this table with no other change.
"""

from __future__ import annotations

from pathlib import Path
from typing import TypeVar

from veritriage.project.model import ProjectModel
from veritriage.project.providers.base import ProjectProvider

_P = TypeVar("_P", bound=type[ProjectProvider])

_REGISTRY: dict[str, type[ProjectProvider]] = {}


def register_project_provider(provider_cls: _P) -> _P:
    """Class decorator adding a project provider to the global registry.

    Raises:
        ValueError: If another provider already registered the same name.
    """
    existing = _REGISTRY.get(provider_cls.name)
    if existing is not None and existing is not provider_cls:
        raise ValueError(
            f"Project provider name {provider_cls.name!r} is already registered by {existing!r}"
        )
    _REGISTRY[provider_cls.name] = provider_cls
    return provider_cls


def unregister_project_provider(name: str) -> None:
    """Remove a provider (used by tests to clean up throwaway providers)."""
    _REGISTRY.pop(name, None)


def available_project_providers() -> dict[str, type[ProjectProvider]]:
    """All registered providers, keyed by name (built-ins ensured loaded)."""
    _ensure_builtin_providers()
    return dict(_REGISTRY)


def collect_project(root: Path) -> ProjectModel:
    """Merge a partial model from every provider that declares itself available.

    Providers run in sorted-name order for determinism. A provider that raises
    is skipped (project understanding is auxiliary, never fatal to an analysis);
    a root where nothing is available yields an empty model.
    """
    _ensure_builtin_providers()
    merged = ProjectModel(source_root=str(root))
    for name in sorted(_REGISTRY):
        provider_cls = _REGISTRY[name]
        try:
            if not provider_cls.available(root):
                continue
            merged = merged.merge(provider_cls().collect(root))
        except Exception:  # noqa: BLE001 - project intelligence is auxiliary, never fatal
            continue
    return merged


def _ensure_builtin_providers() -> None:
    """Import the built-in provider modules so their decorators run."""
    from veritriage.project import providers  # noqa: F401  (import for side effect)
