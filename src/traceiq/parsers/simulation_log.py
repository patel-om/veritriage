"""Simulation log parser: UVM, Questa, VCS, Xcelium, and generic formats.

v1 parses line-oriented messages only; multi-line constructs (e.g. Questa's
"Time:/Scope:" continuation lines after an assertion error) are a documented
limitation and land in a future version.
"""

from __future__ import annotations

import re
from pathlib import Path

from traceiq.models import (
    AssertionFailure,
    Failure,
    LogSummary,
    Severity,
    SimulationEvent,
)
from traceiq.parsers.base import Parser, ParseResult
from traceiq.parsers.registry import register

# --- Message formats -------------------------------------------------------
# UVM_ERROR /path/tb.sv(102) @ 55000: uvm_test_top.env.scb [SCBD] message
_UVM_RE = re.compile(
    r"^(?:#\s*)?UVM_(?P<sev>INFO|WARNING|ERROR|FATAL)"
    r"(?:\s+(?P<file>[^\s(]+)\((?P<fline>\d+)\))?"
    r"\s+@\s*(?P<time>[\d.]+(?:\s*[a-zA-Z]+)?)\s*:"
    r"\s*(?P<comp>\S+)"
    r"(?:\s+\[(?P<id>[^\]]+)\])?"
    r"\s*(?P<msg>.*)$"
)

# Error-[SE] Syntax error   (Synopsys VCS)
_VCS_RE = re.compile(r"^(?P<sev>Error|Warning|Fatal)-\[(?P<code>[^\]]+)\]\s*(?P<msg>.*)$")

# xmsim: *E,ASRTST (./tb.sv,55): message   (Cadence Xcelium)
_XCELIUM_RE = re.compile(
    r"^(?P<tool>\w+):\s*\*(?P<sev>[EWFN]),(?P<code>\w+)"
    r"(?:\s*\((?P<file>[^,()]+),(?P<fline>\d+)\))?:?\s*(?P<msg>.*)$"
)

# ** Error: (vsim-3601) message   (Siemens Questa / ModelSim, optional '# ' transcript prefix)
_QUESTA_RE = re.compile(
    r"^(?:#\s*)?\*\*\s*(?P<sev>Error|Fatal|Warning|Note)"
    r"(?:\s*\([^)]*\))?:\s*"
    r"(?:\((?P<code>v\w+-\d+)\)\s*)?"
    r"(?P<msg>.*)$"
)

# Error: message   (tool-agnostic fallback)
_GENERIC_RE = re.compile(
    r"^\s*(?:#\s*)?(?P<sev>ERROR|Error|FATAL|Fatal|WARNING|Warning)\b\s*[:\-]\s*(?P<msg>.+)$"
)

# UVM end-of-run report tally, e.g. "UVM_ERROR :    2" - a count, not an event.
_UVM_COUNT_RE = re.compile(r"^\s*(?:#\s*)?UVM_(INFO|WARNING|ERROR|FATAL)\s*:\s*\d+\s*$")

# --- Metadata --------------------------------------------------------------
_TEST_NAME_RES = (
    re.compile(r"Running test\s+(?P<name>[\w.:]+)"),
    re.compile(r"\+UVM_TESTNAME=(?P<name>[\w.:]+)"),
)
_SIMULATOR_MARKERS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"Chronologic|Synopsys VCS|\bVCS\b"), "Synopsys VCS"),
    (re.compile(r"Questa|ModelSim|\bvsim\b"), "Siemens Questa"),
    (re.compile(r"Xcelium|xmsim|xrun|Cadence"), "Cadence Xcelium"),
)

_ASSERTION_HINT_RE = re.compile(r"\bassert(?:ion)?\b|\boffending\b", re.IGNORECASE)
_ASSERTION_NAME_RE = re.compile(r"[Aa]ssertion\s+'?(?P<name>[\w$./\[\]:]+)'?")
_ASSERTION_CODES = frozenset({"ASRTST", "ASSERT"})

_SEVERITY_BY_LETTER = {"E": Severity.ERROR, "W": Severity.WARNING, "F": Severity.FATAL, "N": Severity.INFO}
_SEVERITY_BY_WORD = {
    "info": Severity.INFO,
    "note": Severity.INFO,
    "warning": Severity.WARNING,
    "error": Severity.ERROR,
    "fatal": Severity.FATAL,
}


