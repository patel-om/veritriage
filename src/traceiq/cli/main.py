"""``traceiq`` command-line interface (Typer + Rich)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

import traceiq
from traceiq.analyzers import AISummarizer, AISummaryError
from traceiq.models import AnalysisReport, Severity
from traceiq.parsers import available_parsers
from traceiq.pipeline import analyze as run_analysis
from traceiq.reports import HtmlReportGenerator
from traceiq.utils import write_json

app = typer.Typer(
    name="traceiq",
    help="TraceIQ - turn simulation logs into evidence-backed root-cause reports.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
_err = Console(stderr=True)


@app.command()
def analyze(
    log_file: Path = typer.Argument(..., help="Simulation log to analyze (e.g. simulation.log)."),
    output_dir: Path = typer.Option(
        Path("."), "--output-dir", "-o", help="Directory for analysis.json and report.html."
    ),
    parser: Optional[str] = typer.Option(
        None, "--parser", help="Force a registered parser instead of auto-detecting."
    ),
    ai: bool = typer.Option(
        False, "--ai/--no-ai", help="Also generate an AI summary (requires 'pip install traceiq[ai]')."
    ),
    ai_model: str = typer.Option(
        "claude-opus-4-8", "--ai-model", help="Claude model to use for the AI summary."
    ),
) -> None:
    """Analyze a simulation log and write analysis.json + report.html."""
    try:
        report = run_analysis(log_file, parser_name=parser)
    except FileNotFoundError as exc:
        _err.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=2)
    except KeyError as exc:
        _err.print(f"[red]error:[/red] {exc.args[0]}")
        raise typer.Exit(code=2)

    if ai:
        try:
            report.ai_summary = AISummarizer(model=ai_model).summarize(report)
        except AISummaryError as exc:
            # AI is optional by design: warn and continue with the deterministic report.
            _err.print(f"[yellow]warning:[/yellow] AI summary skipped - {escape(str(exc))}")

    json_path = write_json(report, output_dir / "analysis.json")
    html_path = HtmlReportGenerator().write(report, output_dir / "report.html")

    _print_summary(report)
    console.print(f"\n[dim]wrote[/dim] {json_path}")
    console.print(f"[dim]wrote[/dim] {html_path}")

    # Non-zero exit when the run failed, so CI can gate on it.
    if report.classification.category.value != "no_failure":
        raise typer.Exit(code=1)


@app.command()
def parsers() -> None:
    """List registered parsers."""
    table = Table(title="Registered parsers")
    table.add_column("Name")
    table.add_column("File patterns")
    for name, cls in sorted(available_parsers().items()):
        table.add_row(name, ", ".join(cls.file_patterns) or "-")
    console.print(table)


@app.command()
def version() -> None:
    """Print the TraceIQ version."""
    console.print(f"traceiq {traceiq.__version__}")


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

    body = Table.grid(padding=(0, 1))
    body.add_column()
    body.add_row(f"[bold]{c.category.display_name}[/bold]  -  confidence {c.confidence}%")
    body.add_row(f"[dim]{c.summary}  (rule: {c.rule_name})[/dim]")
    body.add_row("")
    body.add_row(counts)
    if c.evidence:
        body.add_row("")
        body.add_row("[bold]Evidence[/bold]")
        for ev in c.evidence:
            where = f"line {ev.line_number}" if ev.line_number else ""
            when = f"t={ev.sim_time}" if ev.sim_time else ""
            loc = " ".join(x for x in (when, where) if x)
            body.add_row(f"  • {ev.description}" + (f"  [dim]({loc})[/dim]" if loc else ""))
    if c.recommendations:
        body.add_row("")
        body.add_row("[bold]Next steps[/bold]")
        for i, rec in enumerate(sorted(c.recommendations, key=lambda r: r.priority), start=1):
            body.add_row(f"  {i}. {rec.action}")

    title = report.summary.test_name or Path(report.input_file).name
    console.print(Panel(body, title=f"TraceIQ · {title}", border_style="blue"))


if __name__ == "__main__":
    app()
