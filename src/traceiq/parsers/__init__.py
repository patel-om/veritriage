"""Parser layer: turn raw verification artifacts into normalized evidence.

New parsers plug in by subclassing :class:`~traceiq.parsers.base.Parser` and
decorating with :func:`~traceiq.parsers.registry.register`; no existing code
changes required. Every parser emits a
:class:`~traceiq.graph.builder.GraphFragment` of evidence nodes and edges via
``emit_evidence`` so all artifacts land in the Evidence Graph.
"""

from traceiq.parsers.base import Parser, ParseResult
from traceiq.parsers.registry import available_parsers, find_parser, get_parser, register

# Importing a parser module registers it. Add new parser imports here (or
# expose an entry-point mechanism in a future version).
from traceiq.parsers.simulation_log import SimulationLogParser
from traceiq.parsers.compile_log import CompileLogParser
from traceiq.parsers.coverage import CoverageParser
from traceiq.parsers.test_metadata import TestMetadataParser

__all__ = [
    "CompileLogParser",
    "CoverageParser",
    "Parser",
    "ParseResult",
    "SimulationLogParser",
    "TestMetadataParser",
    "available_parsers",
    "find_parser",
    "get_parser",
    "register",
]
