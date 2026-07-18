"""End-to-end analysis pipeline: parse → classify → report model.

This is the library-level entry point; the CLI is a thin wrapper around it.
"""

from __future__ import annotations

from pathlib import Path

from traceiq.models import AnalysisReport, Severity
from traceiq.parsers import find_parser, get_parser
from traceiq.rules import RuleEngine


def analyze(log_path: Path, parser_name: str | None = None, engine: RuleEngine | None = None) -> AnalysisReport:
    """Analyze one artifact and return the full report model.

    Args:
        log_path: Path to the artifact (a simulation log in v1).
        parser_name: Force a specific registered parser; auto-detected if None.
        engine: Rule engine to use; the default built-in rule set if None.

    Raises:
        FileNotFoundError: If ``log_path`` does not exist.
    """
    if not log_path.is_file():
        raise FileNotFoundError(f"No such log file: {log_path}")

    parser = get_parser(parser_name) if parser_name else find_parser(log_path)
    parse_result = parser.parse(log_path)

    engine = engine or RuleEngine()
    primary, alternatives = engine.classify(parse_result)

    # Keep the report focused: warnings and above. INFO stays available to
    # rules via ParseResult but would bloat analysis.json on chatty logs.
    notable_events = [e for e in parse_result.events if e.severity != Severity.INFO]

    return AnalysisReport(
        input_file=str(log_path),
        parser_name=parse_result.parser_name,
        summary=parse_result.summary,
        classification=primary,
        alternatives=alternatives,
        failures=parse_result.failures,
        events=notable_events,
    )
