"""Built-in classification rules, evaluated over the Evidence Graph.

Confidence values are deliberately coarse and ordered so that more specific
diagnoses outrank generic ones when several rules fire:

    compile (90) >= assertion (90) > timeout (85) > testbench (80) > fatal (70)
"""

from __future__ import annotations

import re

from veritriage.graph.graph import EvidenceGraph
from veritriage.graph.model import ArtifactType, EvidenceNode
from veritriage.models import ClassificationResult, FailureCategory, Recommendation, Severity
from veritriage.rules.base import Rule


def _matching(nodes: list[EvidenceNode], pattern: re.Pattern[str]) -> list[EvidenceNode]:
    """Nodes whose description or raw line matches ``pattern``."""
    return [
        n
        for n in nodes
        if pattern.search(n.description) or (n.raw_line is not None and pattern.search(n.raw_line))
    ]


class CompileFailureRule(Rule):
    """The run never simulated: compilation or elaboration failed."""

    name = "compile-failure"
    category = FailureCategory.COMPILE_FAILURE

    _PATTERN = re.compile(
        r"syntax error|undeclared|not (?:been )?declared|cannot open|"
        r"compilation (?:error|failed|terminated)|elaborat\w* (?:error|failed)|"
        r"near ['\"]",
        re.IGNORECASE,
    )
    _CODES = frozenset({"SE", "IND", "MPD", "UD"})  # common VCS compile error codes

    def evaluate(self, graph: EvidenceGraph) -> ClassificationResult | None:
        failing = graph.failing()
        # Evidence from a dedicated compile log is authoritative; pattern and
        # message-code matching covers compile errors inside a mixed run log.
        matched = [n for n in failing if n.artifact_type == ArtifactType.COMPILE_LOG]
        matched += [n for n in _matching(failing, self._PATTERN) if n not in matched]
        matched += [
            n
            for n in failing
            if n not in matched and n.attributes.get("message_id") in self._CODES
        ]
        if not matched:
            return None
        first = matched[0]
        source_file = first.attributes.get("source_file")
        source_line = first.attributes.get("source_line")
        where = f" at {source_file}:{source_line}" if source_file and source_line else ""
        return self._result(
            confidence=90,
            summary="Compile/elaboration failure - the design never simulated",
            nodes=matched,
            recommendations=[
                Recommendation(
                    action=f"Fix the first compile error{where} and rebuild.",
                    rationale="Later errors are usually cascades of the first one.",
                    priority=1,
                ),
                Recommendation(
                    action="Re-run the regression after a clean compile.",
                    rationale="Runtime behavior cannot be assessed until the build succeeds.",
                    priority=2,
                ),
            ],
        )


class AssertionFailureRule(Rule):
    """An SVA/checker assertion fired: a protocol or invariant was violated."""

    name = "assertion-failure"
    category = FailureCategory.ASSERTION_FAILURE

    def evaluate(self, graph: EvidenceGraph) -> ClassificationResult | None:
        assertions = [n for n in graph.nodes_of_type(ArtifactType.ASSERTION) if n.is_failing]
        if not assertions:
            return None
        first = assertions[0]
        scope = first.module or "the failing checker"
        when = f" around time {first.sim_time}" if first.sim_time else ""
        return self._result(
            confidence=90,
            summary="Assertion failure - a design invariant or protocol check was violated",
            nodes=assertions,
            recommendations=[
                Recommendation(
                    action=f"Inspect the waveform{when} at scope {scope}.",
                    rationale="The first assertion violation pinpoints where behavior first diverged.",
                    priority=1,
                ),
                Recommendation(
                    action="Check the signals sampled by the assertion against the spec.",
                    rationale="Decide whether the DUT or the assertion/testbench encoding is wrong.",
                    priority=2,
                ),
            ],
        )


class TimeoutRule(Rule):
    """The test hung: a phase/watchdog timeout ended the run."""

    name = "timeout"
    category = FailureCategory.TIMEOUT

    _PATTERN = re.compile(r"time[- ]?out|watchdog|PH_TIMEOUT|TIMOUT", re.IGNORECASE)

    def evaluate(self, graph: EvidenceGraph) -> ClassificationResult | None:
        matched = _matching(graph.failing(), self._PATTERN)
        if not matched:
            return None
        return self._result(
            confidence=85,
            summary="Timeout - the test hung and was killed by a watchdog/phase timeout",
            nodes=matched,
            recommendations=[
                Recommendation(
                    action="Check for a raised objection that is never dropped, or a stalled handshake.",
                    rationale="UVM phase timeouts almost always mean forward progress stopped.",
                    priority=1,
                ),
                Recommendation(
                    action="Look at the last simulation activity before the timeout fired.",
                    rationale="The stall point is usually just before the final reported time.",
                    priority=2,
                ),
            ],
        )


class TestbenchFailureRule(Rule):
    """Scoreboard/comparison mismatch: likely a checking-environment issue."""

    name = "testbench-failure"
    category = FailureCategory.TESTBENCH_FAILURE

    _PATTERN = re.compile(
        r"scoreboard|mismatch|compare (?:fail|error)|miscompare|"
        r"expected\b.*\b(?:got|actual|received)|prediction",
        re.IGNORECASE,
    )

    def evaluate(self, graph: EvidenceGraph) -> ClassificationResult | None:
        matched = _matching(graph.failing(), self._PATTERN)
        if not matched:
            return None
        return self._result(
            confidence=80,
            summary="Likely testbench issue - scoreboard or comparison mismatch",
            nodes=matched,
            recommendations=[
                Recommendation(
                    action="Inspect the scoreboard prediction logic for the first mismatching transaction.",
                    rationale="Expected-vs-actual mismatches begin either in the DUT or in the predictor; check the predictor first when DUT outputs follow the protocol.",
                    priority=1,
                ),
                Recommendation(
                    action="Compare the first mismatching transaction against the specification.",
                    rationale="Determines whether the DUT or the reference model is wrong.",
                    priority=2,
                ),
            ],
        )


class FatalErrorRule(Rule):
    """A fatal message ended the run without a more specific diagnosis."""

    name = "fatal-error"
    category = FailureCategory.FATAL_ERROR

    def evaluate(self, graph: EvidenceGraph) -> ClassificationResult | None:
        fatal = graph.with_severity(Severity.FATAL)
        if not fatal:
            return None
        return self._result(
            confidence=70,
            summary="Fatal error - the simulation aborted",
            nodes=fatal,
            recommendations=[
                Recommendation(
                    action="Read the first fatal message and the errors immediately preceding it.",
                    rationale="Fatals are usually the terminal symptom of an earlier error.",
                    priority=1,
                ),
            ],
        )


def default_rules() -> list[Rule]:
    """The built-in rule set, in deterministic evaluation order."""
    return [
        CompileFailureRule(),
        AssertionFailureRule(),
        TimeoutRule(),
        TestbenchFailureRule(),
        FatalErrorRule(),
    ]
