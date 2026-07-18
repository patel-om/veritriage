"""Failure taxonomy and concrete failure records."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field

from traceiq.models.events import SimulationEvent


class FailureCategory(str, Enum):
    """Deterministic failure classes the rule engine can assign."""

    TIMEOUT = "timeout"
    ASSERTION_FAILURE = "assertion_failure"
    FATAL_ERROR = "fatal_error"
    COMPILE_FAILURE = "compile_failure"
    TESTBENCH_FAILURE = "testbench_failure"
    UNKNOWN_FAILURE = "unknown_failure"
    NO_FAILURE = "no_failure"

    @property
    def display_name(self) -> str:
        """Title-case label for reports, e.g. 'Assertion Failure'."""
        return self.value.replace("_", " ").title()


class Failure(BaseModel):
    """A concrete failing observation extracted by a parser.

    Failures are raw facts ("an ERROR occurred at this line"), not verdicts.
    Classifying *why* the run failed is the rule engine's job.
    """

    kind: Literal["failure", "assertion_failure"] = "failure"
    description: str = Field(description="One-line description of the failing observation.")
    event: SimulationEvent = Field(description="The event that constitutes this failure.")


class AssertionFailure(Failure):
    """A failure caused by an SVA/checker assertion firing."""

    kind: Literal["assertion_failure"] = "assertion_failure"  # type: ignore[assignment]
    assertion_path: str | None = Field(
        default=None, description="Hierarchical path or name of the failing assertion, if known."
    )
