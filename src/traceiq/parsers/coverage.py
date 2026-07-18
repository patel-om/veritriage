"""Coverage summary parser.

v2 supports a simple line-oriented coverage summary format:

    covergroup cg_axi_burst : 72.50%
    module scoreboard : 55.00%

Each entry becomes one evidence node; entries below 100% are flagged as holes
so the correlator can link them to failures in the same scope.
"""

from __future__ import annotations

import re
from pathlib import Path

from traceiq.graph.builder import GraphFragment
from traceiq.graph.model import ArtifactType, EvidenceNode, make_node_id
from traceiq.models import LogSummary
from traceiq.parsers.base import Parser, ParseResult
from traceiq.parsers.registry import register

_COVERAGE_RE = re.compile(
    r"^\s*(?P<kind>covergroup|module|instance|group)\s+(?P<name>\S+)\s*:?\s*"
    r"(?P<pct>\d+(?:\.\d+)?)\s*%\s*$",
    re.IGNORECASE,
)


@register
class CoverageParser(Parser):
    """Parses a coverage summary into per-scope evidence nodes."""

    name = "coverage"
    artifact_type = ArtifactType.COVERAGE
    file_patterns = ("coverage.txt", "coverage*.txt", "*.cov")

    def parse(self, path: Path) -> ParseResult:
        entries: list[dict[str, object]] = []
        total_lines = 0
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
        ):
            total_lines = line_number
            m = _COVERAGE_RE.match(line)
            if not m:
                continue
            pct = float(m["pct"])
            entries.append(
                {
                    "kind": m["kind"].lower(),
                    "name": m["name"],
                    "pct": pct,
                    "is_hole": pct < 100.0,
                    "line_number": line_number,
                }
            )
        return ParseResult(
            parser_name=self.name,
            source_path=str(path),
            summary=LogSummary(total_lines=total_lines),
            metadata={"entries": entries},
        )

    def emit_evidence(self, result: ParseResult) -> GraphFragment:
        nodes = []
        for entry in result.metadata.get("entries", []):
            name = str(entry["name"])
            pct = float(entry["pct"])  # type: ignore[arg-type]
            nodes.append(
                EvidenceNode(
                    id=make_node_id(
                        self.artifact_type.value,
                        result.source_path,
                        str(entry["line_number"]),
                        name,
                    ),
                    artifact_type=self.artifact_type,
                    description=f"{entry['kind']} {name} coverage at {pct:g}%",
                    source_path=result.source_path,
                    line_number=int(entry["line_number"]),  # type: ignore[arg-type]
                    module=name,
                    attributes={
                        "kind": entry["kind"],
                        "pct": pct,
                        "is_hole": bool(entry["is_hole"]),
                    },
                )
            )
        return GraphFragment(nodes=nodes)