@register
class SimulationLogParser(Parser):
    """Parses a simulation run log into normalized events and failures."""

    # Claim only *.log so future artifact parsers (coverage.txt, ...) can claim
    # their own files; anything unclaimed still falls back to this parser.
    name = "simulation_log"
    file_patterns = ("*.log",)

    def parse(self, path: Path) -> ParseResult:
        """Parse the log at ``path``. Undecodable bytes are replaced, not fatal."""
        text = path.read_text(encoding="utf-8", errors="replace")

        events: list[SimulationEvent] = []
        failures: list[Failure | AssertionFailure] = []
        counts: dict[Severity, int] = {}
        test_name: str | None = None
        simulator: str | None = None
        last_sim_time: str | None = None
        total_lines = 0

        for line_number, raw_line in enumerate(text.splitlines(), start=1):
            total_lines = line_number
            line = raw_line.rstrip()
            if not line or _UVM_COUNT_RE.match(line):
                continue

            if simulator is None:
                simulator = self._detect_simulator(line)
            if test_name is None:
                test_name = self._detect_test_name(line)

            event = self._parse_line(line, raw_line, line_number)
            if event is None:
                continue

            events.append(event)
            counts[event.severity] = counts.get(event.severity, 0) + 1
            if event.sim_time is not None:
                last_sim_time = event.sim_time
            if event.severity.is_failure:
                failures.append(self._to_failure(event))

        summary = LogSummary(
            total_lines=total_lines,
            counts=counts,
            test_name=test_name,
            simulator=simulator,
            last_sim_time=last_sim_time,
        )
        return ParseResult(
            parser_name=self.name,
            source_path=str(path),
            events=events,
            failures=failures,
            summary=summary,
        )

    # --- Line-level parsing ------------------------------------------------

    def _parse_line(self, line: str, raw_line: str, line_number: int) -> SimulationEvent | None:
        """Match one line against the known formats; None if it is not a message."""
        m = _UVM_RE.match(line)
        if m:
            return SimulationEvent(
                severity=_SEVERITY_BY_WORD[m["sev"].lower()],
                message=m["msg"].strip(),
                line_number=line_number,
                raw_line=raw_line,
                sim_time=m["time"].strip(),
                component=m["comp"],
                message_id=m["id"],
                source_file=m["file"],
                source_line=int(m["fline"]) if m["fline"] else None,
            )

        m = _VCS_RE.match(line)
        if m:
            return SimulationEvent(
                severity=_SEVERITY_BY_WORD[m["sev"].lower()],
                message=m["msg"].strip(),
                line_number=line_number,
                raw_line=raw_line,
                message_id=m["code"],
            )

        m = _XCELIUM_RE.match(line)
        if m:
            return SimulationEvent(
                severity=_SEVERITY_BY_LETTER[m["sev"]],
                message=m["msg"].strip(),
                line_number=line_number,
                raw_line=raw_line,
                message_id=m["code"],
                source_file=m["file"],
                source_line=int(m["fline"]) if m["fline"] else None,
            )

        m = _QUESTA_RE.match(line)
        if m:
            return SimulationEvent(
                severity=_SEVERITY_BY_WORD[m["sev"].lower()],
                message=m["msg"].strip(),
                line_number=line_number,
                raw_line=raw_line,
                message_id=m["code"],
            )

        m = _GENERIC_RE.match(line)
        if m:
            return SimulationEvent(
                severity=_SEVERITY_BY_WORD[m["sev"].lower()],
                message=m["msg"].strip(),
                line_number=line_number,
                raw_line=raw_line,
            )

        return None

    # --- Failure extraction ------------------------------------------------

    def _to_failure(self, event: SimulationEvent) -> Failure | AssertionFailure:
        """Wrap a failing event; promote to AssertionFailure when it looks like one."""
        is_assertion = bool(_ASSERTION_HINT_RE.search(event.message)) or (
            event.message_id is not None and event.message_id.upper() in _ASSERTION_CODES
        )
        if is_assertion:
            name_match = _ASSERTION_NAME_RE.search(event.message)
            assertion_path = name_match["name"] if name_match else None
            if assertion_path and assertion_path.lower() in ("failed", "error"):
                assertion_path = None
            return AssertionFailure(
                description=f"Assertion failed: {event.message}",
                event=event,
                assertion_path=assertion_path or event.component,
            )
        return Failure(
            description=f"{event.severity.value.upper()}: {event.message}",
            event=event,
        )

    # --- Metadata detection ------------------------------------------------

    @staticmethod
    def _detect_simulator(line: str) -> str | None:
        for pattern, name in _SIMULATOR_MARKERS:
            if pattern.search(line):
                return name
        return None

    @staticmethod
    def _detect_test_name(line: str) -> str | None:
        for pattern in _TEST_NAME_RES:
            m = pattern.search(line)
            if m:
                # UVM prints "Running test <name>..." - drop the ellipsis.
                return m["name"].rstrip(".")
        return None
