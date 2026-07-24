"""The Engineering Context Engine: normalized context to evidence and views.

Tool-agnostic by construction: this module consumes only
:class:`EngineeringContext` and the Evidence Graph. It imports no provider,
runs no subprocess, and never names an engineering tool. That is pinned by
``tests/test_engineering.py::test_engineering_core_is_tool_agnostic``.

Three jobs, all deterministic:

1. **Evidence emission.** ``emit_engineering_evidence`` projects the context
   into evidence nodes (``ArtifactType.ENGINEERING_CHANGE``): one per recent
   commit, one for the CI run. Ownership and issues deliberately do NOT
   become graph nodes: ownership must never sit in the evidence path that
   feeds ranking (it routes people, not verdicts), and issues are reference
   material, not observations.

2. **Ownership augment.** ``augment_with_ownership`` appends one extra
   recommendation naming the owner of a failing scope, additively, after
   reasoning completed: the same seam ``HistoryEngine.augment`` established.

3. **Report view.** ``build_engineering_view`` assembles the report's
   ``engineering`` section: commits with their correlated failures, CI info,
   ownership, impacted tests, honest capability gaps, the timeline, and the
   investigation projection.
"""

from __future__ import annotations

from veritriage.engineering.impact import impacted_tests_in_run
from veritriage.engineering.investigation import build_investigation
from veritriage.engineering.model import (
    Commit,
    ContextCapability,
    EngineeringContext,
)
from veritriage.engineering.ownership import ownership_recommendation
from veritriage.engineering.timeline import build_timeline
from veritriage.graph.builder import GraphFragment
from veritriage.graph.graph import EvidenceGraph
from veritriage.graph.model import (
    ArtifactType,
    EvidenceEdge,
    EvidenceNode,
    RelationType,
    make_node_id,
)
from veritriage.models import AnalysisReport, Severity
from veritriage.models.engineering import (
    ChangedFileView,
    CIRunView,
    CommitView,
    ContextUnavailableView,
    EngineeringContextView,
    IssueView,
    OwnershipView,
)

#: Analyses gated on provider capabilities, reported honestly when absent.
_CAPABILITY_GATED = (
    ("change-correlation", ContextCapability.CHANGED_FILES),
    ("ci-environment-analysis", ContextCapability.CI_RUNS),
    ("ownership-routing", ContextCapability.OWNERSHIP),
)


def _commit_node_id(commit: Commit) -> str:
    return make_node_id(ArtifactType.ENGINEERING_CHANGE.value, commit.source, commit.revision)


def _commit_description(commit: Commit) -> str:
    by_category: dict[str, int] = {}
    for file in commit.files:
        by_category[file.category.value] = by_category.get(file.category.value, 0) + 1
    summary = ", ".join(f"{n} {cat}" for cat, n in sorted(by_category.items()))
    author = f" by {commit.author}" if commit.author else ""
    files = f" ({summary} file{'s' if len(commit.files) != 1 else ''})" if summary else ""
    return f"Commit {commit.revision[:10]}{author}: {commit.title}{files}"


def emit_engineering_evidence(context: EngineeringContext) -> GraphFragment:
    """Project a normalized context into an Evidence Graph fragment.

    Deterministic: node IDs are content-hashed from (artifact type, source,
    revision), so the same context always produces the same fragment and a
    context arriving twice (manifest artifact plus injected collection)
    merges into identical nodes instead of duplicates.
    """
    nodes: list[EvidenceNode] = []
    edges: list[EvidenceEdge] = []

    previous: EvidenceNode | None = None
    # Oldest first, so PRECEDES edges read in causal order.
    for commit in sorted(
        context.commits, key=lambda c: (c.timestamp is not None, c.timestamp, c.revision)
    ):
        modules = sorted({m for f in commit.files for m in f.modules})
        node = EvidenceNode(
            id=_commit_node_id(commit),
            artifact_type=ArtifactType.ENGINEERING_CHANGE,
            description=_commit_description(commit),
            severity=None,
            confidence=commit.confidence,
            source_path=f"{commit.source}:{commit.revision}",
            module=None,
            attributes={
                "kind": "commit",
                "source": commit.source,
                "revision": commit.revision,
                "author": commit.author,
                "timestamp": commit.timestamp.isoformat() if commit.timestamp else None,
                "files": [f.path for f in commit.files],
                "categories": sorted({f.category.value for f in commit.files}),
                "modules": modules,
            },
        )
        nodes.append(node)
        if previous is not None:
            edges.append(
                EvidenceEdge(
                    source_id=previous.id,
                    target_id=node.id,
                    relation=RelationType.PRECEDES,
                    rationale="Earlier engineering change in the same history.",
                )
            )
        previous = node

    ci = context.ci_run
    if ci is not None:
        drifted = bool(ci.environment_changes)
        label = f"CI run {ci.pipeline or 'unknown'}" + (f" #{ci.build_number}" if ci.build_number else "")
        drift = (
            "; environment changed since the previous run: " + "; ".join(ci.environment_changes)
            if drifted
            else ""
        )
        nodes.append(
            EvidenceNode(
                id=make_node_id(ArtifactType.ENGINEERING_CHANGE.value, ci.source, "ci", ci.id),
                artifact_type=ArtifactType.ENGINEERING_CHANGE,
                description=f"{label}{drift}",
                # Declared environment drift is a warning-grade observation;
                # a stable environment is plain context.
                severity=Severity.WARNING if drifted else None,
                confidence=ci.confidence,
                source_path=f"{ci.source}:ci:{ci.id}",
                attributes={
                    "kind": "ci_run",
                    "source": ci.source,
                    "pipeline": ci.pipeline,
                    "build_number": ci.build_number,
                    "simulator": ci.simulator,
                    "compiler": ci.compiler,
                    "configuration": dict(ci.configuration),
                    "environment_changes": list(ci.environment_changes),
                },
            )
        )

    return GraphFragment(nodes=nodes, edges=edges)


