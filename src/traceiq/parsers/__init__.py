"""Parser layer: turn raw verification artifacts into normalized models.

New parsers plug in by subclassing :class:`~traceiq.parsers.base.Parser` and
decorating with :func:`~traceiq.parsers.registry.register` — no existing code
changes required.
"""

from traceiq.parsers.base import Parser, ParseResult
from traceiq.parsers.registry import available_parsers, find_parser, get_parser, register

# Importing a parser module registers it. Add new parser imports here (or
# expose an entry-point mechanism in a future version).
from traceiq.parsers.simulation_log import SimulationLogParser

__all__ = [
    "Parser",
    "ParseResult",
    "SimulationLogParser",
    "available_parsers",
    "find_parser",
    "get_parser",
    "register",
]
