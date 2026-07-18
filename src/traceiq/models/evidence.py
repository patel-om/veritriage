"""Evidence: the atoms every TraceIQ conclusion must be built from."""

from __future__ import annotations

from pydantic import BaseModel, Field

from traceiq.models.events import SimulationEvent


class Evidence(BaseModel):
    """A single verifiable observation supporting a conclusion.

    Every classification the rule engine emits — and every claim the optional
    AI summary is allowed to make — must trace back to one or more of these.
    Each piece of evidence points at a concrete location in the source log.
    """

    description: str = Field(description="Human-readable statement of what was observed.")
    line_number: int | None = Field(
        default=None, description="1-based line in the source log this observation points at."
    )
    snippet: str | None = Field(default=None, description="Verbatim log excerpt backing the claim.")
    sim_time: str | None = Field(default=None, description="Simulation time of the observation.")

    @classmethod
    def from_event(cls, event: SimulationEvent, description: str | None = None) -> Evidence:
        """Build evidence directly from a parsed event.

        Args:
            event: The event backing the observation.
            description: Override text; defaults to the event's own message.
        """
        return cls(
            description=description or f"{event.severity.value.upper()}: {event.message}",
            line_number=event.line_number,
            snippet=event.raw_line,
            sim_time=event.sim_time,
        )
