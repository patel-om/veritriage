"""Built-in classification rules shipped with TraceIQ v1.

Confidence values are deliberately coarse and ordered so that more specific
diagnoses outrank generic ones when several rules fire:

    compile (90) ≥ assertion (90) > timeout (85) > testbench (80) > fatal (70)
"""

from __future__ import annotations

import re

from traceiq.models import (
    AssertionFailure,
    ClassificationResult,
    FailureCategory,
    Recommendation,
    SimulationEvent,
)
from traceiq.parsers.base import ParseResult
from traceiq.rules.base import Rule


def _matching(events: list[SimulationEvent], pattern: re.Pattern[str]) -> list[SimulationEvent]:
    """Events whose message or raw line matches ``pattern``."""
    return [e for e in events if pattern.search(e.message) or pattern.search(e.raw_line)]


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

    def evaluate(self, parse_result: ParseResult) -> ClassificationResult | None:
        failing = parse_result.failing_events
        matched = _matching(failing, self._PATTERN)
        matched += [
            e for e in failing
            if e not in matched and e.message_id is not None and e.message_id in self._CODES
        ]
        if not matched:
            return None
        first = matched[0]
        where = (
            f" at {first.source_file}:{first.source_line}"
            if first.source_file and first.source_line
            else ""
        )
        return self._result(
            confidence=90,
            summary="Compile/elaboration failure - the design never simulated",
            events=matched,
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
    """An SVA/checker assertion fired - a protocol or invariant was violated."""

    name = "assertion-failure"
    category = FailureCategory.ASSERTION_FAILURE

    def evaluate(self, parse_result: ParseResult) -> ClassificationResult | None:
        assertion_failures = [f for f in parse_result.failures if isinstance(f, AssertionFailure)]
        if not assertion_failures:
            return None
        first = assertion_failures[0]
        scope = first.assertion_path or first.event.component or "the failing checker"
        when = f" around time {first.event.sim_time}" if first.event.sim_time else ""
        return self._result(
            confidence=90,
            summary="Assertion failure - a design invariant or protocol check was violated",
            events=[f.event for f in assertion_failures],
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

    def evaluate(self, parse_result: ParseResult) -> ClassificationResult | None:
        matched = _matching(parse_result.failing_events, self._PATTERN)
        if not matched:
            return None
        return self._result(
            confidence=85,
            summary="Timeout - the test hung and was killed by a watchdog/phase timeout",
            events=matched,
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
    """Scoreboard/comparison mismatch - likely a checking-environment issue."""

    name = "testbench-failure"
    category = FailureCategory.TESTBENCH_FAILURE

    _PATTERN = re.compile(
        r"scoreboard|mismatch|compare (?:fail|error)|miscompare|"
        r"expected\b.*\b(?:got|actual|received)|prediction",
        re.IGNORECASE,
    )

    def evaluate(self, parse_result: ParseResult) -> ClassificationResult | None:
        matched = _matching(parse_result.failing_events, self._PATTERN)
        if not matched:
            return None
        return self._result(
            confidence=80,
            summary="Likely testbench issue - scoreboard or comparison mismatch",
            events=matched,
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

    def evaluate(self, parse_result: ParseResult) -> ClassificationResult | None:
        fatal = [e for e in parse_result.events if e.severity.value == "fatal"]
        if not fatal:
            return None
        return self._result(
            confidence=70,
            summary="Fatal error - the simulation aborted",
            events=fatal,
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
