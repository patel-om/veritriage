"""Self-contained HTML report renderer (Jinja2, no external assets)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, PackageLoader, select_autoescape

from veritriage.graph.graph import EvidenceGraph
from veritriage.models import AnalysisReport, FailureCategory, HypothesisCategory, Severity

#: Maps each failure category to a status role in the report's fixed status
#: palette. Status colors are always paired with a text label - never alone.
_STATUS_ROLE: dict[FailureCategory, str] = {
    FailureCategory.NO_FAILURE: "good",
    FailureCategory.UNKNOWN_FAILURE: "warning",
    FailureCategory.TIMEOUT: "serious",
    FailureCategory.TESTBENCH_FAILURE: "serious",
    FailureCategory.COMPILE_FAILURE: "critical",
    FailureCategory.ASSERTION_FAILURE: "critical",
    FailureCategory.FATAL_ERROR: "critical",
}

_HYPOTHESIS_ROLE: dict[HypothesisCategory, str] = {
    HypothesisCategory.RTL_BUG: "critical",
    HypothesisCategory.TESTBENCH_ISSUE: "serious",
    HypothesisCategory.BUILD_ISSUE: "warning",
    HypothesisCategory.INFRASTRUCTURE_ISSUE: "muted",
}

#: Column order for the evidence-graph drawing, by artifact type value.
_COLUMN_ORDER = (
    "engineering_change",
    "compile_log",
    "simulation_log",
    "assertion",
    "coverage",
    "test_metadata",
    "waveform_metadata",
)

_MAX_DRAWN_NODES = 24

#: Pattern-ownership label prefix -> status role for the report chip.
_OWNERSHIP_ROLE = {
    "design": "critical",
    "testbench": "serious",
    "build": "warning",
    "infrastructure": "muted",
}

#: Evidence severity value -> status role for the waveform observation chips.
_SEVERITY_ROLE = {
    "fatal": "critical",
    "error": "serious",
    "warning": "warning",
    "info": "muted",
}


class HtmlReportGenerator:
    """Renders an :class:`AnalysisReport` into a single self-contained HTML file."""

    def __init__(self) -> None:
        self._env = Environment(
            loader=PackageLoader("veritriage.reports", "templates"),
            autoescape=select_autoescape(("html", "j2")),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self, report: AnalysisReport, graph: EvidenceGraph | None = None) -> str:
        """Render the report to an HTML string.

        Args:
            report: The analysis to render.
            graph: When provided, the working-set evidence graph is drawn as
                an inline SVG; without it the section shows stats only.
        """
        ownership_roles = {}
        if report.knowledge is not None:
            ownership_roles = {
                p.pattern_id: _OWNERSHIP_ROLE.get(p.ownership.split(" ")[0], "muted")
                for p in report.knowledge.patterns
            }
        template = self._env.get_template("report.html.j2")
        return template.render(
            report=report,
            ownership_roles=ownership_roles,
            waveform_severity_role=_SEVERITY_ROLE,
            status_role=_STATUS_ROLE.get(report.classification.category, "warning"),
            hypothesis_role=_HYPOTHESIS_ROLE,
            fatal_count=report.summary.count(Severity.FATAL),
            error_count=report.summary.count(Severity.ERROR),
            warning_count=report.summary.count(Severity.WARNING),
            assertion_count=sum(1 for f in report.failures if f.kind == "assertion_failure"),
            graph_viz=_layout_working_set(report, graph) if graph is not None else None,
        )

    def write(
        self, report: AnalysisReport, path: Path, graph: EvidenceGraph | None = None
    ) -> Path:
        """Render and write the report to ``path``; returns the path written."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.render(report, graph=graph), encoding="utf-8")
        return path


def _layout_working_set(
    report: AnalysisReport, graph: EvidenceGraph
) -> dict[str, Any] | None:
    """Deterministic column layout of the working-set subgraph for inline SVG.

    Nodes are grouped into columns by artifact type and stacked in working-set
    order; edges connect node centers. No JavaScript, no external assets.
    """
    if report.reasoning is None or not report.reasoning.working_set.items:
        return None
    node_ids = report.reasoning.working_set.node_ids[:_MAX_DRAWN_NODES]
    nodes = [graph.nodes[i] for i in node_ids if i in graph.nodes]
    if not nodes:
        return None

    present_types = [t for t in _COLUMN_ORDER if any(n.artifact_type.value == t for n in nodes)]
    col_width, row_height, top = 200, 58, 46
    columns = [
        {"x": 30 + i * col_width, "label": t.replace("_", " ")}
        for i, t in enumerate(present_types)
    ]
    col_x = {t: 30 + i * col_width for i, t in enumerate(present_types)}

    placed: dict[str, dict[str, Any]] = {}
    rows_used: dict[str, int] = {}
    for node in nodes:
        t = node.artifact_type.value
        row = rows_used.get(t, 0)
        rows_used[t] = row + 1
        if node.severity is not None and node.severity.value in ("error", "fatal"):
            color = "critical" if node.severity.value == "fatal" else "serious"
        elif node.severity is not None and node.severity.value == "warning":
            color = "warning"
        else:
            color = "muted"
        if node.artifact_type.value == "assertion":
            color = "critical"
        where = f" line {node.line_number}" if node.line_number else ""
        placed[node.id] = {
            "id": node.id,
            "x": col_x[t] + 14,
            "y": top + row * row_height,
            "color": color,
            "label": node.id.removeprefix("ev-"),
            "tooltip": f"[{node.id}]{where}: {node.description[:140]}",
        }

    edges = []
    for edge in graph.edges:
        src, dst = placed.get(edge.source_id), placed.get(edge.target_id)
        if src is None or dst is None:
            continue
        edges.append(
            {
                "x1": src["x"],
                "y1": src["y"],
                "x2": dst["x"],
                "y2": dst["y"],
                "relation": edge.relation.value.replace("_", " "),
                "tooltip": f"{edge.relation.value}: {edge.rationale}",
                "dashed": edge.relation.value == "correlates_with",
            }
        )

    width = 30 + len(present_types) * col_width
    height = top + max(rows_used.values(), default=0) * row_height + 20
    return {"width": width, "height": height, "columns": columns, "nodes": list(placed.values()), "edges": edges}
