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
from veritriage.models import AnalysisReport, Severity
from veritriage.reasoning import AIReasoner, AIReasoningError
from veritriage.parsers import available_parsers
from veritriage.reports import HtmlReportGenerator
from veritriage.utils import write_json

# The CLI is a client of the workspace service layer (M8): investigation
# logic lives in WorkspaceServices, shared verbatim with the MCP server.
# Nothing here may import veritriage.pipeline directly; an architecture test
# in tests/test_workspace.py pins that.
from veritriage.workspace import WorkspaceServices

#: Default location of the regression database, relative to the working tree.
DEFAULT_DB = Path(".veritriage") / "regressions.db"

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
        False, "--ai/--no-ai", help="Also run the AI review stage (requires 'pip install veritriage[ai]')."
    ),
    ai_model: str = typer.Option(
        "claude-opus-4-8", "--ai-model", help="Claude model to use for the AI review."
    ),
    history: bool = typer.Option(
        True,
        "--history/--no-history",
        help="Record this run in the regression database and attach historical context.",
    ),
    context: bool = typer.Option(
        True,
        "--context/--no-context",
        help="Gather engineering context (recent commits, manifests) from the context root.",
    ),
    context_root: Path = typer.Option(
        Path("."), "--context-root", help="Directory the context providers inspect."
    ),
    db: Path = typer.Option(
        DEFAULT_DB, "--db", help="Regression database file (created on first use)."
    ),
) -> None:
    """Analyze verification artifacts into an evidence graph and reports."""
    engineering = _gather_context(context_root) if context else None
    try:
        session = WorkspaceServices(db=db).investigate(
            artifacts,
            parser_name=parser,
            engineering=engineering,
            record_history=history,
        )
    except (FileNotFoundError, ValueError) as exc:
        _err.print(f"[red]error:[/red] {escape(str(exc))}")
        raise typer.Exit(code=2)
    except KeyError as exc:
        _err.print(f"[red]error:[/red] {escape(str(exc.args[0]))}")
        raise typer.Exit(code=2)
    report, graph = session.report, session.graph

    if ai and report.reasoning is not None:
        try:
            review = AIReasoner(model=ai_model).review(graph, report.reasoning)
            report.reasoning.ai_review = review
            report.ai_summary = review.narrative
            for hypothesis in report.reasoning.hypotheses:
                note = review.hypothesis_notes.get(hypothesis.id)
                if note:
                    hypothesis.ai_note = note
        except AIReasoningError as exc:
            # AI is optional by design: warn and continue with the deterministic result.
            _err.print(f"[yellow]warning:[/yellow] AI review skipped - {escape(str(exc))}")

    json_path = write_json(report, output_dir / "analysis.json")
    graph_path = write_json(graph, output_dir / "evidence_graph.json")
    html_path = HtmlReportGenerator().write(report, output_dir / "report.html", graph=graph)

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
def knowledge() -> None:
    """List loaded Knowledge Packs and what each one teaches."""
    from veritriage.knowledge import load_packs

    table = Table(title="Knowledge Packs")
    for column in ("Pack", "Version", "Domain", "Concepts", "Patterns", "Playbooks", "FSMs"):
        table.add_column(column)
    for pack in load_packs():
        table.add_row(
            f"{pack.name} ({pack.id})",
            pack.version,
            pack.domain,
            str(len(pack.concepts)),
            str(len(pack.patterns)),
            str(len(pack.playbooks)),
            str(len(pack.state_machines)),
        )
    console.print(table)


@app.command()
def waveform() -> None:
    """List registered waveform adapters and the formats they resolve."""
    from veritriage.waveform import available_adapters

    table = Table(title="Waveform adapters")
    for column in ("Adapter", "Format", "File patterns", "Capabilities"):
        table.add_column(column)
    for name, cls in sorted(available_adapters().items()):
        table.add_row(
            name,
            cls.format,
            ", ".join(cls.file_patterns) or "-",
            ", ".join(sorted(c.value for c in cls.capabilities)) or "-",
        )
    console.print(table)


