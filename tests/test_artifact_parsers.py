"""Tests for the non-simulation artifact parsers added in v2."""

from __future__ import annotations

import pytest

from veritriage.graph import ArtifactType
from veritriage.parsers import (
    CompileLogParser,
    CoverageParser,
    FormalResultParser,
    TestMetadataParser,
    find_parser,
)
from veritriage.pipeline import analyze


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


class TestFormalResultParser:
    def test_claims_formal_json(self, fixture_log):
        parser = find_parser(fixture_log("formal_run.formal.json"))
        assert isinstance(parser, FormalResultParser)

    def test_emits_per_property_evidence_with_verdicts(self, fixture_log):
        parser = FormalResultParser()
        result = parser.parse(fixture_log("formal_run.formal.json"))
        fragment = parser.emit_evidence(result)
        assert len(fragment.nodes) == 5
        assert all(n.artifact_type == ArtifactType.FORMAL_RESULT for n in fragment.nodes)
        statuses = {n.attributes["property"]: n.attributes["status"] for n in fragment.nodes}
        assert statuses["p_grant_onehot"] == "falsified"
        assert statuses["p_req_ack"] == "vacuous"
        assert statuses["c_wr_hit"] == "covered"
        # falsified / vacuous / inconclusive are failing; proven / covered are not.
        failing = {n.attributes["property"] for n in fragment.nodes if n.is_failing}
        assert failing == {"p_grant_onehot", "p_forward_progress", "p_req_ack"}

    def test_status_aliases_normalize(self):
        parser = FormalResultParser()
        from pathlib import Path
        import json
        import tempfile

        raw = {"properties": [
            {"name": "a", "status": "CEX"},
            {"name": "b", "status": "proved"},
            {"name": "c", "status": "undetermined"},
        ]}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.formal.json"
            p.write_text(json.dumps(raw), encoding="utf-8")
            fragment = parser.emit_evidence(parser.parse(p))
        by_name = {n.attributes["property"]: n.attributes["status"] for n in fragment.nodes}
        assert by_name == {"a": "falsified", "b": "proven", "c": "inconclusive"}

    def test_native_formal_reaches_the_knowledge_pack(self, fixture_log):
        # The point of native ingestion: formal verdicts become first-class
        # evidence the formal Knowledge Pack matches and reasons over, with no
        # log scraping.
        outcome = analyze([fixture_log("formal_run.formal.json")])
        assert outcome.report.knowledge is not None
        matched = {p.pattern_id for p in outcome.report.knowledge.patterns}
        assert {"formal.counterexample", "formal.vacuous-pass", "formal.inconclusive-bound"} <= matched
        signals = {s.name for s in outcome.report.reasoning.signals}
        assert "knowledge:formal.counterexample" in signals
