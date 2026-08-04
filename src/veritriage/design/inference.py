"""How the Design Graph reaches the report.

One integration surface, deliberately narrow: ``build_design_view`` assembles
the :class:`DesignContext` embedded in the report. The graph itself is never
copied into the report; views reference it by node ID, so a report can cite a
structural element without carrying the structure.

The Design Graph never enters the Evidence Graph. This module reads the
Evidence Graph (to learn which scopes failed) and never writes to it.
Deterministic and AI-free.
"""

from __future__ import annotations

from veritriage.design.model import DesignGraph, DesignNode, DesignRelation, NodeKind
from veritriage.design.query import DesignQuery
from veritriage.graph.graph import EvidenceGraph
from veritriage.models import (
    ClockCrossingView,
    ClockDomainView,
    DesignContext,
    DesignNodeView,
    DesignRelationView,
    HierarchyRow,
    RiskHotspot,
    VerificationTopologyView,
)

#: How many hierarchy rows a report carries. A full SoC tree belongs in an IDE.
MAX_HIERARCHY_ROWS = 40

#: How many unverified modules are worth naming before the point is made.
MAX_RISK_ITEMS = 6


def failing_scopes(graph: EvidenceGraph) -> list[str]:
    """The scopes this run's failing evidence pointed at, in first-seen order."""
    found: list[str] = []
    for node in graph.failing():
        if node.module and node.module not in found:
            found.append(node.module)
    return found


def build_design_view(design: DesignGraph, evidence: EvidenceGraph) -> DesignContext:
    """Assemble the report-facing DesignContext for one run."""
    query = DesignQuery(design)
    scopes = failing_scopes(evidence)
    region = query.affected_region(scopes)
    region_ids = {n.id for n in region}

    relations = [
        DesignRelationView(
            source=design.nodes[e.source_id].name,
            target=design.nodes[e.target_id].name,
            relation=e.relation.value,
            rationale=e.rationale,
            inferred=e.inferred,
        )
        for e in design.edges
        if e.source_id in region_ids and e.target_id in region_ids
    ]

    components = [
        _component_view(design, node)
        for node in region
        if node.kind is NodeKind.UVM_COMPONENT
    ]
    # A failing run with no component in its immediate region still benefits
    # from knowing who watches the interfaces involved.
    for node in region:
        if node.kind is not NodeKind.INTERFACE:
            continue
        for observer in query.observers_of(node.name):
            view = _component_view(design, observer)
            if view not in components:
                components.append(view)

    return DesignContext(
        project_id=design.project_id,
        graph_fingerprint=design.fingerprint(),
        node_count=len(design.nodes),
        edge_count=len(design.edges),
        stats=design.stats(),
        affected_region=[_node_view(n) for n in region],
        affected_relations=relations,
        relevant_modules=sorted(
            n.name for n in region if n.kind in (NodeKind.MODULE, NodeKind.IP)
        ),
        verification_components=components,
        clock_domains=_clock_domains(design),
        reset_domains=sorted(n.name for n in design.of_kind(NodeKind.RESET_DOMAIN)),
        clock_crossings=[
            ClockCrossingView(
                left=left.name,
                right=right.name,
                note=(
                    f"{left.name} and {right.name} communicate but do not share a "
                    "clock domain, so this boundary needs synchronization."
                ),
            )
            for left, right in query.crossings()
        ],
        protocol_map=query.protocol_map(),
        hierarchy=[
            HierarchyRow(
                depth=depth,
                node_id=node.id,
                name=node.name,
                kind=node.kind.value,
                owner=node.owner,
            )
            for depth, node in query.hierarchy()[:MAX_HIERARCHY_ROWS]
        ],
        dependencies=[
            DesignRelationView(
                source=design.nodes[e.source_id].name,
                target=design.nodes[e.target_id].name,
                relation=e.relation.value,
                rationale=e.rationale,
                inferred=e.inferred,
            )
            for e in design.edges
            if e.relation is DesignRelation.DEPENDS_ON
        ],
        risk_hotspots=_risks(query, region),
        extractors=sorted({n.extracted_by for n in design.nodes.values()}),
    )


def _node_view(node: DesignNode) -> DesignNodeView:
    return DesignNodeView(
        node_id=node.id,
        kind=node.kind.value,
        name=node.name,
        qualified_name=node.qualified_name,
        owner=node.owner,
        protocol_id=node.protocol_id,
        source_file=node.source_file,
    )


def _component_view(design: DesignGraph, node: DesignNode) -> VerificationTopologyView:
    watched = next(
        (
            e
            for e in design.edges_from(
                node.id,
                DesignRelation.MONITORS,
                DesignRelation.DRIVES,
                DesignRelation.PREDICTS,
                DesignRelation.CONNECTS,
            )
        ),
        None,
    )
    target = design.node(watched.target_id) if watched is not None else None
    return VerificationTopologyView(
        component=node.qualified_name or node.name,
        type=node.attributes.get("type", node.kind.value),
        interface=target.name if target is not None else None,
        relation=watched.relation.value if watched is not None else None,
    )


def _clock_domains(design: DesignGraph) -> list[ClockDomainView]:
    views: list[ClockDomainView] = []
    for domain in sorted(design.of_kind(NodeKind.CLOCK_DOMAIN), key=lambda n: n.name):
        members = sorted(
            n.name
            for n in design.sources(domain.id, DesignRelation.CLOCKED_BY)
            if n.kind is NodeKind.MODULE
        )
        views.append(
            ClockDomainView(
                node_id=domain.id,
                name=domain.name,
                module_count=len(members),
                modules=members[:8],
            )
        )
    return views


def _risks(query: DesignQuery, region: list[DesignNode]) -> list[RiskHotspot]:
    """Structural risks, derived from the graph. Never a guess."""
    risks: list[RiskHotspot] = []
    region_ids = {n.id for n in region}

    unverified = [
        n for n in query.unverified_modules() if not region or n.id in region_ids
    ]
    for module in unverified[:MAX_RISK_ITEMS]:
        risks.append(
            RiskHotspot(
                kind="unverified_module",
                subject=module.name,
                detail=(
                    f"No assertion group or coverage group in the project model points "
                    f"at {module.name}, so nothing is currently checking it."
                ),
                node_ids=[module.id],
            )
        )
    for left, right in query.crossings():
        risks.append(
            RiskHotspot(
                kind="clock_crossing",
                subject=f"{left.name} <-> {right.name}",
                detail=(
                    "These modules communicate across a clock domain boundary, which is "
                    "where synchronization bugs live."
                ),
                node_ids=[left.id, right.id],
            )
        )
    return risks