def augment_with_ownership(
    report: AnalysisReport, graph: EvidenceGraph, context: EngineeringContext
) -> None:
    """Append one ownership-routing recommendation, additively.

    Mirrors ``HistoryEngine.augment``: appended after every existing step,
    never replacing or reordering anything reasoning produced. Ownership
    influences who to talk to, never which hypothesis wins.
    """
    if report.reasoning is None or not context.ownership:
        return
    recommendation = ownership_recommendation(report, graph, context.ownership)
    if recommendation is not None:
        recommendations = report.reasoning.recommendations
        recommendation.priority = max((r.priority for r in recommendations), default=0) + 1
        recommendations.append(recommendation)


def build_engineering_view(
    context: EngineeringContext,
    graph: EvidenceGraph,
    report: AnalysisReport,
) -> EngineeringContextView | None:
    """Assemble the report's engineering section from context plus the graph.

    Returns None when no context contributed, so the report field stays
    absent on context-free runs. Every statement in the view cites node IDs
    (correlated failures, timeline entries, investigation layers).
    """
    if context.is_empty:
        return None

    failing_ids = {n.id for n in graph.failing()}
    commit_views: list[CommitView] = []
    for commit in context.commits:
        node_id = _commit_node_id(commit)
        correlated = sorted(
            e.target_id
            for e in graph.edges_from(node_id)
            if e.relation == RelationType.CORRELATES_WITH and e.target_id in failing_ids
        ) if node_id in graph.nodes else []
        commit_views.append(
            CommitView(
                commit_id=commit.id,
                node_id=node_id if node_id in graph.nodes else None,
                revision=commit.revision,
                author=commit.author,
                timestamp=commit.timestamp.isoformat() if commit.timestamp else None,
                title=commit.title,
                source=commit.source,
                files=[
                    ChangedFileView(
                        path=f.path,
                        category=f.category.value,
                        lines_added=f.lines_added,
                        lines_deleted=f.lines_deleted,
                        modules=list(f.modules),
                    )
                    for f in commit.files
                ],
                correlated_failures=correlated,
            )
        )

    ci_view = None
    ci = context.ci_run
    if ci is not None:
        ci_node = make_node_id(ArtifactType.ENGINEERING_CHANGE.value, ci.source, "ci", ci.id)
        ci_view = CIRunView(
            node_id=ci_node if ci_node in graph.nodes else None,
            pipeline=ci.pipeline,
            build_number=ci.build_number,
            simulator=ci.simulator,
            compiler=ci.compiler,
            configuration=dict(ci.configuration),
            environment_changes=list(ci.environment_changes),
            source=ci.source,
        )

    unavailable = [
        ContextUnavailableView(
            analysis=name,
            required_capability=capability.value,
            sources=list(context.sources),
            reason=(
                f"no contributing provider ({', '.join(context.sources) or 'none'}) "
                f"resolves {capability.value}, so {name} could not run"
            ),
        )
        for name, capability in _CAPABILITY_GATED
        if capability not in context.capabilities
    ]

    return EngineeringContextView(
        sources=list(context.sources),
        capabilities=sorted(c.value for c in context.capabilities),
        commits=commit_views,
        ci_run=ci_view,
        ownership=[
            OwnershipView(scope=o.scope, role=o.role, owner=o.owner, source=o.source)
            for o in context.ownership
        ],
        issues=[
            IssueView(tracker_id=i.tracker_id, title=i.title, status=i.status, source=i.source)
            for i in context.issues
        ],
        impacted_tests=impacted_tests_in_run(context, graph),
        unavailable=unavailable,
        timeline=build_timeline(graph, report),
        investigation=build_investigation(graph, report),
    )


__all__ = [
    "augment_with_ownership",
    "build_engineering_view",
    "emit_engineering_evidence",
]
