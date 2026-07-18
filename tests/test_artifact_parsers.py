"""Tests for the non-simulation artifact parsers added in v2."""

from __future__ import annotations

import pytest

from veritriage.graph import ArtifactType
from veritriage.parsers import (
    CompileLogParser,
    CoverageParser,
    TestMetadataParser,
    find_parser,
)


class TestCompileLogParser:
    def test_claims_compile_log_over_generic_simulation(self, fixture_log):
        parser = find_parser(fixture_log("compile.log"))
        assert isinstance(parser, CompileLogParser)

    def test_emits_compile_log_evidence(self, fixture_log):
        parser = CompileLogParser()
        result = parser.parse(fixture_log("compile.log"))
        fragment = parser.emit_evidence(result)
        assert fragment.nodes
        assert all(n.artifact_type == ArtifactType.COMPILE_LOG for n in fragment.nodes)
        codes = {n.attributes.get("message_id") for n in fragment.nodes}
        assert codes == {"SE", "UD"}


class TestCoverageParser:
    def test_claims_coverage_txt(self, fixture_log):
        assert isinstance(find_parser(fixture_log("coverage.txt")), CoverageParser)

    def test_extracts_entries_and_flags_holes(self, fixture_log):
        parser = CoverageParser()
        result = parser.parse(fixture_log("coverage.txt"))
        fragment = parser.emit_evidence(result)
        assert len(fragment.nodes) == 4
        by_module = {n.module: n for n in fragment.nodes}
        assert by_module["scoreboard"].attributes["pct"] == 55.0
        assert by_module["scoreboard"].attributes["is_hole"] is True
        assert by_module["cg_reset"].attributes["is_hole"] is False
        # Coverage carries no message severity.
        assert all(n.severity is None for n in fragment.nodes)


class TestTestMetadataParser:
    def test_claims_test_metadata_json(self, fixture_log):
        assert isinstance(find_parser(fixture_log("test_metadata.json")), TestMetadataParser)

    def test_single_run_node_with_scalar_attributes(self, fixture_log):
        parser = TestMetadataParser()
        result = parser.parse(fixture_log("test_metadata.json"))
        fragment = parser.emit_evidence(result)
        assert len(fragment.nodes) == 1
        node = fragment.nodes[0]
        assert node.artifact_type == ArtifactType.TEST_METADATA
        assert "axi_random_test" in node.description
        assert node.attributes["seed"] == 987654321
        assert result.summary.test_name == "axi_random_test"

    def test_invalid_json_raises(self, tmp_path):
        bad = tmp_path / "test_metadata.json"
        bad.write_text("not json {")
        with pytest.raises(ValueError, match="not valid JSON"):
            TestMetadataParser().parse(bad)
