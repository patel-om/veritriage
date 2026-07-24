"""Core Evidence Graph models: nodes, edges, and deterministic IDs.

The Evidence Graph is VeriTriage's single source of truth. Every parser emits
evidence nodes into it, deterministic correlation links them, the rule engine
classifies from it, and the AI layer reasons over it exclusively. Nothing
downstream of parsing ever reads a raw artifact again.
"""

from __future__ import annotations

import hashlib
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from veritriage.models.events import Severity


class ArtifactType(str, Enum):
    """The kind of verification artifact a piece of evidence came from."""

    SIMULATION_LOG = "simulation_log"
    ASSERTION = "assertion"
    COVERAGE = "coverage"
    TEST_METADATA = "test_metadata"
    COMPILE_LOG = "compile_log"
    #: Produced by the Waveform Intelligence Engine since M6 (v0.6.0).
    WAVEFORM_METADATA = "waveform_metadata"
    #: Produced by the Engineering Context Engine since M7 (v0.7.0): commits,
    #: CI runs, and other engineering change, normalized by context providers.
    ENGINEERING_CHANGE = "engineering_change"


class RelationType(str, Enum):
    """Typed relationships between evidence nodes."""

    #: Temporal ordering: source happened before target in the same run.
    PRECEDES = "precedes"
    #: Deterministic causal link, e.g. an assertion firing before a fatal.
    CAUSES = "causes"
    #: Cross-artifact association, e.g. a coverage hole in a failing scope.
    CORRELATES_WITH = "correlates_with"
    #: Membership, e.g. a failing event belongs to a test run.
    PART_OF = "part_of"
    #: One observation strengthens another without implying causality.
    SUPPORTS = "supports"


def make_node_id(*parts: str) -> str:
    """Deterministic node ID from identifying content.

    Hashing (artifact type, source path, location, message, ordinal) means the
    same input artifacts always produce the same graph, byte for byte, which
    keeps the whole pipeline reproducible and lets external tools reference
    nodes stably across re-runs.
    """
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()
    return f"ev-{digest[:12]}"


class EvidenceNode(BaseModel):
    """One verifiable observation extracted from a verification artifact."""

    id: str = Field(description="Deterministic content-derived ID (see make_node_id).")
    artifact_type: ArtifactType
    description: str = Field(description="Human-readable statement of the observation.")
    severity: Severity | None = Field(
        default=None,
        description="Severity when applicable; None for non-message artifacts (coverage, metadata).",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Extraction confidence: 1.0 for direct format matches, lower for inference.",
    )
    sim_time: str | None = Field(default=None, description="Simulation time, if the artifact reports one.")
    source_path: str = Field(description="Artifact file this evidence was extracted from.")
    line_number: int | None = Field(default=None, description="1-based line in the artifact.")
    module: str | None = Field(
        default=None, description="Design/testbench scope, e.g. 'uvm_test_top.env.scb'."
    )
    attributes: dict[str, Any] = Field(
        default_factory=dict,
        description="Artifact-specific payload (raw line, message id, coverage %, seed, ...).",
    )

    @property
    def is_failing(self) -> bool:
        """True for error/fatal evidence."""
        return self.severity is not None and self.severity.is_failure

    @property
    def raw_line(self) -> str | None:
        """Verbatim artifact line, when the parser preserved one."""
        value = self.attributes.get("raw_line")
        return str(value) if value is not None else None


class EvidenceEdge(BaseModel):
    """A typed, justified relationship between two evidence nodes.

    Every edge carries a rationale so the graph is self-explaining: any
    conclusion can be walked back through edges to raw artifact locations.
    """

    source_id: str
    target_id: str
    relation: RelationType
    rationale: str = Field(description="Why this relationship holds; shown in reports.")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
