"""Evidence Graph tests: determinism, integrity, correlation, and the AI boundary."""

from __future__ import annotations

import pytest

from traceiq.graph import (
    ArtifactType,
    EvidenceEdge,
    EvidenceGraph,
    EvidenceNode,
    GraphBuilder,
    RelationType,
    make_node_id,
)
from traceiq.parsers import find_parser


def build_graph(fixture_log, *names: str) -> EvidenceGraph:
    builder = GraphBuilder()
    for name in names:
        path = fixture_log(name)
        parser = find_parser(path)
        builder.add_fragment(parser.emit_evidence(parser.parse(path)))
    return builder.build()


class TestGraphIntegrity:
    def test_node_ids_are_deterministic(self, fixture_log):
        a = build_graph(fixture_log, "uvm_scoreboard.log")
        b = build_graph(fixture_log, "uvm_scoreboard.log")
        assert list(a.nodes) == list(b.nodes)
        assert a == b

    def test_edges_must_reference_existing_nodes(self):
        graph = EvidenceGraph()
        node = EvidenceNode(
            id=make_node_id("simulation_log", "x.log", "1", "boom"),
            artifact_type=ArtifactType.SIMULATION_LOG,
            description="boom",
            source_path="x.log",
        )
        graph.add_node(node)
        with pytest.raises(KeyError, match="unknown node"):
            graph.add_edge(
                EvidenceEdge(
                    source_id=node.id,
                    target_id="ev-nonexistent",
                    relation=RelationType.PRECEDES,
                    rationale="broken",
                )
            )

    def test_id_collision_with_different_content_rejected(self):
        graph = EvidenceGraph()
        node_id = make_node_id("simulation_log", "x.log", "1", "boom")
        graph.add_node(
            EvidenceNode(
                id=node_id,
                artifact_type=ArtifactType.SIMULATION_LOG,
                description="boom",
                source_path="x.log",
            )
        )
        with pytest.raises(ValueError, match="collision"):
            graph.add_node(
                EvidenceNode(
                    id=node_id,
                    artifact_type=ArtifactType.SIMULATION_LOG,
                    description="different content",
                    source_path="x.log",
                )
            )


class TestParserEmission:
    def test_every_parser_output_has_required_fields(self, fixture_log):
        graph = build_graph(
            fixture_log, "uvm_scoreboard.log", "compile.log", "coverage.txt", "test_metadata.json"
        )
        for node in graph.nodes.values():
            assert node.id.startswith("ev-")
            assert node.description
            assert node.source_path
            assert 0.0 <= node.confidence <= 1.0

    def test_all_declared_artifact_types_present(self, fixture_log):
        graph = build_graph(
            fixture_log,
            "uvm_scoreboard.log",
            "uvm_assertion.log",
            "compile.log",
            "coverage.txt",
            "test_metadata.json",
        )
        types = {n.artifact_type for n in graph.nodes.values()}
        assert ArtifactType.SIMULATION_LOG in types
        assert ArtifactType.ASSERTION in types
        assert ArtifactType.COMPILE_LOG in types
        assert ArtifactType.COVERAGE in types
        assert ArtifactType.TEST_METADATA in types

    def test_assertion_causes_fatal_edge(self, fixture_log):
        graph = build_graph(fixture_log, "uvm_assertion.log")
        causes = [e for e in graph.edges if e.relation == RelationType.CAUSES]
        assert causes, "expected assertion -> fatal CAUSES edge"
        src = graph.nodes[causes[0].source_id]
        assert src.artifact_type == ArtifactType.ASSERTION

    def test_failing_events_chained_by_precedes(self, fixture_log):
        graph = build_graph(fixture_log, "uvm_scoreboard.log")
        precedes = [e for e in graph.edges if e.relation == RelationType.PRECEDES]
        assert len(precedes) == 1  # two failing events, one chain link


class TestCorrelation:
    def test_failures_linked_to_test_run(self, fixture_log):
        graph = build_graph(fixture_log, "uvm_scoreboard.log", "test_metadata.json")
        part_of = [e for e in graph.edges if e.relation == RelationType.PART_OF]
        assert part_of
        run = graph.nodes[part_of[0].target_id]
        assert run.artifact_type == ArtifactType.TEST_METADATA

    def test_coverage_hole_correlates_with_failure_in_same_scope(self, fixture_log):
        graph = build_graph(fixture_log, "uvm_scoreboard.log", "coverage.txt")
        correlates = [e for e in graph.edges if e.relation == RelationType.CORRELATES_WITH]
        assert correlates, "scoreboard coverage hole should link to scoreboard failure"
        hole = graph.nodes[correlates[0].source_id]
        assert hole.module == "scoreboard"
        assert hole.attributes["is_hole"] is True

    def test_full_coverage_never_correlates(self, fixture_log):
        graph = build_graph(fixture_log, "uvm_scoreboard.log", "coverage.txt")
        full = next(n for n in graph.nodes.values() if n.module == "cg_reset")
        assert not graph.edges_from(full.id)


class TestReasoningView:
    """The reasoning view is the AI boundary: bounded, normalized, no raw text."""

    def test_view_contains_only_included_nodes_and_their_edges(self, fixture_log):
        graph = build_graph(fixture_log, "uvm_assertion.log", "test_metadata.json")
        view = graph.to_reasoning_view()
        ids = {n["id"] for n in view["nodes"]}
        for edge in view["edges"]:
            assert edge["source"] in ids
            assert edge["target"] in ids

    def test_view_is_bounded(self, fixture_log):
        graph = build_graph(fixture_log, "uvm_scoreboard.log")
        view = graph.to_reasoning_view(max_nodes=1)
        assert len(view["nodes"]) == 1

    def test_view_never_leaks_raw_artifact_lines(self, fixture_log):
        # Raw lines live in node attributes for reports, but the AI view
        # must expose only normalized fields.
        graph = build_graph(fixture_log, "uvm_scoreboard.log")
        view = graph.to_reasoning_view()
        for node in view["nodes"]:
            assert "raw_line" not in node
            assert "attributes" not in node
