"""Evidence: the atoms every VeriTriage conclusion must be built from."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from veritriage.models.events import SimulationEvent

if TYPE_CHECKING:  # models must never import graph at runtime (graph imports models)
    from veritriage.graph.model import EvidenceNode


class Evidence(BaseModel):
    """A single verifiable observation supporting a conclusion.

    Every classification the rule engine emits - and every claim the optional
    AI summary is allowed to make - must trace back to one of these. Each
    piece of evidence points at a concrete location in a source artifact and,
    since v2, at its node in the Evidence Graph.
    """

    description: str = Field(description="Human-readable statement of what was observed.")
    line_number: int | None = Field(
        default=None, description="1-based line in the source artifact this points at."
    )
    snippet: str | None = Field(default=None, description="Verbatim artifact excerpt backing the claim.")
    sim_time: str | None = Field(default=None, description="Simulation time of the observation.")
    node_id: str | None = Field(
        default=None, description="ID of the Evidence Graph node backing this claim."
    )

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

    @classmethod
    def from_node(cls, node: EvidenceNode, description: str | None = None) -> Evidence:
        """Build evidence from an Evidence Graph node, keeping the node link.

        Args:
            node: The graph node backing the observation.
            description: Override text; defaults to severity + node description.
        """
        prefix = node.severity.value.upper() if node.severity else node.artifact_type.value
        return cls(
            description=description or f"{prefix}: {node.description}",
            line_number=node.line_number,
            snippet=node.raw_line,
            sim_time=node.sim_time,
            node_id=node.id,
        )
