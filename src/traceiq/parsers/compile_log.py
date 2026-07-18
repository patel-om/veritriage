"""Compile/elaboration log parser.

Compile logs share the message formats of simulation logs (VCS ``Error-[SE]``,
Questa ``** Error``, Xcelium ``*E`` codes), so this parser reuses the
simulation parser's line matching and only changes identity: its evidence is
tagged ``ArtifactType.COMPILE_LOG``, which lets the compile-failure rule fire
on artifact type rather than regex heuristics alone.
"""

from __future__ import annotations

from traceiq.graph.model import ArtifactType
from traceiq.parsers.registry import register
from traceiq.parsers.simulation_log import SimulationLogParser


@register
class CompileLogParser(SimulationLogParser):
    """Parses a compile/elaboration log into normalized evidence."""

    name = "compile_log"
    artifact_type = ArtifactType.COMPILE_LOG
    file_patterns = ("compile.log", "*compile*.log", "vlog.log", "vcs.log", "xmvlog.log", "elab*.log")
