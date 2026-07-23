"""Waveform adapter registry: pluggable format discovery.

Same shape as the parser and knowledge-pack registries. A new simulator is one
``@register_adapter`` decorated class; discovery, dispatch, and the ``waveform``
CLI listing all flow through this table with no other change.
"""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path
from typing import TypeVar

from veritriage.waveform.adapters.base import WaveformAdapter

_A = TypeVar("_A", bound=type[WaveformAdapter])

_REGISTRY: dict[str, type[WaveformAdapter]] = {}


def register_adapter(adapter_cls: _A) -> _A:
    """Class decorator adding a waveform adapter to the global registry.

    Raises:
        ValueError: If another adapter already registered the same name.
    """
    existing = _REGISTRY.get(adapter_cls.name)
    if existing is not None and existing is not adapter_cls:
        raise ValueError(
            f"Waveform adapter name {adapter_cls.name!r} is already registered by {existing!r}"
        )
    _REGISTRY[adapter_cls.name] = adapter_cls
    return adapter_cls


def unregister_adapter(name: str) -> None:
    """Remove an adapter (used by tests to clean up throwaway adapters)."""
    _REGISTRY.pop(name, None)


def available_adapters() -> dict[str, type[WaveformAdapter]]:
    """All registered adapters, keyed by name (built-ins ensured loaded)."""
    _ensure_builtin_adapters()
    return dict(_REGISTRY)


def all_patterns() -> tuple[str, ...]:
    """Every file pattern any registered adapter claims, de-duplicated."""
    _ensure_builtin_adapters()
    seen: dict[str, None] = {}
    for adapter_cls in _REGISTRY.values():
        for pattern in adapter_cls.file_patterns:
            seen.setdefault(pattern, None)
    return tuple(seen)


def _pattern_specificity(pattern: str) -> int:
    """Rank a glob: exact names beat narrow globs beat catch-alls."""
    if "*" not in pattern and "?" not in pattern:
        return 1000 + len(pattern)
    return len(pattern.replace("*", "").replace("?", ""))


def find_adapter(path: Path) -> WaveformAdapter | None:
    """The registered adapter whose pattern most specifically claims ``path``.

    Returns None when nothing claims it, so the caller can decline the file.
    """
    _ensure_builtin_adapters()
    best: tuple[int, type[WaveformAdapter]] | None = None
    for adapter_cls in _REGISTRY.values():
        if not adapter_cls.can_handle(path):
            continue
        score = max(
            (_pattern_specificity(p) for p in adapter_cls.file_patterns if fnmatch(path.name, p)),
            default=0,
        )
        if best is None or score > best[0]:
            best = (score, adapter_cls)
    return best[1]() if best is not None else None


def _ensure_builtin_adapters() -> None:
    """Import built-in adapter modules so their decorators run."""
    from veritriage.waveform import adapters  # noqa: F401  (import for side effect)
