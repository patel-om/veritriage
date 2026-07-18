"""Parser registry: pluggable discovery without touching existing code."""

from __future__ import annotations

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


def find_parser(path: Path) -> Parser:
    """Find the first registered parser that claims ``path``.

    Falls back to the ``simulation_log`` parser when nothing claims the file,
    since v1 only handles simulation logs anyway.

    Raises:
        KeyError: If nothing claims the file and no fallback is registered.
    """
    for parser_cls in _REGISTRY.values():
        if parser_cls.can_parse(path):
            return parser_cls()
    return get_parser("simulation_log")
