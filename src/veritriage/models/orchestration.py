"""Orchestration vocabulary: Investigation Plans and Execution Traces (M9).

These are plain, frozen data models, placed in the layer-neutral ``models``
package (the same precedent as the waveform and engineering report views) so
the workspace session can reference them while the workspace itself stays
below the orchestrator in the dependency order.

A plan is what an investigation *intends* to do; a trace is what *happened*.
Plans are immutable and carry no execution state; statuses, timings, and
artifact flow live in the trace, so both can be serializable artifacts
without contradiction. Timings are observability, never identity: trace
*structure* is deterministic, durations are excluded from determinism
guarantees.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StepStatus(str, Enum):
    """Lifecycle of one plan step during execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class PlanStep(BaseModel):
    """One declared unit of investigation work."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="Step instance ID, unique within the plan.")
    step_type: str = Field(description="Registered step type this instance runs.")
    depends_on: tuple[str, ...] = Field(
        default=(), description="Plan-step IDs that must complete first."
    )
    inputs: tuple[str, ...] = Field(
        default=(),
        description="Artifact names this step reads (contract + trace bookkeeping; "
        "execution gating is by depends_on).",
    )
    outputs: tuple[str, ...] = Field(default=(), description="Artifact names this step produces.")
    max_retries: int = Field(default=0, ge=0)
    params: dict[str, Any] = Field(default_factory=dict)


class InvestigationPlan(BaseModel):
    """An immutable, serializable investigation workflow."""

    model_config = ConfigDict(frozen=True)

    plan_id: str = Field(description="Deterministic: profile + step IDs + created_for.")
    profile: str
    created_for: tuple[str, ...] = Field(
        default=(), description="Artifact paths (or a session ID, on resume)."
    )
    steps: tuple[PlanStep, ...]

    def step(self, step_id: str) -> PlanStep | None:
        for candidate in self.steps:
            if candidate.id == step_id:
                return candidate
        return None


class StepTrace(BaseModel):
    """What one step actually did when the plan ran."""

    model_config = ConfigDict(frozen=True)

    step_id: str
    step_type: str
    status: StepStatus
    attempts: int = 0
    duration_ms: float | None = Field(
        default=None, description="Wall-clock observability; excluded from determinism."
    )
    consumed: tuple[str, ...] = Field(
        default=(), description="Declared inputs that were present when the step ran."
    )
    produced: tuple[str, ...] = Field(default=(), description="Artifacts the step wrote.")
    evidence: tuple[str, ...] = Field(
        default=(), description="Key references produced, e.g. a session ID or report path."
    )
    note: str | None = Field(default=None, description="Failure reason or skip cause.")


class SubsystemAttribution(BaseModel):
    """Which intelligence subsystem contributed what, computed from the session."""

    model_config = ConfigDict(frozen=True)

    subsystem: str = Field(
        description="'rules', 'knowledge', 'waveform', 'engineering', 'history', 'ownership'."
    )
    signals: tuple[str, ...] = Field(default=(), description="Signal names it contributed.")
    recommendations: int = Field(
        default=0, description="Next-step recommendations originating from it."
    )


class InvestigationTrace(BaseModel):
    """The complete execution record of one plan run."""

    model_config = ConfigDict(frozen=True)

    plan_id: str
    profile: str
    steps: tuple[StepTrace, ...] = Field(description="In execution order.")
    attribution: tuple[SubsystemAttribution, ...] = Field(default=())
    total_duration_ms: float | None = None
    completed: bool = Field(description="True when every step COMPLETED.")

    def structural_view(self) -> dict[str, Any]:
        """The trace with timings stripped: the deterministic part.

        Two runs of the same plan over the same artifacts compare equal on
        this view; durations vary and are deliberately excluded.
        """
        return {
            "plan_id": self.plan_id,
            "profile": self.profile,
            "completed": self.completed,
            "steps": [
                step.model_dump(exclude={"duration_ms"}) for step in self.steps
            ],
            "attribution": [entry.model_dump() for entry in self.attribution],
        }
