"""The Design Graph: typed structure, derived from the Project Model.

The third graph in the platform, and deliberately so. The Evidence Graph says
what happened in one run; the Knowledge Graph says what is generally true of a
protocol; the Design Graph says what this system *is*. Merging any pair would
destroy a property, so they stay separate and reference each other by ID.

Shaped like the Evidence Graph on purpose: content-hashed node IDs, typed
edges, and a rationale on every edge. The same Project Model always produces the
same graph, byte for byte, so a design node can be cited from a report, a plan,
or an MCP response and mean the same thing tomorrow.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Iterable

from pydantic import BaseModel, ConfigDict, Field


class NodeKind(str, Enum):
    """What sort of structural thing a node is."""

    MODULE = "module"
    IP = "ip"
    INTERFACE = "interface"
    CLOCK_DOMAIN = "clock_domain"
    RESET_DOMAIN = "reset_domain"
    ADDRESS_REGION = "address_region"
    REGISTER_BLOCK = "register_block"
    UVM_COMPONENT = "uvm_component"
    VIP = "vip"
    SEQUENCE = "sequence"
    TEST = "test"
    COVERAGE_GROUP = "coverage_group"
    ASSERTION_GROUP = "assertion_group"
    CONFIG_OBJECT = "config_object"
    PROTOCOL = "protocol"

    @property
    def display_name(self) -> str:
        return self.value.replace("_", " ").title().replace("Uvm", "UVM").replace("Ip", "IP")


class DesignRelation(str, Enum):
    """Typed relationships between structural nodes."""

    INSTANTIATES = "instantiates"
    OWNS = "owns"
    CONNECTS = "connects"
    DRIVES = "drives"
    MONITORS = "monitors"
    PREDICTS = "predicts"
    IMPLEMENTS = "implements"
    DEPENDS_ON = "depends_on"
    CLOCKED_BY = "clocked_by"
    RESET_BY = "reset_by"
    COMMUNICATES_WITH = "communicates_with"
    COVERS = "covers"
    ASSERTS = "asserts"
    CONFIGURED_BY = "configured_by"


def make_node_id(kind: NodeKind, name: str) -> str:
    """Deterministic, content-derived node ID.

    Kind plus canonical name, so the same structure always yields the same ID
    and two extractors describing the same module converge on one node.
    """
    digest = hashlib.sha1(f"{kind.value}|{name.strip().lower()}".encode("utf-8")).hexdigest()
    return f"dn-{digest[:12]}"


class DesignNode(BaseModel):
    """One structural element of the system."""

    model_config = ConfigDict(frozen=True)

    id: str
    kind: NodeKind
    name: str
    qualified_name: str | None = Field(
        default=None, description="Full hierarchical path, when the model knows one."
    )
    source_file: str | None = None
    owner: str | None = Field(default=None, description="Engineering owner, when declared.")
    protocol_id: str | None = Field(
        default=None, description="Knowledge Pack this element speaks, when identified."
    )
    attributes: dict[str, str] = Field(
        default_factory=dict, description="Kind-specific plain data; never opaque."
    )
    extracted_by: str = Field(description="The extractor that produced this node.")


class DesignEdge(BaseModel):
    """One typed relationship, always justified by the field it came from."""

    model_config = ConfigDict(frozen=True)

    source_id: str
    target_id: str
    relation: DesignRelation
    rationale: str = Field(description="The Project Model field this edge was derived from.")
    inferred: bool = Field(
        default=False,
        description="True when the edge follows hierarchy rather than an explicit "
        "declaration. Inference is allowed; hiding it is not.",
    )


class DesignGraph(BaseModel):
    """The structural graph of one verification project.

    Built once from a Project Model and only read afterwards. ``fingerprint()``
    exists so tests can prove it, mirroring the Knowledge Graph.
    """

    schema_version: str = "1"
    project_id: str = ""
    nodes: dict[str, DesignNode] = Field(default_factory=dict)
    edges: list[DesignEdge] = Field(default_factory=list)

    # --- Construction ------------------------------------------------------

    def add_node(self, node: DesignNode) -> DesignNode:
        """Add a node; re-adding the same ID keeps the richer description.

        Two extractors may legitimately describe the same module from different
        angles (hierarchy knows its parent, ownership knows its team). Merging
        by field rather than rejecting is what lets extractors stay independent.
        """
        existing = self.nodes.get(node.id)
        if existing is None:
            self.nodes[node.id] = node
            return node
        merged = existing.model_copy(
            update={
                "qualified_name": existing.qualified_name or node.qualified_name,
                "source_file": existing.source_file or node.source_file,
                "owner": existing.owner or node.owner,
                "protocol_id": existing.protocol_id or node.protocol_id,
                "attributes": {**node.attributes, **existing.attributes},
            }
        )
        self.nodes[node.id] = merged
        return merged

    def add_edge(self, edge: DesignEdge) -> DesignEdge | None:
        """Add an edge between two existing nodes; unknown endpoints are dropped.

        Dropping rather than raising is deliberate: the Project Model is often
        partial (a manifest may name a clock root that was never declared as a
        module), and a partial model should yield a smaller graph, not an error.
        """
        if edge.source_id not in self.nodes or edge.target_id not in self.nodes:
            return None
        if edge not in self.edges:
            self.edges.append(edge)
        return edge

    # --- Queries (all deterministic) ---------------------------------------

    def node(self, node_id: str) -> DesignNode | None:
        return self.nodes.get(node_id)

    def by_name(self, name: str, kind: NodeKind | None = None) -> DesignNode | None:
        """Resolve a bare name to a node, optionally constrained by kind."""
        lowered = name.strip().lower()
        for node in self.nodes.values():
            if node.name.lower() != lowered:
                continue
            if kind is None or node.kind is kind:
                return node
        return None

    def of_kind(self, *kinds: NodeKind) -> list[DesignNode]:
        wanted = set(kinds)
        return [n for n in self.nodes.values() if n.kind in wanted]

    def edges_from(self, node_id: str, *relations: DesignRelation) -> list[DesignEdge]:
        wanted = set(relations)
        return [
            e
            for e in self.edges
            if e.source_id == node_id and (not wanted or e.relation in wanted)
        ]

    def edges_to(self, node_id: str, *relations: DesignRelation) -> list[DesignEdge]:
        wanted = set(relations)
        return [
            e
            for e in self.edges
            if e.target_id == node_id and (not wanted or e.relation in wanted)
        ]

    def targets(self, node_id: str, *relations: DesignRelation) -> list[DesignNode]:
        return [self.nodes[e.target_id] for e in self.edges_from(node_id, *relations)]

    def sources(self, node_id: str, *relations: DesignRelation) -> list[DesignNode]:
        return [self.nodes[e.source_id] for e in self.edges_to(node_id, *relations)]

    def neighbours(self, node_id: str) -> list[DesignNode]:
        """Every node one edge away, in edge order, deduplicated."""
        seen: dict[str, DesignNode] = {}
        for edge in self.edges:
            other = None
            if edge.source_id == node_id:
                other = edge.target_id
            elif edge.target_id == node_id:
                other = edge.source_id
            if other is not None and other not in seen and other in self.nodes:
                seen[other] = self.nodes[other]
        return list(seen.values())

    def stats(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for node in self.nodes.values():
            counts[node.kind.value] = counts.get(node.kind.value, 0) + 1
        for edge in self.edges:
            key = f"edge:{edge.relation.value}"
            counts[key] = counts.get(key, 0) + 1
        return dict(sorted(counts.items()))

    @property
    def is_empty(self) -> bool:
        return not self.nodes

    def fingerprint(self) -> str:
        """Stable digest of the whole graph; unchanged means unmutated."""
        payload = {
            "nodes": sorted(
                (n.model_dump(mode="json") for n in self.nodes.values()),
                key=lambda n: n["id"],
            ),
            "edges": sorted(
                (e.model_dump(mode="json") for e in self.edges),
                key=lambda e: (e["source_id"], e["target_id"], e["relation"]),
            ),
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return "sha1:" + hashlib.sha1(canonical.encode("utf-8")).hexdigest()


def node_ids(nodes: Iterable[DesignNode]) -> list[str]:
    """Sorted, deduplicated IDs for a set of nodes."""
    return sorted({n.id for n in nodes})
