"""EngineeringContextParser: context manifests enter as ordinary artifacts.

The seam that lets ``pipeline.analyze()`` accept a ``*.engctx.json`` exactly
like a log or a waveform: the file is just another artifact claimed by a
registered ``Parser``. Internally it delegates to the manifest provider's
loader (the only format-aware step) and projects the normalized context into
evidence via the tool-agnostic context engine.

CI systems that cannot invoke providers at collection time simply drop a
manifest next to the logs, and everything downstream is identical to the
live-provider path.
"""

from __future__ import annotations

from pathlib import Path

from veritriage.engineering.context import emit_engineering_evidence
from veritriage.engineering.model import EngineeringContext
from veritriage.engineering.providers.manifest import MANIFEST_PATTERNS, load_manifest
from veritriage.graph.builder import GraphFragment
from veritriage.graph.model import ArtifactType
from veritriage.models import LogSummary
from veritriage.parsers.base import Parser, ParseResult
from veritriage.parsers.registry import register

_CONTEXT_KEY = "engineering_context"


@register
class EngineeringContextParser(Parser):
    """Parses a canonical engineering-context manifest into change evidence."""

    name = "engineering_context"
    artifact_type = ArtifactType.ENGINEERING_CHANGE
    file_patterns = MANIFEST_PATTERNS

    def parse(self, path: Path) -> ParseResult:
        context = load_manifest(path)
        return ParseResult(
            parser_name=self.name,
            source_path=str(path),
            summary=LogSummary(total_lines=len(context.commits)),
            metadata={_CONTEXT_KEY: context},
        )

    def emit_evidence(self, result: ParseResult) -> GraphFragment:
        context = stored_context(result)
        if context is None:
            return GraphFragment()
        return emit_engineering_evidence(context)


def stored_context(result: ParseResult) -> EngineeringContext | None:
    """The normalized context a manifest parse stashed, if any."""
    stored = result.metadata.get(_CONTEXT_KEY)
    return stored if isinstance(stored, EngineeringContext) else None
