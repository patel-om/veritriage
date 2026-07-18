"""Self-contained HTML report renderer (Jinja2, no external assets)."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from traceiq.models import AnalysisReport, FailureCategory, Severity

#: Maps each failure category to a status role in the report's fixed status
#: palette. Status colors are always paired with a text label — never alone.
_STATUS_ROLE: dict[FailureCategory, str] = {
    FailureCategory.NO_FAILURE: "good",
    FailureCategory.UNKNOWN_FAILURE: "warning",
    FailureCategory.TIMEOUT: "serious",
    FailureCategory.TESTBENCH_FAILURE: "serious",
    FailureCategory.COMPILE_FAILURE: "critical",
    FailureCategory.ASSERTION_FAILURE: "critical",
    FailureCategory.FATAL_ERROR: "critical",
}


class HtmlReportGenerator:
    """Renders an :class:`AnalysisReport` into a single self-contained HTML file."""

    def __init__(self) -> None:
        self._env = Environment(
            loader=PackageLoader("traceiq.reports", "templates"),
            autoescape=select_autoescape(("html", "j2")),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, report: AnalysisReport) -> str:
        """Render the report to an HTML string."""
        template = self._env.get_template("report.html.j2")
        return template.render(
            report=report,
            status_role=_STATUS_ROLE.get(report.classification.category, "warning"),
            fatal_count=report.summary.count(Severity.FATAL),
            error_count=report.summary.count(Severity.ERROR),
            warning_count=report.summary.count(Severity.WARNING),
            assertion_count=sum(1 for f in report.failures if f.kind == "assertion_failure"),
        )

    def write(self, report: AnalysisReport, path: Path) -> Path:
        """Render and write the report to ``path``; returns the path written."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.render(report), encoding="utf-8")
        return path
