"""Rule engine tests: one fixture per failure class, plus fallbacks."""

from __future__ import annotations

from traceiq.models import ClassificationResult, FailureCategory
from traceiq.parsers import SimulationLogParser
from traceiq.rules import Rule, RuleEngine


def classify(fixture_log, name: str):
    result = SimulationLogParser().parse(fixture_log(name))
    return RuleEngine().classify(result)


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
        assert primary.recommendations, "verdict must suggest next steps"

    def test_compile_failure_detected(self, fixture_log):
        primary, _ = classify(fixture_log, "vcs_compile_error.log")
        assert primary.category == FailureCategory.COMPILE_FAILURE
        assert primary.confidence == 90

    def test_bare_fatal_classified(self, fixture_log):
        primary, _ = classify(fixture_log, "questa_fatal.log")
        assert primary.category == FailureCategory.FATAL_ERROR

    def test_every_failing_verdict_has_evidence_and_steps(self, fixture_log):
        for name in (
            "uvm_assertion.log",
            "uvm_timeout.log",
            "uvm_scoreboard.log",
            "vcs_compile_error.log",
            "questa_fatal.log",
        ):
            primary, _ = classify(fixture_log, name)
            assert primary.evidence, f"{name}: no evidence"
            assert primary.recommendations, f"{name}: no recommendations"


class TestEngineExtensibility:
    def test_unknown_failure_fallback(self, tmp_path):
        log = tmp_path / "weird.log"
        log.write_text("Error: flux capacitor misaligned\n")
        result = SimulationLogParser().parse(log)
        primary, _ = RuleEngine().classify(result)
        assert primary.category == FailureCategory.UNKNOWN_FAILURE
        assert primary.confidence == 30
        assert primary.evidence

    def test_custom_rule_can_outrank_builtins(self, fixture_log):
        class FluxRule(Rule):
            name = "flux"
            category = FailureCategory.TESTBENCH_FAILURE

            def evaluate(self, parse_result):
                return ClassificationResult(
                    category=self.category,
                    confidence=99,
                    rule_name=self.name,
                    summary="custom rule wins",
                )

        engine = RuleEngine()
        engine.register(FluxRule())
        result = SimulationLogParser().parse(fixture_log("uvm_assertion.log"))
        primary, _ = engine.classify(result)
        assert primary.rule_name == "flux"

    def test_deterministic_output(self, fixture_log):
        a = classify(fixture_log, "uvm_timeout.log")
        b = classify(fixture_log, "uvm_timeout.log")
        assert a == b
