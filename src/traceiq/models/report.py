"""Top-level analysis report and its constituent result models."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field

from traceiq.models.events import Severity, SimulationEvent
from traceiq.models.evidence import Evidence
from traceiq.models.failure import AssertionFailure, Failure, FailureCategory


class Recommendation(BaseModel):
    """A suggested next debugging step, always paired with a rationale."""

    action: str = Field(description="What the engineer should do next.")
    rationale: str = Field(description="Why this step follows from the evidence.")
    priority: int = Field(default=1, ge=1, description="1 = do first; higher numbers come later.")


class ClassificationResult(BaseModel):
    """The output of one rule: a verdict backed by evidence.

    The rule engine may produce several of these; the highest-confidence one
    becomes the report's primary classification and the rest are kept as
    alternatives so the engineer can see what else was considered.
    """

    category: FailureCategory
    confidence: int = Field(ge=0, le=100, description="Confidence in percent, 0-100.")
    rule_name: str = Field(description="Name of the rule that produced this result.")
    summary: str = Field(description="One-line verdict, e.g. 'Likely testbench issue'.")
    evidence: list[Evidence] = Field(default_factory=list)
    recommendations: list[Recommendation] = Field(default_factory=list)


class LogSummary(BaseModel):
    """Aggregate statistics about the parsed log."""

    total_lines: int = Field(ge=0)
    counts: dict[Severity, int] = Field(
        default_factory=dict, description="Event count per severity."
    )
    test_name: str | None = Field(default=None, description="Test name, if detected.")
    simulator: str | None = Field(default=None, description="Simulator, if detected.")
    last_sim_time: str | None = Field(
        default=None, description="Last simulation time observed in the log."
    )

    def count(self, severity: Severity) -> int:
        """Event count for one severity (0 if none were seen)."""
        return self.counts.get(severity, 0)


class AnalysisReport(BaseModel):
    """The complete result of one `traceiq analyze` run.

    Serialized verbatim to ``analysis.json`` and rendered to HTML. Fields are
    additive across versions; ``schema_version`` bumps on breaking changes.
    """

    schema_version: str = "1"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    input_file: str = Field(description="Path of the analyzed log, as given on the CLI.")
    parser_name: str = Field(description="Name of the parser that produced the events.")
    summary: LogSummary
    classification: ClassificationResult
    alternatives: list[ClassificationResult] = Field(
        default_factory=list, description="Other rule verdicts, sorted by descending confidence."
    )
    failures: list[Failure | AssertionFailure] = Field(default_factory=list)
    events: list[SimulationEvent] = Field(
        default_factory=list,
        description="Notable events (warning and above) in log order.",
    )
    ai_summary: str | None = Field(
        default=None, description="Optional AI-generated narrative; grounded in `evidence` only."
    )
