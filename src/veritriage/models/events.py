"""Normalized simulation events extracted from raw log lines."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class Severity(str, Enum):
    """Severity of a simulation message, normalized across simulators."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    FATAL = "fatal"

    @property
    def is_failure(self) -> bool:
        """True for severities that indicate a failing run."""
        return self in (Severity.ERROR, Severity.FATAL)


class SimulationEvent(BaseModel):
    """One normalized message from a simulation log.

    A single event corresponds to a single source line in v1. Parsers map
    simulator-specific formats (UVM, Questa, VCS, Xcelium, generic) onto
    this common shape so rules and reports never need to know which tool
    produced the log.
    """

    severity: Severity
    message: str = Field(description="Message text with severity prefix and metadata stripped.")
    line_number: int = Field(ge=1, description="1-based line number in the source log.")
    raw_line: str = Field(description="The original log line, verbatim.")
    sim_time: str | None = Field(
        default=None,
        description="Simulation time as reported by the tool (units vary), e.g. '105000'.",
    )
    component: str | None = Field(
        default=None,
        description="Hierarchical reporter path, e.g. 'uvm_test_top.env.scoreboard'.",
    )
    message_id: str | None = Field(
        default=None, description="Tool message id, e.g. UVM id 'SCBD' or Xcelium code 'ASRTST'."
    )
    source_file: str | None = Field(
        default=None, description="Source file reference embedded in the message, if any."
    )
    source_line: int | None = Field(
        default=None, description="Line within `source_file`, if the log reported one."
    )
