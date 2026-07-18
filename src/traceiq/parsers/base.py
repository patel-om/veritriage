"""Common parser interface every artifact parser implements."""

from __future__ import annotations

from abc import ABC, abstractmethod
from fnmatch import fnmatch
from pathlib import Path
from typing import ClassVar

from pydantic import BaseModel, Field

from traceiq.models import AssertionFailure, Failure, LogSummary, SimulationEvent


class ParseResult(BaseModel):
    """Normalized output of any parser.

    This is the hand-off contract between the parsing layer and everything
    downstream (rules, reports, AI). Future artifact types (coverage,
    assertions, waveform metadata) extend this model additively.
    """

    parser_name: str
    source_path: str
    events: list[SimulationEvent] = Field(default_factory=list)
    failures: list[Failure | AssertionFailure] = Field(default_factory=list)
    summary: LogSummary

    @property
    def failing_events(self) -> list[SimulationEvent]:
        """Events with error or fatal severity, in log order."""
        return [e for e in self.events if e.severity.is_failure]


class Parser(ABC):
    """Base class for all artifact parsers.

    Subclasses set :attr:`name` and :attr:`file_patterns` and implement
    :meth:`parse`. Registration happens via the ``@register`` decorator in
    :mod:`traceiq.parsers.registry`.
    """

    #: Unique parser name, used for CLI selection and report provenance.
    name: ClassVar[str]

    #: Glob patterns this parser claims by default (used by ``can_parse``).
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