@app.command()
def mcp(
    session_root: Path = typer.Option(
        None, "--session-root", help="Sessions directory (default .veritriage/sessions)."
    ),
    db: Path = typer.Option(DEFAULT_DB, "--db", help="Regression database file."),
) -> None:
    """Serve VeriTriage as an MCP tool server over stdio.

    Point an MCP host (Claude Code, an IDE) at `veritriage mcp` and it can
    analyze regressions, walk evidence, search knowledge, and query history
    through the same services the CLI uses.
    """
    from veritriage.mcp import McpStdioServer

    services = WorkspaceServices(session_root=session_root, db=db)
    McpStdioServer(services).serve_forever()


@app.command()
def sessions(
    session_root: Path = typer.Option(
        None, "--session-root", help="Sessions directory (default .veritriage/sessions)."
    ),
) -> None:
    """List persisted investigation sessions."""
    services = WorkspaceServices(session_root=session_root)
    stored = services.list_sessions()
    if not stored:
        console.print("[dim]no sessions stored yet; run `veritriage investigate`[/dim]")
        return
    table = Table(title=f"Investigation sessions ({len(stored)})")
    for column in ("Session", "Created", "Classification", "Confidence", "Test", "Inputs"):
        table.add_column(column)
    for summary in stored:
        table.add_row(
            summary.session_id,
            summary.created_at[:16],
            summary.classification,
            f"{summary.confidence}%",
            summary.test_name or "-",
            str(len(summary.input_files)),
        )
    console.print(table)


@app.command()
def run(
    profile: str = typer.Argument(..., help="Investigation profile, e.g. fast-triage."),
    artifacts: List[Path] = typer.Argument(..., help="Artifacts to investigate."),
    context_root: Path = typer.Option(
        Path("."), "--context-root", help="Directory the context providers inspect."
    ),
    output_dir: Optional[Path] = typer.Option(
        None, "--output-dir", "-o", help="Report output directory (profiles with render-report)."
    ),
    session_root: Path = typer.Option(
        None, "--session-root", help="Sessions directory (default .veritriage/sessions)."
    ),
    db: Path = typer.Option(DEFAULT_DB, "--db", help="Regression database file."),
) -> None:
    """Run one orchestrated investigation profile end to end."""
    from veritriage.orchestrator import run_profile

    services = WorkspaceServices(session_root=session_root, db=db)
    try:
        session = run_profile(
            services, profile, artifacts, context_root=context_root, output_dir=output_dir
        )
    except KeyError as exc:
        _err.print(f"[red]error:[/red] {escape(str(exc.args[0]))}")
        raise typer.Exit(code=2)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        _err.print(f"[red]error:[/red] {escape(str(exc))}")
        raise typer.Exit(code=2)

    _print_summary(session.report)
    trace = session.trace
    table = Table(title=f"Investigation trace ({trace.profile}, plan {session.plan.plan_id})")
    for column in ("Step", "Status", "Attempts", "Duration", "Produced"):
        table.add_column(column)
    for step in trace.steps:
        table.add_row(
            step.step_id,
            step.status.value,
            str(step.attempts),
            f"{step.duration_ms:.0f} ms" if step.duration_ms is not None else "-",
            ", ".join(step.produced) or "-",
        )
    console.print(table)
    for entry in trace.attribution:
        console.print(
            f"[dim]{entry.subsystem}:[/dim] {len(entry.signals)} signal"
            f"{'s' if len(entry.signals) != 1 else ''}, {entry.recommendations} recommendation"
            f"{'s' if entry.recommendations != 1 else ''}"
        )
    console.print(
        f"[dim]session[/dim] [bold]{session.session_id}[/bold]"
        + (f"  [dim]total[/dim] {trace.total_duration_ms:.0f} ms" if trace.total_duration_ms else "")
    )
    if not trace.completed:
        _err.print("[yellow]warning:[/yellow] investigation completed partially; see the trace")
    if session.report.classification.category.value != "no_failure":
        raise typer.Exit(code=1)


@app.command()
def profiles() -> None:
    """List registered investigation profiles and their steps."""
    from veritriage.orchestrator import available_profiles

    table = Table(title="Investigation profiles")
    for column in ("Profile", "Steps", "Description"):
        table.add_column(column)
    for name, profile in sorted(available_profiles().items()):
        table.add_row(name, " -> ".join(s.id for s in profile.steps), profile.description)
    console.print(table)


def _gather_context(root: Path):
    """Collect engineering context from every available provider, best-effort.

    Returns None when nothing contributed so the pipeline's report keeps its
    ``engineering`` field absent instead of empty.
    """
    from veritriage.engineering import collect_context

    gathered = collect_context(root)
    return None if gathered.is_empty else gathered


