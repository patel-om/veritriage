"""Report-facing engineering context models (Milestone 7).

These are the normalized, serializable views embedded in the analysis report's
``engineering`` field. Like every model in this package, they are plain data
and import nothing from :mod:`veritriage.graph` or :mod:`veritriage.engineering`,
so the models package stays below the graph and engine layers.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChangedFileView(BaseModel):
    """One changed file as shown in the report."""

    path: str
    category: str
    lines_added: int = 0
    lines_deleted: int = 0
    modules: list[str] = Field(default_factory=list)


class CommitView(BaseModel):
    """One engineering change, with its evidence node and correlations."""

    commit_id: str
    node_id: str | None = Field(default=None, description="Evidence node this commit became.")
    revision: str
    author: str | None = None
    timestamp: str | None = None
    title: str
    source: str
    files: list[ChangedFileView] = Field(default_factory=list)
    correlated_failures: list[str] = Field(
        default_factory=list, description="Failing evidence node IDs this change correlates with."
    )


class CIRunView(BaseModel):
    """The CI execution context, when a provider supplied one."""

    node_id: str | None = None
    pipeline: str | None = None
    build_number: str | None = None
    simulator: str | None = None
    compiler: str | None = None
    configuration: dict[str, str] = Field(default_factory=dict)
    environment_changes: list[str] = Field(default_factory=list)
    source: str


class OwnershipView(BaseModel):
    """Who owns a scope; informs recommendations only, never ranking."""

    scope: str
    role: str
    owner: str
    source: str


class IssueView(BaseModel):
    """A linked ticket, reference material only."""

    tracker_id: str
    title: str
    status: str | None = None
    source: str


class ImpactedTestView(BaseModel):
    """One test judged likely affected by the current changes, with citations."""

    test_name: str
    score: float = Field(ge=0.0, le=1.0)
    reason: str
    changed_modules: list[str] = Field(default_factory=list)
    regression_ids: list[str] = Field(
        default_factory=list, description="Historical regressions this judgement derives from."
    )


class ContextUnavailableView(BaseModel):
    """An analysis skipped because no provider had the capability."""

    analysis: str
    required_capability: str
    sources: list[str] = Field(default_factory=list)
    reason: str


class TimelineEventView(BaseModel):
    """One event on the engineering timeline, in display order."""

    phase: str = Field(description="'change', 'ci', 'compile', 'simulation', 'waveform', 'knowledge'")
    label: str
    node_id: str | None = None
    when: str | None = Field(default=None, description="Timestamp or sim time, when known.")


class InvestigationLayerView(BaseModel):
    """One layer of the investigation projection."""

    name: str
    node_ids: list[str] = Field(default_factory=list)


class InvestigationEdgeView(BaseModel):
    """A cross-layer relationship in the investigation projection."""

    source_id: str
    target_id: str
    relation: str
    rationale: str


class InvestigationView(BaseModel):
    """A projection of the Evidence Graph grouped by intelligence layer.

    Not a new graph: every ID here is an Evidence Graph node ID, and building
    this view never mutates the graph.
    """

    layers: list[InvestigationLayerView] = Field(default_factory=list)
    cross_edges: list[InvestigationEdgeView] = Field(default_factory=list)


class EngineeringContextView(BaseModel):
    """The Engineering Context Engine's contribution to one report."""

    sources: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    commits: list[CommitView] = Field(default_factory=list)
    ci_run: CIRunView | None = None
    ownership: list[OwnershipView] = Field(default_factory=list)
    issues: list[IssueView] = Field(default_factory=list)
    impacted_tests: list[ImpactedTestView] = Field(default_factory=list)
    unavailable: list[ContextUnavailableView] = Field(default_factory=list)
    timeline: list[TimelineEventView] = Field(default_factory=list)
    investigation: InvestigationView | None = None

    @property
    def is_empty(self) -> bool:
        return not self.commits and self.ci_run is None and not self.ownership and not self.issues
