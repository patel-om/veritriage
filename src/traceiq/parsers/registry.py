"""Parser registry: pluggable discovery without touching existing code."""

from __future__ import annotations

from fnmatch import fnmatch
from pathlib import Path
from typing import TypeVar

from traceiq.parsers.base import Parser

_P = TypeVar("_P", bound=type[Parser])

_REGISTRY: dict[str, type[Parser]] = {}


def register(parser_cls: _P) -> _P:
    """Class decorator adding a parser to the global registry.

    Raises:
        ValueError: If another parser already registered the same name.
    """
    existing = _REGISTRY.get(parser_cls.name)
    if existing is not None and existing is not parser_cls:
        raise ValueError(f"Parser name {parser_cls.name!r} is already registered by {existing!r}")
    _REGISTRY[parser_cls.name] = parser_cls
    return parser_cls


def available_parsers() -> dict[str, type[Parser]]:
    """All registered parsers, keyed by name."""
    return dict(_REGISTRY)


def get_parser(name: str) -> Parser:
    """Instantiate a parser by registered name.

    Raises:
        KeyError: If no parser with that name is registered.
    """
    try:
        return _REGISTRY[name]()
    except KeyError:
        known = ", ".join(sorted(_REGISTRY)) or "<none>"
        raise KeyError(f"Unknown parser {name!r}. Registered parsers: {known}") from None


def _pattern_specificity(pattern: str) -> int:
    """Rank a glob pattern: exact names beat narrow globs beat catch-alls."""
    if "*" not in pattern and "?" not in pattern:
        return 1000 + len(pattern)
    return len(pattern.replace("*", "").replace("?", ""))


def find_parser(path: Path) -> Parser:
    """Find the registered parser whose pattern most specifically claims ``path``.

    Specificity ranking lets 'compile.log' beat the simulation parser's
    generic '*.log' regardless of registration order. Falls back to the
    ``simulation_log`` parser when nothing claims the file.

    Raises:
        KeyError: If nothing claims the file and no fallback is registered.
    """
    best: tuple[int, type[Parser]] | None = None
    for parser_cls in _REGISTRY.values():
        if not parser_cls.can_parse(path):
            continue
        score = max(
            (_pattern_specificity(p) for p in parser_cls.file_patterns if fnmatch(path.name, p)),
            default=0,
        )
        if best is None or score > best[0]:
            best = (score, parser_cls)
    if best is not None:
        return best[1]()
    return get_parser("simulation_log")