@app.command()
def context(
    root: Path = typer.Option(Path("."), "--root", help="Directory the providers inspect."),
    commits: int = typer.Option(10, "--commits", "-n", help="How many recent commits to gather."),
) -> None:
    """Show the normalized engineering context the providers see for a root."""
    from veritriage.engineering import available_providers, collect_context

    table = Table(title="Context providers")
    for column in ("Provider", "Source", "Available here", "Capabilities"):
        table.add_column(column)
    for name, cls in sorted(available_providers().items()):
        table.add_row(
            name,
            cls.source,
            "yes" if cls.available(root) else "no",
            ", ".join(sorted(c.value for c in cls.capabilities)) or "-",
        )
    console.print(table)

    gathered = collect_context(root, max_commits=commits)
    if gathered.is_empty:
        console.print("[dim]no engineering context available at this root[/dim]")
        return
    changes = Table(title=f"Recent changes ({', '.join(gathered.sources)})")
    for column in ("Revision", "Author", "When", "Title", "Files"):
        changes.add_column(column)
    for commit in gathered.commits:
        changes.add_row(
            commit.revision[:10],
            commit.author or "-",
            commit.timestamp.strftime("%Y-%m-%d %H:%M") if commit.timestamp else "-",
            commit.title,
            str(len(commit.files)),
        )
    console.print(changes)
    if gathered.ci_run is not None:
        ci = gathered.ci_run
        drift = "; ".join(ci.environment_changes) or "none declared"
        console.print(
            f"CI: [bold]{ci.pipeline or 'unknown'}[/bold]"
            + (f" #{ci.build_number}" if ci.build_number else "")
            + f"  |  environment drift: {escape(drift)}"
        )
    for entry in gathered.ownership:
        console.print(f"[dim]owner:[/dim] {escape(entry.scope)} -> {escape(entry.owner)} ({entry.role})")


@app.command()
def investigate(
    artifacts: List[Path] = typer.Argument(..., help="Artifacts to analyze with full context."),
    context_root: Path = typer.Option(
        Path("."), "--context-root", help="Directory the context providers inspect."
    ),
    output_dir: Optional[Path] = typer.Option(
        None, "--output-dir", "-o", help="Also write analysis.json / report.html here."
    ),
) -> None:
    """Analyze with engineering context and print the investigation view."""
    engineering = _gather_context(context_root)
    services = WorkspaceServices()
    try:
        session = services.investigate(artifacts, engineering=engineering)
    except (FileNotFoundError, ValueError) as exc:
        _err.print(f"[red]error:[/red] {escape(str(exc))}")
        raise typer.Exit(code=2)
    report, graph = session.report, session.graph
    bundle = services.save(session)
    _print_summary(report)
    console.print(
        f"[dim]session[/dim] [bold]{session.session_id}[/bold] [dim]saved to[/dim] {bundle}"
    )

    view = report.engineering
    if view is None:
        console.print("[dim]no engineering context contributed to this run[/dim]")
    else:
        if view.timeline:
            timeline = Table(title="Engineering timeline")
            for column in ("Phase", "When", "Event", "Evidence"):
                timeline.add_column(column)
            for event in view.timeline:
                timeline.add_row(
                    event.phase, event.when or "-", event.label, event.node_id or "-"
                )
            console.print(timeline)
        if view.investigation is not None:
            layers = Table(title="Investigation view (Evidence Graph projection)")
            for column in ("Layer", "Nodes", "IDs"):
                layers.add_column(column)
            for layer in view.investigation.layers:
                layers.add_row(
                    layer.name, str(len(layer.node_ids)), ", ".join(layer.node_ids[:4])
                )
            console.print(layers)
            for edge in view.investigation.cross_edges[:8]:
                console.print(
                    f"[dim]{edge.source_id} -{edge.relation}-> {edge.target_id}:[/dim] "
                    f"{escape(edge.rationale)}"
                )

    if output_dir is not None:
        write_json(report, output_dir / "analysis.json")
        write_json(graph, output_dir / "evidence_graph.json")
        HtmlReportGenerator().write(report, output_dir / "report.html", graph=graph)
        console.print(f"\n[dim]wrote artifacts to[/dim] {output_dir}")

    if report.classification.category.value != "no_failure":
        raise typer.Exit(code=1)


