"""Reasoning engine tests: every stage independently, then the whole pipeline."""

from __future__ import annotations

from veritriage.graph import EvidenceGraph, GraphBuilder
from veritriage.models import HypothesisCategory, WorkingSet
from veritriage.parsers import find_parser
from veritriage.reasoning import (
    EvidenceSelector,
    ReasoningEngine,
    RecommendationEngine,
    available_generators,
    evaluate_signals,
    generate_hypotheses,
    rank_hypotheses,
    register_generator,
)
from veritriage.reasoning.hypotheses import HypothesisGenerator


def graph_of(fixture_log, *names: str) -> EvidenceGraph:
    builder = GraphBuilder()
    for name in names:
        path = fixture_log(name)
        parser = find_parser(path)
        builder.add_fragment(parser.emit_evidence(parser.parse(path)))
    return builder.build()


class TestEvidenceSelection:
    def test_working_set_covers_failure_context(self, fixture_log):
        graph = graph_of(
            fixture_log, "uvm_scoreboard.log", "coverage.txt", "test_metadata.json"
        )
        ws = EvidenceSelector().select(graph)
        reasons = {item.reason for item in ws.items}
        assert "failing evidence" in reasons
        assert any(r.startswith("linked by") for r in reasons)
        # The run-metadata node is in the set (admitted via its part_of link).
        meta_ids = {n.id for n in graph.nodes.values() if n.artifact_type.value == "test_metadata"}
        assert meta_ids & set(ws.node_ids)
        assert all(node_id in graph.nodes for node_id in ws.node_ids)

    def test_working_set_is_bounded(self, fixture_log):
        graph = graph_of(fixture_log, "uvm_scoreboard.log", "coverage.txt")
        ws = EvidenceSelector(max_nodes=2).select(graph)
        assert len(ws.items) == 2

    def test_selection_is_deterministic(self, fixture_log):
        graph = graph_of(fixture_log, "uvm_timeout.log", "coverage.txt")
        assert EvidenceSelector().select(graph) == EvidenceSelector().select(graph)


class TestSignals:
    def test_timeout_without_assertion_boosts_rtl_deadlock(self, fixture_log):
        graph = graph_of(fixture_log, "uvm_timeout.log")
        ws = EvidenceSelector().select(graph)
        signals = evaluate_signals(graph, ws)
        names = {s.name for s in signals}
        assert "timeout-deadlock" in names
        signal = next(s for s in signals if s.name == "timeout-deadlock")
        assert signal.weights[HypothesisCategory.RTL_BUG] > 0
        assert signal.evidence_ids

    def test_assertion_suppresses_deadlock_signal(self, fixture_log):
        graph = graph_of(fixture_log, "uvm_assertion.log")
        ws = EvidenceSelector().select(graph)
        names = {s.name for s in evaluate_signals(graph, ws)}
        assert "protocol-violation" in names
        assert "timeout-deadlock" not in names

    def test_scoreboard_mismatch_without_assertion_boosts_testbench(self, fixture_log):
        graph = graph_of(fixture_log, "uvm_scoreboard.log")
        ws = EvidenceSelector().select(graph)
        signal = next(
            s for s in evaluate_signals(graph, ws) if s.name == "scoreboard-mismatch"
        )
        tb = signal.weights[HypothesisCategory.TESTBENCH_ISSUE]
        rtl = signal.weights[HypothesisCategory.RTL_BUG]
        assert tb > rtl

    def test_compile_diagnostics_signal(self, fixture_log):
        graph = graph_of(fixture_log, "compile.log")
        ws = EvidenceSelector().select(graph)
        names = {s.name for s in evaluate_signals(graph, ws)}
        assert "compile-diagnostics" in names

    def test_signals_never_conclude(self, fixture_log):
        # Architectural: signals carry weights and evidence, not verdicts.
        graph = graph_of(fixture_log, "uvm_scoreboard.log")
        ws = EvidenceSelector().select(graph)
        for signal in evaluate_signals(graph, ws):
            assert signal.evidence_ids, f"{signal.name} carries no evidence"
            assert signal.weights, f"{signal.name} carries no ranking weights"


