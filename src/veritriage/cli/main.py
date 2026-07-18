"""``veritriage`` command-line interface (Typer + Rich)."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

import veritriage
from veritriage.analyzers import AISummarizer, AISummaryError
from veritriage.models import AnalysisReport, Severity
from veritriage.parsers import available_parsers
from veritriage.pipeline import analyze as run_analysis
from veritriage.reports import HtmlReportGenerator
from veritriage.utils import write_json

app = typer.Typer(
    name="veritriage",
    help="VeriTriage - turn verification artifacts into evidence-backed root-cause reports.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
_err = Console(stderr=True)


@app.command()
def analyze(
    artifacts: List[Path] = typer.Argument(
        ...,
        help="Artifacts to analyze together: simulation log, compile log, coverage summary, test metadata.",
    ),
    output_dir: Path = typer.Option(
        Path("."),
        "--output-dir",
        "-o",
        help="Directory for analysis.json, evidence_graph.json, and report.html.",
    ),
    parser: Optional[str] = typer.Option(
        None, "--parser", help="Force one registered parser for every artifact instead of auto-detecting."
    ),
    ai: bool = typer.Option(
        False, "--ai/--no-ai", help="Also generate an AI summary (requires 'pip install veritriage[ai]')."
    ),
    ai_model: str = typer.Option(
        "claude-opus-4-8", "--ai-model", help="Claude model to use for the AI summary."
    ),
) -> None:
    """Analyze verification artifacts into an evidence graph and reports."""
    try:
        outcome = run_analysis(artifacts, parser_name=parser)
    except (FileNotFoundError, ValueError) as exc:
        _err.print(f"[red]error:[/red] {escape(str(exc))}")
        raise typer.Exit(code=2)
    except KeyError as exc:
        _err.print(f"[red]error:[/red] {escape(str(exc.args[0]))}")
        raise typer.Exit(code=2)
    report, graph = outcome

    if ai:
        try:
            report.ai_summary = AISummarizer(model=ai_model).summarize(report, graph)
        except AISummaryError as exc:
            # AI is optional by design: warn and continue with the deterministic report.
            _err.print(f"[yellow]warning:[/yellow] AI summary skipped - {escape(str(exc))}")

    json_path = write_json(report, output_dir / "analysis.json")
    graph_path = write_json(graph, output_dir / "evidence_graph.json")
    html_path = HtmlReportGenerator().write(report, output_dir / "report.html")

    _print_summary(report)
    console.print(f"\n[dim]wrote[/dim] {json_path}")
    console.print(f"[dim]wrote[/dim] {graph_path}")
    console.print(f"[dim]wrote[/dim] {html_path}")

    # Non-zero exit when the run failed, so CI can gate on it.
    if report.classification.category.value != "no_failure":
        raise typer.Exit(code=1)


@app.command()
def parsers() -> None:
    """List registered parsers."""
    table = Table(title="Registered parsers")
    table.add_column("Name")
    table.add_column("Artifact type")
    table.add_column("File patterns")
    for name, cls in sorted(available_parsers().items()):
        table.add_row(name, cls.artifact_type.value, ", ".join(cls.file_patterns) or "-")
    console.print(table)


@app.command()
def version() -> None:
    """Print the VeriTriage version."""
    console.print(f"veritriage {veritriage.__version__}")


def _print_summary(report: AnalysisReport) -> None:
    """Render the terminal summary panel for an analysis."""
    c = report.classification
    counts = Table.grid(padding=(0, 2))
    counts.add_column(style="bold")
    counts.add_column()
    for label, severity in (
        ("Fatals", Severity.FATAL),
        ("Errors", Severity.ERROR),
        ("Warnings", Severity.WARNING),
    ):
        counts.add_row(label, str(report.summary.count(severity)))
    counts.add_row("Evidence nodes", str(report.graph_stats.node_count))
    counts.add_row("Evidence edges", str(report.graph_stats.edge_count))

    body = Table.grid(padding=(0, 1))
    body.add_column()
    body.add_row(f"[bold]{c.category.display_name}[/bold]  |  confidence {c.confidence}%")
    body.add_row(f"[dim]{escape(c.summary)}  (rule: {c.rule_name})[/dim]")
    body.add_row("")
    body.add_row(counts)
    if c.evidence:
        body.add_row("")
        body.add_row("[bold]Evidence[/bold]")
        for ev in c.evidence:
            where = f"line {ev.line_number}" if ev.line_number else ""
            when = f"t={ev.sim_time}" if ev.sim_time else ""
            node = ev.node_id or ""
            loc = " ".join(x for x in (when, where, node) if x)
            body.add_row(f"  • {escape(ev.description)}" + (f"  [dim]({loc})[/dim]" if loc else ""))
    if c.recommendations:
        body.add_row("")
        body.add_row("[bold]Next steps[/bold]")
        for i, rec in enumerate(sorted(c.recommendations, key=lambda r: r.priority), start=1):
            body.add_row(f"  {i}. {escape(rec.action)}")

    title = report.summary.test_name or Path(report.input_files[0]).name
    console.print(Panel(body, title=f"VeriTriage · {title}", border_style="blue"))


if __name__ == "__main__":
    app()