@app.command()
def impact(
    context_root: Path = typer.Option(
        Path("."), "--context-root", help="Directory the context providers inspect."
    ),
    limit: int = typer.Option(10, "--limit", "-n", help="How many impacted tests to show."),
    db: Path = typer.Option(DEFAULT_DB, "--db", help="Regression database file."),
) -> None:
    """Rank tests likely affected by the current changes, from history."""
    from veritriage.engineering import HistoricalRegression, impacted_tests_from_history
    from veritriage.storage import RegressionStore

    engineering = _gather_context(context_root)
    if engineering is None or not engineering.changed_modules():
        console.print("[dim]no changed modules found at this root; nothing to rank[/dim]")
        return
    if not db.is_file():
        _err.print(f"[red]error:[/red] no regression database at {db}; run an analysis first")
        raise typer.Exit(code=2)

    with RegressionStore(db) as store:
        history_slices = [
            HistoricalRegression(
                regression_id=record.regression_id,
                test_name=record.test_name,
                failing_modules=tuple(
                    sorted(
                        {
                            token
                            for node in record.graph.failing()
                            for token in (
                                node.module or "",
                                str(node.attributes.get("source_file") or ""),
                            )
                            if token
                        }
                    )
                ),
                classification=record.classification,
                created_at=record.created_at,
            )
            for record in store.all_records()
            if record.is_failure
        ]

    ranked = impacted_tests_from_history(engineering, history_slices, limit=limit)
    if not ranked:
        console.print("[dim]no historical failures overlap the changed modules[/dim]")
        return
    table = Table(title=f"Likely impacted tests ({len(engineering.changed_modules())} changed modules)")
    for column in ("Test", "Score", "Why", "Regressions"):
        table.add_column(column)
    for entry in ranked:
        table.add_row(
            entry.test_name,
            f"{entry.score:.2f}",
            entry.reason,
            ", ".join(entry.regression_ids[:3]),
        )
    console.print(table)


@app.command()
def dashboard(
    output_dir: Path = typer.Option(
        Path("."), "--output-dir", "-o", help="Directory for dashboard.html."
    ),
    db: Path = typer.Option(DEFAULT_DB, "--db", help="Regression database file."),
) -> None:
    """Render the regression-intelligence dashboard from the database."""
    from veritriage.dashboard import DashboardGenerator
    from veritriage.storage import RegressionStore

    if not db.is_file():
        _err.print(f"[red]error:[/red] no regression database at {db}; run an analysis first")
        raise typer.Exit(code=2)
    with RegressionStore(db) as store:
        path = DashboardGenerator(store).write(output_dir / "dashboard.html")
        console.print(f"[dim]wrote[/dim] {path}  ({store.count()} regressions)")


@app.command()
def history(
    limit: int = typer.Option(15, "--limit", "-n", help="How many regressions to show."),
    db: Path = typer.Option(DEFAULT_DB, "--db", help="Regression database file."),
) -> None:
    """List the most recent regressions in the database."""
    from veritriage.storage import RegressionStore

    if not db.is_file():
        _err.print(f"[red]error:[/red] no regression database at {db}; run an analysis first")
        raise typer.Exit(code=2)
    with RegressionStore(db) as store:
        table = Table(title=f"Regression history ({store.count()} total)")
        for column in ("When", "Regression", "Test", "Classification", "Confidence", "Signature"):
            table.add_column(column)
        for record in store.recent(limit=limit):
            table.add_row(
                record.created_at.strftime("%Y-%m-%d %H:%M"),
                record.regression_id,
                record.test_name or "-",
                record.report.classification.category.display_name,
                f"{record.confidence}%",
                record.signature.digest,
            )
        console.print(table)