class TestHypotheses:
    def test_every_hypothesis_cites_existing_evidence(self, fixture_log):
        graph = graph_of(
            fixture_log, "uvm_scoreboard.log", "coverage.txt", "test_metadata.json"
        )
        ws = EvidenceSelector().select(graph)
        for hypothesis in generate_hypotheses(graph, ws):
            assert hypothesis.evidence_ids, f"{hypothesis.id} has no evidence"
            assert all(i in graph.nodes for i in hypothesis.evidence_ids)

    def test_build_generator_abstains_without_compile_evidence(self, fixture_log):
        graph = graph_of(fixture_log, "uvm_scoreboard.log")
        ws = EvidenceSelector().select(graph)
        ids = {h.id for h in generate_hypotheses(graph, ws)}
        assert "hyp-build_issue" not in ids

    def test_clean_run_generates_no_hypotheses(self, fixture_log):
        graph = graph_of(fixture_log, "uvm_pass.log")
        ws = EvidenceSelector().select(graph)
        assert generate_hypotheses(graph, ws) == []

    def test_new_generator_plugs_in_without_touching_existing_code(self, fixture_log):
        @register_generator
        class ClockingIssueGenerator(HypothesisGenerator):
            name = "test-clocking-issue"
            category = HypothesisCategory.RTL_BUG

            def generate(self, graph, working_set):
                nodes = self._working_nodes(graph, working_set)
                failing = [n for n in nodes if n.is_failing]
                if not failing:
                    return None
                return self._build(
                    title="Clocking issue", statement="test", evidence=failing
                )

        try:
            assert "test-clocking-issue" in available_generators()
            graph = graph_of(fixture_log, "uvm_scoreboard.log")
            ws = EvidenceSelector().select(graph)
            titles = {h.title for h in generate_hypotheses(graph, ws)}
            assert "Clocking issue" in titles
        finally:
            from veritriage.reasoning.hypotheses import _GENERATORS

            _GENERATORS.pop("test-clocking-issue", None)


class TestRanking:
    def test_scoreboard_run_ranks_testbench_first(self, fixture_log):
        graph = graph_of(fixture_log, "uvm_scoreboard.log")
        ws = EvidenceSelector().select(graph)
        signals = evaluate_signals(graph, ws)
        ranked = rank_hypotheses(generate_hypotheses(graph, ws), signals, graph)
        assert ranked[0].category == HypothesisCategory.TESTBENCH_ISSUE
        assert ranked[0].confidence > ranked[-1].confidence

    def test_compile_run_ranks_build_first(self, fixture_log):
        graph = graph_of(fixture_log, "compile.log")
        ws = EvidenceSelector().select(graph)
        signals = evaluate_signals(graph, ws)
        ranked = rank_hypotheses(generate_hypotheses(graph, ws), signals, graph)
        assert ranked[0].category == HypothesisCategory.BUILD_ISSUE

    def test_confidence_trace_is_complete_and_consistent(self, fixture_log):
        graph = graph_of(fixture_log, "uvm_timeout.log")
        ws = EvidenceSelector().select(graph)
        signals = evaluate_signals(graph, ws)
        for hypothesis in rank_hypotheses(generate_hypotheses(graph, ws), signals, graph):
            trace = hypothesis.confidence_trace
            raw = trace.base + sum(c.delta for c in trace.contributions)
            expected = round(max(0.0, min(1.0, raw)) * trace.evidence_factor, 4)
            assert trace.final == expected
            assert hypothesis.confidence == trace.final
            assert 0.0 < trace.evidence_factor <= 1.0


class TestRecommendations:
    def test_recommendations_are_categorized(self, fixture_log):
        graph = graph_of(fixture_log, "uvm_scoreboard.log", "test_metadata.json")
        result = ReasoningEngine().reason(graph)
        assert result.recommendations
        priorities = [r.priority for r in result.recommendations]
        assert priorities == sorted(priorities)
        for rec in result.recommendations:
            assert rec.effort in ("low", "medium", "high")
            assert 0.0 <= rec.confidence <= 1.0
            assert rec.evidence_ids

    def test_recommendations_reproducible_from_same_graph(self, fixture_log):
        graph = graph_of(fixture_log, "uvm_timeout.log", "coverage.txt")
        a = ReasoningEngine().reason(graph)
        b = ReasoningEngine().reason(graph)
        assert a.recommendations == b.recommendations
        assert a == b


class TestStageIndependence:
    """Each stage runs standalone on constructed inputs: no hidden coupling."""

    def test_signals_run_on_hand_built_working_set(self, fixture_log):
        graph = graph_of(fixture_log, "uvm_timeout.log")
        subset = WorkingSet(
            items=[
                {"node_id": n.id, "reason": "manual"} for n in list(graph.failing())[:1]
            ]
        )
        signals = evaluate_signals(graph, subset)
        assert isinstance(signals, list)

    def test_ranking_runs_without_signals(self, fixture_log):
        graph = graph_of(fixture_log, "uvm_scoreboard.log")
        ws = EvidenceSelector().select(graph)
        ranked = rank_hypotheses(generate_hypotheses(graph, ws), [], graph)
        for hypothesis in ranked:
            assert hypothesis.confidence_trace.contributions == []

    def test_recommender_runs_on_ranked_hypotheses_alone(self, fixture_log):
        graph = graph_of(fixture_log, "uvm_scoreboard.log")
        ws = EvidenceSelector().select(graph)
        signals = evaluate_signals(graph, ws)
        ranked = rank_hypotheses(generate_hypotheses(graph, ws), signals, graph)
        recs = RecommendationEngine().recommend(ranked, graph)
        assert recs

    def test_engine_accepts_injected_stages(self, fixture_log):
        graph = graph_of(fixture_log, "uvm_scoreboard.log", "coverage.txt", "test_metadata.json")
        engine = ReasoningEngine(selector=EvidenceSelector(max_nodes=3), rules=[])
        result = engine.reason(graph)
        assert len(result.working_set.items) == 3
        assert result.signals == []
