"""Design Intelligence vocabulary (Milestone 15).

The report-facing views of the Design Graph. Like every model in this package
these are plain data importing nothing from the graph or engine layers.

These are *views*, not the graph. The graph itself lives in
``veritriage.design`` and is referenced from here by node ID, so a report can
cite a structural element without carrying a copy of the structure.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class DesignNodeView(BaseModel):
    """One structural element, as shown in a report."""

    node_id: str
    kind: str
    name: str
    qualified_name: str | None = None
    owner: str | None = None
    protocol_id: str | None = None
    source_file: str | None = None


class DesignRelationView(BaseModel):
    """One typed relationship, with the field it was derived from."""

    source: str = Field(description="Source node name.")
    target: str = Field(description="Target node name.")
    relation: str
    rationale: str
    inferred: bool = False


class HierarchyRow(BaseModel):
    """One line of the instantiation tree."""

    depth: int = Field(ge=0)
    node_id: str
    name: str
    kind: str
    owner: str | None = None


class ClockDomainView(BaseModel):
    """A clock domain and the design it covers."""

    node_id: str
    name: str
    module_count: int = 0
    modules: list[str] = Field(default_factory=list)


class ClockCrossingView(BaseModel):
    """Two communicating modules that do not share a clock."""

    left: str
    right: str
    note: str


class VerificationTopologyView(BaseModel):
    """Who watches what, resolved through the graph rather than by name."""

    component: str
    type: str
    interface: str | None = None
    relation: str | None = Field(
        default=None, description="monitors / drives / predicts / connects."
    )


class RiskHotspot(BaseModel):
    """A structural risk, derived from the graph and never guessed."""

    kind: str = Field(description="e.g. 'unverified_module', 'clock_crossing'.")
    subject: str
    detail: str
    node_ids: list[str] = Field(default_factory=list)


class DesignContext(BaseModel):
    """Everything Design Intelligence concluded about one run's structure.

    Attached to the report as ``AnalysisReport.design``. Present only when a
    Project Model was supplied: the graph is derived from it, so no model means
    no structure to reason over.
    """

    project_id: str = ""
    graph_fingerprint: str = ""
    node_count: int = 0
    edge_count: int = 0
    stats: dict[str, int] = Field(default_factory=dict)

    affected_region: list[DesignNodeView] = Field(
        default_factory=list,
        description="The design neighbourhood around this run's failing scopes.",
    )
    affected_relations: list[DesignRelationView] = Field(
        default_factory=list, description="How the affected region hangs together."
    )
    relevant_modules: list[str] = Field(default_factory=list)
    verification_components: list[VerificationTopologyView] = Field(default_factory=list)
    clock_domains: list[ClockDomainView] = Field(default_factory=list)
    reset_domains: list[str] = Field(default_factory=list)
    clock_crossings: list[ClockCrossingView] = Field(default_factory=list)
    protocol_map: dict[str, list[str]] = Field(
        default_factory=dict, description="Protocol ID -> interfaces that speak it."
    )
    hierarchy: list[HierarchyRow] = Field(default_factory=list)
    dependencies: list[DesignRelationView] = Field(default_factory=list)
    risk_hotspots: list[RiskHotspot] = Field(default_factory=list)
    extractors: list[str] = Field(
        default_factory=list, description="Extractors that contributed, in run order."
    )

    @property
    def is_empty(self) -> bool:
        return self.node_count == 0