@app.command()
def feedback(
    regression_id: str = typer.Argument(..., help="Regression ID the feedback applies to."),
    diagnosis: Optional[str] = typer.Option(
        None, "--diagnosis", help="Was the diagnosis right? 'correct' or 'incorrect'."
    ),
    root_cause: Optional[str] = typer.Option(
        None, "--root-cause", help="The confirmed actual root cause."
    ),
    useful: List[str] = typer.Option(
        [], "--useful", help="A recommendation action that helped (repeatable)."
    ),
    false: List[str] = typer.Option(
        [], "--false", help="A recommendation action that wasted time (repeatable)."
    ),
    note: Optional[str] = typer.Option(None, "--note", help="Free-form notes."),
    db: Path = typer.Option(DEFAULT_DB, "--db", help="Regression database file."),
) -> None:
    """Record engineer feedback on an analyzed regression."""
    from veritriage.feedback import FeedbackRecord
    from veritriage.storage import RegressionStore

    if diagnosis is not None and diagnosis not in ("correct", "incorrect"):
        _err.print("[red]error:[/red] --diagnosis must be 'correct' or 'incorrect'")
        raise typer.Exit(code=2)
    if not db.is_file():
        _err.print(f"[red]error:[/red] no regression database at {db}; run an analysis first")
        raise typer.Exit(code=2)
    with RegressionStore(db) as store:
        if store.get(regression_id) is None:
            _err.print(f"[red]error:[/red] unknown regression {escape(regression_id)}")
            raise typer.Exit(code=2)
        store.save_feedback(
            FeedbackRecord(
                regression_id=regression_id,
                diagnosis=diagnosis,  # type: ignore[arg-type]
                actual_root_cause=root_cause,
                useful_recommendations=list(useful),
                false_recommendations=list(false),
                notes=note,
            )
        )
        console.print(f"recorded feedback for [bold]{escape(regression_id)}[/bold]")


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
    if report.knowledge is not None and report.knowledge.patterns:
        body.add_row("")
        body.add_row("[bold]Known patterns[/bold]")
        for pattern in report.knowledge.patterns[:3]:
            body.add_row(
                f"  • {escape(pattern.name)}  [dim]{pattern.score:.0%} match "
                f"({pattern.pack} pack, owns: {escape(pattern.ownership)})[/dim]"
            )
        if report.knowledge.state_projection and report.knowledge.state_projection.stopped_at:
            sp = report.knowledge.state_projection
            reached = " -> ".join(s.state for s in sp.states if s.reached)
            body.add_row(
                f"  [dim]{escape(sp.name)}: {escape(reached)} -> "
                f"stopped before {escape(sp.stopped_at)}[/dim]"
            )
    if report.history is not None:
        body.add_row("")
        h = report.history
        if h.seen_before:
            best = next((s for s in h.similar if s.signature_match), None)
            seen = f"[bold]Seen before:[/bold] yes, {h.times_seen} prior run{'s' if h.times_seen != 1 else ''} with this exact signature"
            body.add_row(seen)
            if best is not None:
                body.add_row(
                    f"  [dim]last: {best.regression_id} · {escape(best.root_cause)}[/dim]"
                )
        elif h.similar:
            top = h.similar[0]
            body.add_row(
                f"[bold]Seen before:[/bold] not exactly; closest is {top.regression_id} "
                f"[dim]({top.score:.0%} similar, {escape(top.root_cause)})[/dim]"
            )
        elif report.classification.category.value != "no_failure":
            body.add_row("[bold]Seen before:[/bold] no, this failure is new to the database")
    if report.reasoning is not None and report.reasoning.hypotheses:
        body.add_row("")
        body.add_row("[bold]Hypotheses[/bold]")
        for hypothesis in report.reasoning.hypotheses:
            pct = f"{hypothesis.confidence * 100:.0f}%"
            body.add_row(
                f"  • {escape(hypothesis.title)}  [dim]{pct} "
                f"({len(hypothesis.evidence_ids)} evidence nodes)[/dim]"
            )
    steps = (
        report.reasoning.recommendations
        if report.reasoning is not None and report.reasoning.recommendations
        else None
    )
    if steps:
        body.add_row("")
        body.add_row("[bold]Next steps[/bold]")
        for rec in sorted(steps, key=lambda r: r.priority)[:4]:
            module = f" [{rec.module}]" if rec.module else ""
            body.add_row(
                f"  {rec.priority}. {escape(rec.action)}"
                f"  [dim](effort {rec.effort}{escape(module)})[/dim]"
            )
    elif c.recommendations:
        body.add_row("")
        body.add_row("[bold]Next steps[/bold]")
        for i, rec in enumerate(sorted(c.recommendations, key=lambda r: r.priority), start=1):
            body.add_row(f"  {i}. {escape(rec.action)}")

    title = report.summary.test_name or Path(report.input_files[0]).name
    console.print(Panel(body, title=f"VeriTriage · {title}", border_style="blue"))


if __name__ == "__main__":
    app()
