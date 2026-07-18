"""CLI tests: end-to-end `traceiq analyze` producing all artifacts."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from traceiq.cli.main import app

runner = CliRunner()


def test_analyze_writes_json_graph_and_html(fixture_log, tmp_path):
    result = runner.invoke(
        app, ["analyze", str(fixture_log("uvm_scoreboard.log")), "-o", str(tmp_path)]
    )
    # Failing run: exit code 1 by design (CI gating), but artifacts exist.
    assert result.exit_code == 1, result.output

    data = json.loads((tmp_path / "analysis.json").read_text())
    assert data["schema_version"] == "2"
    assert data["classification"]["category"] == "testbench_failure"
    assert data["classification"]["confidence"] == 80
    assert data["classification"]["evidence"]
    assert data["classification"]["evidence"][0]["node_id"].startswith("ev-")

    graph = json.loads((tmp_path / "evidence_graph.json").read_text())
    assert graph["nodes"]
    assert all(node_id.startswith("ev-") for node_id in graph["nodes"])

    html = (tmp_path / "report.html").read_text()
    assert "Failure Classification" in html
    assert "Evidence Graph" in html

    assert "Testbench Failure" in result.output


def test_analyze_multiple_artifacts(fixture_log, tmp_path):
    result = runner.invoke(
        app,
        [
            "analyze",
            str(fixture_log("uvm_scoreboard.log")),
            str(fixture_log("coverage.txt")),
            str(fixture_log("test_metadata.json")),
            "-o",
            str(tmp_path),
        ],
    )
    assert result.exit_code == 1, result.output
    graph = json.loads((tmp_path / "evidence_graph.json").read_text())
    types = {n["artifact_type"] for n in graph["nodes"].values()}
    assert {"simulation_log", "coverage", "test_metadata"} <= types
    relations = {e["relation"] for e in graph["edges"]}
    assert "part_of" in relations
    assert "correlates_with" in relations


def test_analyze_clean_log_exits_zero(fixture_log, tmp_path):
    result = runner.invoke(app, ["analyze", str(fixture_log("uvm_pass.log")), "-o", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "analysis.json").is_file()
    assert (tmp_path / "evidence_graph.json").is_file()


def test_analyze_missing_file_errors(tmp_path):
    result = runner.invoke(app, ["analyze", str(tmp_path / "nope.log"), "-o", str(tmp_path)])
    assert result.exit_code == 2


def test_parsers_command_lists_all_artifact_parsers():
    result = runner.invoke(app, ["parsers"])
    assert result.exit_code == 0
    for name in ("simulation_log", "compile_log", "coverage", "test_metadata"):
        assert name in result.output


def test_version_command():
    import traceiq

    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert traceiq.__version__ in result.output
