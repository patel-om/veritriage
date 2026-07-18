"""Parser layer tests: event extraction, metadata, registry plumbing."""

from __future__ import annotations

from pathlib import Path

import pytest

from traceiq.models import AssertionFailure, Severity
from traceiq.parsers import SimulationLogParser, available_parsers, find_parser, get_parser
from traceiq.parsers.base import Parser
from traceiq.parsers.registry import register


def parse(fixture_log, name: str):
    return SimulationLogParser().parse(fixture_log(name))


class TestUvmParsing:
    def test_clean_log_has_no_failures(self, fixture_log):
        result = parse(fixture_log, "uvm_pass.log")
        assert result.failures == []
        assert result.summary.count(Severity.ERROR) == 0
        assert result.summary.count(Severity.INFO) == 4

    def test_report_summary_tally_lines_are_not_events(self, fixture_log):
        # "UVM_ERROR :   0" at the end of a log is a count, not an error.
        result = parse(fixture_log, "uvm_pass.log")
        assert result.summary.count(Severity.ERROR) == 0
        assert result.summary.count(Severity.FATAL) == 0

    def test_event_fields_extracted(self, fixture_log):
        result = parse(fixture_log, "uvm_scoreboard.log")
        errors = [e for e in result.events if e.severity == Severity.ERROR]
        assert len(errors) == 2
        first = errors[0]
        assert first.component == "uvm_test_top.env.scb"
        assert first.message_id == "SCBD"
        assert first.sim_time == "55000"
        assert first.source_file == "/tb/scoreboard.sv"
        assert first.source_line == 142
        assert "expected data 0xDEAD" in first.message

    def test_test_name_and_simulator_detected(self, fixture_log):
        result = parse(fixture_log, "uvm_scoreboard.log")
        assert result.summary.test_name == "axi_random_test"
        assert result.summary.simulator == "Synopsys VCS"

    def test_assertion_failure_promoted(self, fixture_log):
        result = parse(fixture_log, "uvm_assertion.log")
        assertions = [f for f in result.failures if isinstance(f, AssertionFailure)]
        assert assertions, "expected an AssertionFailure"
        assert assertions[0].assertion_path == "a_valid_stable"

    def test_last_sim_time_tracked(self, fixture_log):
        result = parse(fixture_log, "uvm_assertion.log")
        assert result.summary.last_sim_time == "106000"


class TestOtherFormats:
    def test_questa_transcript(self, fixture_log):
        result = parse(fixture_log, "questa_fatal.log")
        assert result.summary.simulator == "Siemens Questa"
        assert result.summary.count(Severity.FATAL) == 1
        assert result.summary.count(Severity.WARNING) == 1
        fatal = next(e for e in result.events if e.severity == Severity.FATAL)
        assert fatal.message_id == "vsim-3601"

    def test_vcs_compile_errors(self, fixture_log):
        result = parse(fixture_log, "vcs_compile_error.log")
        assert result.summary.count(Severity.ERROR) == 2
        codes = {e.message_id for e in result.failing_events}
        assert codes == {"SE", "UD"}


class TestRegistry:
    def test_simulation_log_parser_registered(self):
        assert "simulation_log" in available_parsers()

    def test_find_parser_by_pattern(self, tmp_path: Path):
        log = tmp_path / "simulation.log"
        log.write_text("UVM_INFO @ 0: reporter [X] hello\n")
        assert isinstance(find_parser(log), SimulationLogParser)

    def test_get_parser_unknown_name_raises(self):
        with pytest.raises(KeyError, match="Unknown parser"):
            get_parser("waveform")

    def test_new_parser_plugs_in_without_touching_existing_code(self, tmp_path: Path):
        @register
        class CoverageParser(Parser):
            name = "test_coverage"
            file_patterns = ("coverage.txt",)

            def parse(self, path):  # pragma: no cover - never called here
                raise NotImplementedError

        try:
            assert "test_coverage" in available_parsers()
            cov = tmp_path / "coverage.txt"
            cov.write_text("")
            assert isinstance(find_parser(cov), CoverageParser)
        finally:
            # Keep the global registry clean for other tests.
            from traceiq.parsers.registry import _REGISTRY

            _REGISTRY.pop("test_coverage", None)

    def test_duplicate_name_rejected(self):
        with pytest.raises(ValueError, match="already registered"):
            @register
            class Impostor(Parser):  # noqa: F841
                name = "simulation_log"

                def parse(self, path):  # pragma: no cover
                    raise NotImplementedError
