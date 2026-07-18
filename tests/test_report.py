"""Report tests: JSON round-trip and HTML rendering."""

from __future__ import annotations

from veritriage.models import AnalysisReport
from veritriage.pipeline import analyze
from veritriage.reports import HtmlReportGenerator


def test_json_round_trip(fixture_log):
    report = analyze(fixture_log("uvm_scoreboard.log")).report
    restored = AnalysisReport.model_validate_json(report.model_dump_json())
    assert restored == report


def test_html_contains_all_sections(fixture_log, tmp_path):
    report = analyze(
        [fixture_log("uvm_scoreboard.log"), fixture_log("coverage.txt")]
    ).report
    html_path = HtmlReportGenerator().write(report, tmp_path / "report.html")
    html = html_path.read_text(encoding="utf-8")

    for section in (
        "Regression Summary",
        "Evidence Graph",
        "Failure Classification",
        "Confidence",
        "Evidence Timeline",
        "Relevant Log Snippets",
        "Suggested Next Steps",
        "Waveform",
    ):
        assert section in html, f"missing section: {section}"

    assert "Testbench Failure" in html
    assert "80%" in html
    assert "axi_random_test" in html
    assert "evidence_graph.json" in html
    assert "correlates with" in html  # cross-artifact edge surfaced in stats


def test_html_escapes_log_content(tmp_path):
    # Log content is untrusted; markup in messages must not become live HTML.
    log = tmp_path / "evil.log"
    log.write_text('Error: <script>alert("x")</script> in packet\n')
    report = analyze(log).report
    html = HtmlReportGenerator().render(report)
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html


def test_clean_run_renders_without_evidence_sections(fixture_log):
    report = analyze(fixture_log("uvm_pass.log")).report
    html = HtmlReportGenerator().render(report)
    assert "No Failure" in html
    assert "Evidence Timeline" not in html


def test_ai_summary_section_rendered_when_present(fixture_log):
    report = analyze(fixture_log("uvm_assertion.log")).report
    report.ai_summary = "The assertion a_valid_stable fired at t=105000 (ev-abc)."
    html = HtmlReportGenerator().render(report)
    assert "AI Summary" in html
    assert "a_valid_stable fired" in html


def test_report_carries_graph_stats(fixture_log):
    report = analyze(
        [fixture_log("uvm_scoreboard.log"), fixture_log("test_metadata.json")]
    ).report
    stats = report.graph_stats
    assert stats.node_count > 0
    assert stats.nodes_by_type.get("test_metadata") == 1
    assert stats.edges_by_relation.get("part_of", 0) >= 1
