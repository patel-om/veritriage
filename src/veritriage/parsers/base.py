"""Common parser interface every artifact parser implements."""

from __future__ import annotations

from abc import ABC, abstractmethod
from fnmatch import fnmatch
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel, Field

from veritriage.graph.builder import GraphFragment
from veritriage.graph.model import (
    ArtifactType,
    EvidenceEdge,
    EvidenceNode,
    RelationType,
    make_node_id,
)
from veritriage.models import AssertionFailure, Failure, LogSummary, Severity, SimulationEvent


class ParseResult(BaseModel):
    """Normalized output of any parser.

    This is the hand-off contract between the parsing layer and everything
    downstream. Message-oriented artifacts populate ``events``/``failures``;
    other artifacts (coverage, test metadata) carry their payload in
    ``metadata`` and describe it fully in their evidence fragment.
    """

    parser_name: str
    source_path: str
    events: list[SimulationEvent] = Field(default_factory=list)
    failures: list[Failure | AssertionFailure] = Field(default_factory=list)
    summary: LogSummary
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Artifact-specific payload for non-message artifacts."
    )

    @property
    def failing_events(self) -> list[SimulationEvent]:
        """Events with error or fatal severity, in log order."""
        return [e for e in self.events if e.severity.is_failure]


class Parser(ABC):
    """Base class for all artifact parsers.

    Subclasses set :attr:`name`, :attr:`artifact_type`, and
    :attr:`file_patterns`, implement :meth:`parse`, and register with the
    ``@register`` decorator. The default :meth:`emit_evidence` covers
    message-oriented artifacts; parsers with other shapes override it.
    """

    #: Unique parser name, used for CLI selection and report provenance.
    name: ClassVar[str]

    #: Evidence nodes this parser emits are tagged with this artifact type.
    artifact_type: ClassVar[ArtifactType] = ArtifactType.SIMULATION_LOG

    #: Glob patterns this parser claims (ranked by specificity in find_parser).
    file_patterns: ClassVar[tuple[str, ...]] = ()

    @classmethod
    def can_parse(cls, path: Path) -> bool:
        """Whether this parser claims the given file.

        The default implementation matches the filename against
        :attr:`file_patterns`; parsers may override to sniff content.
        """
        return any(fnmatch(path.name, pattern) for pattern in cls.file_patterns)

    @abstractmethod
    def parse(self, path: Path) -> ParseResult:
        """Parse the artifact at ``path`` into a :class:`ParseResult`."""
        raise NotImplementedError

    def emit_evidence(self, result: ParseResult) -> GraphFragment:
        """Project a parse result into evidence nodes and intra-artifact edges.

        Default behavior for message-oriented artifacts:

        * every non-INFO event becomes a node; assertion failures are tagged
          ``ArtifactType.ASSERTION`` so they are queryable as first-class
          evidence regardless of which log carried them;
        * consecutive failing nodes are chained with PRECEDES edges;
        * an assertion followed by a fatal gets a CAUSES edge.
        """
        assertion_lines = {
            f.event.line_number for f in result.failures if f.kind == "assertion_failure"
        }
        nodes: list[EvidenceNode] = []
        edges: list[EvidenceEdge] = []
        previous_failing: EvidenceNode | None = None
        open_assertions: list[EvidenceNode] = []

        for ordinal, event in enumerate(result.events):
            if event.severity == Severity.INFO:
                continue
            is_assertion = event.line_number in assertion_lines
            node_type = ArtifactType.ASSERTION if is_assertion else self.artifact_type
            attributes: dict[str, Any] = {"raw_line": event.raw_line}
            for key, value in (
                ("message_id", event.message_id),
                ("source_file", event.source_file),
                ("source_line", event.source_line),
            ):
                if value is not None:
                    attributes[key] = value

            node = EvidenceNode(
                id=make_node_id(
                    node_type.value,
                    result.source_path,
                    str(event.line_number),
                    event.message,
                    str(ordinal),
                ),
                artifact_type=node_type,
                description=event.message,
                severity=event.severity,
                sim_time=event.sim_time,
                source_path=result.source_path,
                line_number=event.line_number,
                module=event.component,
                attributes=attributes,
            )
            nodes.append(node)

            if not node.is_failing:
                continue
            if previous_failing is not None:
                edges.append(
                    EvidenceEdge(
                        source_id=previous_failing.id,
                        target_id=node.id,
                        relation=RelationType.PRECEDES,
                        rationale="Earlier failing message in the same artifact.",
                    )
                )
            previous_failing = node
            # A fatal terminates the run: earlier assertions are its likely
            # cause even when the fatal message itself references an assertion.
            if event.severity == Severity.FATAL and open_assertions:
                for assertion in open_assertions:
                    edges.append(
                        EvidenceEdge(
                            source_id=assertion.id,
                            target_id=node.id,
                            relation=RelationType.CAUSES,
                            rationale="Assertion fired before this fatal ended the run.",
                        )
                    )
                open_assertions = []
            elif is_assertion:
                open_assertions.append(node)

        return GraphFragment(nodes=nodes, edges=edges)
