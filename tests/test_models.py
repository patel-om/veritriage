"""Model-level tests: invariants the rest of the stack relies on."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from veritriage.models import (
    ClassificationResult,
    Evidence,
    FailureCategory,
    Severity,
    SimulationEvent,
)


def make_event(**overrides) -> SimulationEvent:
    base = dict(
        severity=Severity.ERROR,
        message="Scoreboard mismatch",
        line_number=42,
        raw_line="UVM_ERROR ... Scoreboard mismatch",
        sim_time="55000",
    )
    base.update(overrides)
    return SimulationEvent(**base)


def test_severity_failure_flag():
    assert Severity.ERROR.is_failure
    assert Severity.FATAL.is_failure
    assert not Severity.WARNING.is_failure
    assert not Severity.INFO.is_failure


def test_evidence_from_event_carries_location():
    ev = Evidence.from_event(make_event())
    assert ev.line_number == 42
    assert ev.sim_time == "55000"
    assert "Scoreboard mismatch" in ev.description
    assert ev.snippet.startswith("UVM_ERROR")


def test_confidence_is_bounded():
    with pytest.raises(ValidationError):
        ClassificationResult(
            category=FailureCategory.TIMEOUT,
            confidence=101,
            rule_name="x",
            summary="too confident",
        )


def test_category_display_name():
    assert FailureCategory.ASSERTION_FAILURE.display_name == "Assertion Failure"
    assert FailureCategory.NO_FAILURE.display_name == "No Failure"


def test_line_numbers_are_one_based():
    with pytest.raises(ValidationError):
        make_event(line_number=0)
