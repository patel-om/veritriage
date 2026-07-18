"""Test metadata parser (JSON).

A test metadata file describes the run itself: test name, seed, status, and
whatever else the flow records. It becomes a single evidence node that the
correlator attaches failures to, giving every failure a "which run was this"
anchor in the graph.
"""

from __future__ import annotations

import json
from pathlib import Path

from traceiq.graph.builder import GraphFragment
from traceiq.graph.model import ArtifactType, EvidenceNode, make_node_id
from traceiq.models import LogSummary
from traceiq.parsers.base import Parser, ParseResult
from traceiq.parsers.registry import register

_NAME_KEYS = ("test_name", "test", "name")


@register
class TestMetadataParser(Parser):
    """Parses a JSON test-metadata file into a single run-descriptor node."""

    name = "test_metadata"
    artifact_type = ArtifactType.TEST_METADATA
    file_patterns = ("test_metadata.json", "*metadata*.json", "run_info.json")

    def parse(self, path: Path) -> ParseResult:
        raw = path.read_text(encoding="utf-8", errors="replace")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path} is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise ValueError(f"{path}: expected a JSON object at the top level")

        test_name = next((str(data[k]) for k in _NAME_KEYS if data.get(k)), None)
        return ParseResult(
            parser_name=self.name,
            source_path=str(path),
            summary=LogSummary(
                total_lines=raw.count("\n") + 1,
                test_name=test_name,
                simulator=str(data["simulator"]) if data.get("simulator") else None,
            ),
            metadata={"data": data},
        )

    def emit_evidence(self, result: ParseResult) -> GraphFragment:
        data: dict = result.metadata.get("data", {})
        test_name = result.summary.test_name or "unknown_test"
        details = ", ".join(
            f"{key}={data[key]}"
            for key in ("seed", "status", "simulator", "duration_s")
            if data.get(key) is not None
        )
        description = f"Test run {test_name}" + (f" ({details})" if details else "")
        # Only scalar fields go into attributes; nested structures stay in
        # analysis.json via ParseResult.metadata if ever needed.
        scalars = {
            k: v for k, v in data.items() if isinstance(v, (str, int, float, bool))
        }
        node = EvidenceNode(
            id=make_node_id(self.artifact_type.value, result.source_path, test_name),
            artifact_type=self.artifact_type,
            description=description,
            source_path=result.source_path,
            module=None,
            attributes=scalars,
        )
        return GraphFragment(nodes=[node])
