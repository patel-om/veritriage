"""End-to-end analysis pipeline: parse artifacts, build the graph, classify.

This is the library-level entry point; the CLI is a thin wrapper around it.

Flow: each artifact is parsed by its matching parser, every parser emits a
GraphFragment, the GraphBuilder merges and correlates them into the Evidence
Graph, and the rule engine classifies from the graph. The graph, not any raw
file, is what every downstream consumer (report, AI layer) works from.
"""

from __future__ import annotations

from pathlib import Path
from typing import NamedTuple, Sequence

from veritriage.graph.builder import GraphBuilder
from veritriage.graph.graph import EvidenceGraph
from veritriage.knowledge import KnowledgeEngine, knowledge_reasoning_rules
from veritriage.models import AnalysisReport, LogSummary, Severity
from veritriage.parsers import find_parser, get_parser
from veritriage.parsers.base import ParseResult
from veritriage.reasoning import ReasoningEngine
from veritriage.reasoning.signals import default_reasoning_rules
from veritriage.rules import RuleEngine


class AnalysisOutcome(NamedTuple):
    """What one analysis run produces: the report and the full graph."""

    report: AnalysisReport
    graph: EvidenceGraph


def analyze(
    paths: Path | Sequence[Path],
    parser_name: str | None = None,
    engine: RuleEngine | None = None,
) -> AnalysisOutcome:
    """Analyze one or more artifacts and return the report plus the graph.

    Args:
        paths: Artifact paths (simulation log, compile log, coverage summary,
            test metadata). A single Path is accepted for convenience.
        parser_name: Force one registered parser for every artifact;
            auto-detected per file when None.
        engine: Rule engine to use; the default built-in rule set if None.

    Raises:
        FileNotFoundError: If any path does not exist.
    """
    artifact_paths = [paths] if isinstance(paths, Path) else list(paths)
    if not artifact_paths:
        raise ValueError("At least one artifact path is required")
    for path in artifact_paths:
        if not path.is_file():
            raise FileNotFoundError(f"No such artifact: {path}")

    results: list[ParseResult] = []
    builder = GraphBuilder()
    for path in artifact_paths:
        parser = get_parser(parser_name) if parser_name else find_parser(path)
        result = parser.parse(path)
        results.append(result)
        builder.add_fragment(parser.emit_evidence(result))
    graph = builder.build()

    engine = engine or RuleEngine()
    primary, alternatives = engine.classify(graph)

    # Knowledge runs before reasoning and feeds it through the standard rule
    # interface: matched patterns become ordinary evidence-cited signals. The
    # reasoning engine itself has no knowledge dependency.
    knowledge_engine = KnowledgeEngine()
    knowledge = knowledge_engine.analyze(graph)
    reasoning = ReasoningEngine(
        rules=[
            *default_reasoning_rules(),
            *knowledge_reasoning_rules(knowledge_engine.knowledge),
        ]
    ).reason(graph)

    # Keep the report focused: warnings and above. INFO stays available to
    # parsers but would bloat analysis.json on chatty logs.
    notable_events = [
        e for r in results for e in r.events if e.severity != Severity.INFO
    ]
    report = AnalysisReport(
        input_files=[str(p) for p in artifact_paths],
        parser_names=[r.parser_name for r in results],
        summary=_merge_summaries(results),
        graph_stats=graph.stats(),
        classification=primary,
        alternatives=alternatives,
        failures=[f for r in results for f in r.failures],
        events=notable_events,
        reasoning=reasoning,
        knowledge=None if knowledge.is_empty else knowledge,
    )
    return AnalysisOutcome(report=report, graph=graph)


def _merge_summaries(results: list[ParseResult]) -> LogSummary:
    """Combine per-artifact summaries into one run-level summary."""
    counts: dict[Severity, int] = {}
    total_lines = 0
    test_name = simulator = last_sim_time = None
    for result in results:
        total_lines += result.summary.total_lines
        for severity, count in result.summary.counts.items():
            counts[severity] = counts.get(severity, 0) + count
        test_name = test_name or result.summary.test_name
        simulator = simulator or result.summary.simulator
        last_sim_time = result.summary.last_sim_time or last_sim_time
    return LogSummary(
        total_lines=total_lines,
        counts=counts,
        test_name=test_name,
        simulator=simulator,
        last_sim_time=last_sim_time,
    )
