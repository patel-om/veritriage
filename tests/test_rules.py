"""Rule engine tests: one fixture per failure class, plus fallbacks.

Since v2 the rules evaluate the Evidence Graph, never parse results or raw
files, so classification works identically for any artifact mix.
"""

from __future__ import annotations

from veritriage.graph import EvidenceGraph, GraphBuilder
from veritriage.models import ClassificationResult, FailureCategory
from veritriage.parsers import find_parser
from veritriage.rules import Rule, RuleEngine


def graph_of(fixture_log, *names: str) -> EvidenceGraph:
    builder = GraphBuilder()
    for name in names:
        path = fixture_log(name)
        parser = find_parser(path)
        builder.add_fragment(parser.emit_evidence(parser.parse(path)))
    return builder.build()


def classify(fixture_log, *names: str):
    return RuleEngine().classify(graph_of(fixture_log, *names))


class TestBuiltinRules:
    def test_clean_log_is_no_failure(self, fixture_log):
        primary, alternatives = classify(fixture_log, "uvm_pass.log")
        assert primary.category == FailureCategory.NO_FAILURE
        assert alternatives == []

    def test_assertion_beats_fatal(self, fixture_log):
        primary, alternatives = classify(fixture_log, "uvm_assertion.log")
        assert primary.category == FailureCategory.ASSERTION_FAILURE
        assert primary.confidence == 90
        assert FailureCategory.FATAL_ERROR in {a.category for a in alternatives}

    def test_timeout_detected(self, fixture_log):
        primary, _ = classify(fixture_log, "uvm_timeout.log")
        assert primary.category == FailureCategory.TIMEOUT
        assert primary.confidence == 85

    def test_scoreboard_mismatch_is_testbench_failure(self, fixture_log):
        primary, _ = classify(fixture_log, "uvm_scoreboard.log")
        assert primary.category == FailureCategory.TESTBENCH_FAILURE
        assert primary.evidence, "verdict must carry evidence"
        assert all(ev.line_number for ev in primary.evidence)
        assert all(ev.node_id for ev in primary.evidence), "evidence must cite graph nodes"
        assert primary.recommendations, "verdict must suggest next steps"

    def test_compile_failure_from_dedicated_compile_log(self, fixture_log):
        primary, _ = classify(fixture_log, "compile.log")
        assert primary.category == FailureCategory.COMPILE_FAILURE
        assert primary.confidence == 90

    def test_compile_failure_inside_simulation_log(self, fixture_log):
        primary, _ = classify(fixture_log, "vcs_compile_error.log")
        assert primary.category == FailureCategory.COMPILE_FAILURE

    def test_bare_fatal_classified(self, fixture_log):
        primary, _ = classify(fixture_log, "questa_fatal.log")
        assert primary.category == FailureCategory.FATAL_ERROR

    def test_multi_artifact_classification_unchanged(self, fixture_log):
        # Adding coverage and metadata artifacts adds context, not misfires:
        # the verdict stays the same as for the log alone.
        primary, _ = classify(
            fixture_log, "uvm_scoreboard.log", "coverage.txt", "test_metadata.json"
        )
        assert primary.category == FailureCategory.TESTBENCH_FAILURE

    def test_every_failing_verdict_has_evidence_and_steps(self, fixture_log):
        for name in (
            "uvm_assertion.log",
            "uvm_timeout.log",
            "uvm_scoreboard.log",
            "compile.log",
            "questa_fatal.log",
        ):
            primary, _ = classify(fixture_log, name)
            assert primary.evidence, f"{name}: no evidence"
            assert primary.recommendations, f"{name}: no recommendations"


class TestEngineExtensibility:
    def test_unknown_failure_fallback(self, tmp_path, fixture_log):
        log = tmp_path / "weird.log"
        log.write_text("Error: flux capacitor misaligned\n")
        parser = find_parser(log)
        builder = GraphBuilder()
        builder.add_fragment(parser.emit_evidence(parser.parse(log)))
        primary, _ = RuleEngine().classify(builder.build())
        assert primary.category == FailureCategory.UNKNOWN_FAILURE
        assert primary.confidence == 30
        assert primary.evidence

    def test_custom_rule_can_outrank_builtins(self, fixture_log):
        class FluxRule(Rule):
            name = "flux"
            category = FailureCategory.TESTBENCH_FAILURE

            def evaluate(self, graph):
                return ClassificationResult(
                    category=self.category,
                    confidence=99,
                    rule_name=self.name,
                    summary="custom rule wins",
                )

        engine = RuleEngine()
        engine.register(FluxRule())
        primary, _ = engine.classify(graph_of(fixture_log, "uvm_assertion.log"))
        assert primary.rule_name == "flux"

    def test_deterministic_output(self, fixture_log):
        a = classify(fixture_log, "uvm_timeout.log", "coverage.txt")
        b = classify(fixture_log, "uvm_timeout.log", "coverage.txt")
        assert a == b
