"""Parser layer: turn raw verification artifacts into normalized evidence.

New parsers plug in by subclassing :class:`~veritriage.parsers.base.Parser` and
decorating with :func:`~veritriage.parsers.registry.register`; no existing code
changes required. Every parser emits a
:class:`~veritriage.graph.builder.GraphFragment` of evidence nodes and edges via
``emit_evidence`` so all artifacts land in the Evidence Graph.
"""

from veritriage.parsers.base import Parser, ParseResult
from veritriage.parsers.registry import available_parsers, find_parser, get_parser, register

# Importing a parser module registers it. Add new parser imports here (or
# expose an entry-point mechanism in a future version).
from veritriage.parsers.simulation_log import SimulationLogParser
from veritriage.parsers.compile_log import CompileLogParser
from veritriage.parsers.coverage import CoverageParser
from veritriage.parsers.test_metadata import TestMetadataParser

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
