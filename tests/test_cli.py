"""CLI tests: end-to-end `traceiq analyze` producing all artifacts."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from traceiq.cli.main import app

runner = CliRunner()


def test_analyze_writes_json_and_html(fixture_log, tmp_path):
    result = runner.invoke(
        app, ["analyze", str(fixture_log("uvm_scoreboard.log")), "-o", str(tmp_path)]
    )
    # Failing run → exit code 1 by design (CI gating), but artifacts exist.
    assert result.exit_code == 1, result.output

    data = json.loads((tmp_path / "analysis.json").read_text())
    assert data["classification"]["category"] == "testbench_failure"
    assert data["classification"]["confidence"] == 80
    assert data["classification"]["evidence"]

    html = (tmp_path / "report.html").read_text()
    assert "Failure Classification" in html

    assert "Testbench Failure" in result.output


def test_analyze_clean_log_exits_zero(fixture_log, tmp_path):
    result = runner.invoke(app, ["analyze", str(fixture_log("uvm_pass.log")), "-o", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "analysis.json").is_file()


def test_analyze_missing_file_errors(tmp_path):
    result = runner.invoke(app, ["analyze", str(tmp_path / "nope.log"), "-o", str(tmp_path)])
    assert result.exit_code == 2


def test_parsers_command_lists_simulation_log():
    result = runner.invoke(app, ["parsers"])
    assert result.exit_code == 0
    assert "simulation_log" in result.output


def test_version_command():
    import traceiq

    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert traceiq.__version__ in result.output
