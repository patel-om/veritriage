"""Structural questions as deterministic graph traversals.

The queries that make the Design Graph worth building. Each one is a question a
DV engineer asks out loud in front of a failing regression and that the platform
previously answered with substring matching, or not at all.

Every method is a pure function of the graph. Scope resolution is the one place
that accepts a messy input (a log scope such as
``uvm_test_top.env.scb``) and it resolves segment by segment against real nodes
rather than by intersecting sets of strings.
"""

from __future__ import annotations

from veritriage.design.model import (
    DesignGraph,
    DesignNode,
    DesignRelation,
    NodeKind,
)

#: How far ``affected_region`` walks from a resolved scope. One hop reaches the
#: parent, the clock domain, and the agent watching the interface: the
#: neighbourhood an engineer actually looks at. Two hops reaches the whole SoC.
DEFAULT_RADIUS = 1


class DesignQuery:
    """Deterministic structural queries over one Design Graph."""

    def __init__(self, graph: DesignGraph) -> None:
        self._graph = graph

    @property
    def graph(self) -> DesignGraph:
        return self._graph

    # --- Resolution ---------------------------------------------------------

    def resolve_scope(self, scope: str) -> DesignNode | None:
        """Resolve a log or evidence scope to a design node.

        Tries the whole path, then each segment from the most specific end, and
        prefers a UVM component over a module when a name is ambiguous: a scope
        written ``uvm_test_top.env.scb`` is a testbench path, and the testbench
        interpretation is the right one.
        """
        if not scope:
            return None
        segments = [s for s in scope.replace("/", ".").split(".") if s]
        for candidate in (scope, *reversed(segments)):
            for kind in (
                NodeKind.UVM_COMPONENT,
                NodeKind.MODULE,
                NodeKind.IP,
                NodeKind.INTERFACE,
            ):
                found = self._graph.by_name(candidate, kind)
                if found is not None:
                    return found
            # A qualified name may match even when the bare name does not.
            for node in self._graph.nodes.values():
                if node.qualified_name and node.qualified_name.lower() == candidate.lower():
                    return node
        return None

    def resolve_scopes(self, scopes: list[str]) -> list[DesignNode]:
        """Resolve many scopes, deduplicated, in first-seen order."""
        found: dict[str, DesignNode] = {}
        for scope in scopes:
            node = self.resolve_scope(scope)
            if node is not None:
                found.setdefault(node.id, node)
        return list(found.values())

    # --- The load-bearing query --------------------------------------------

    def affected_region(
        self, scopes: list[str], radius: int = DEFAULT_RADIUS
    ) -> list[DesignNode]:
        """The design neighbourhood around a failure's scopes.

        This is what makes a failure locatable in the system rather than only
        in a log: the modules, domains, interfaces, and verification components
        within ``radius`` hops of where the evidence pointed.
        """
        frontier = self.resolve_scopes(scopes)
        seen = {n.id: n for n in frontier}
        for _ in range(max(0, radius)):
            expanded: list[DesignNode] = []
            for node in frontier:
                for neighbour in self._graph.neighbours(node.id):
                    if neighbour.id not in seen:
                        seen[neighbour.id] = neighbour
                        expanded.append(neighbour)
            frontier = expanded
            if not frontier:
                break
        return sorted(seen.values(), key=lambda n: (n.kind.value, n.name))

    # --- Ownership and observation -----------------------------------------

    def owner_of(self, interface_name: str) -> DesignNode | None:
        """The UVM agent that owns the components bound to an interface."""
        interface = self._graph.by_name(interface_name, NodeKind.INTERFACE)
        if interface is None:
            return None
        for component in self._graph.sources(
            interface.id,
            DesignRelation.MONITORS,
            DesignRelation.DRIVES,
            DesignRelation.PREDICTS,
            DesignRelation.CONNECTS,
        ):
            if component.kind is not NodeKind.UVM_COMPONENT:
                continue
            parents = self._graph.sources(component.id, DesignRelation.OWNS)
            for parent in parents:
                if parent.attributes.get("type", "").lower() == "agent":
                    return parent
            return component
        return None

    def observers_of(self, interface_name: str) -> list[DesignNode]:
        """Everything watching an interface: monitors, VIPs, predictors."""
        interface = self._graph.by_name(interface_name, NodeKind.INTERFACE)
        if interface is None:
            return []
        return sorted(
            self._graph.sources(
                interface.id, DesignRelation.MONITORS, DesignRelation.PREDICTS
            ),
            key=lambda n: n.name,
        )

    # --- Topology -----------------------------------------------------------

    def clock_domains_of(self, scopes: list[str]) -> list[DesignNode]:
        """The clock domains the given scopes belong to."""
        domains: dict[str, DesignNode] = {}
        for node in self.resolve_scopes(scopes):
            for domain in self._graph.targets(node.id, DesignRelation.CLOCKED_BY):
                domains.setdefault(domain.id, domain)
        return sorted(domains.values(), key=lambda n: n.name)

    def reset_domains_of(self, scopes: list[str]) -> list[DesignNode]:
        domains: dict[str, DesignNode] = {}
        for node in self.resolve_scopes(scopes):
            for domain in self._graph.targets(node.id, DesignRelation.RESET_BY):
                domains.setdefault(domain.id, domain)
        return sorted(domains.values(), key=lambda n: n.name)

    def crossings(self) -> list[tuple[DesignNode, DesignNode]]:
        """Module pairs that communicate across different clock domains.

        A clock domain crossing is exactly this: two modules that talk to each
        other and do not share a clock. Reported as pairs, deterministically
        ordered, so a report can name them.
        """
        found: list[tuple[DesignNode, DesignNode]] = []
        for edge in self._graph.edges:
            if edge.relation is not DesignRelation.COMMUNICATES_WITH:
                continue
            left = self._graph.node(edge.source_id)
            right = self._graph.node(edge.target_id)
            if left is None or right is None:
                continue
            left_domains = {d.id for d in self._graph.targets(left.id, DesignRelation.CLOCKED_BY)}
            right_domains = {
                d.id for d in self._graph.targets(right.id, DesignRelation.CLOCKED_BY)
            }
            if left_domains and right_domains and not (left_domains & right_domains):
                found.append((left, right))
        return sorted(found, key=lambda pair: (pair[0].name, pair[1].name))

    def hierarchy(self, root: str | None = None) -> list[tuple[int, DesignNode]]:
        """The instantiation tree as (depth, node), depth first.

        Cycle-safe: a malformed model yields a shorter tree, never a hang.
        """
        if root is not None:
            start = self._graph.by_name(root, NodeKind.MODULE)
        else:
            start = next(
                (n for n in self._graph.of_kind(NodeKind.MODULE) if n.attributes.get("is_top")),
                None,
            ) or next(iter(self._graph.of_kind(NodeKind.MODULE)), None)
        if start is None:
            return []

        rows: list[tuple[int, DesignNode]] = []
        seen: set[str] = set()

        def walk(node: DesignNode, depth: int) -> None:
            if node.id in seen:
                return
            seen.add(node.id)
            rows.append((depth, node))
            children = sorted(
                self._graph.targets(node.id, DesignRelation.INSTANTIATES),
                key=lambda n: n.name,
            )
            for child in children:
                walk(child, depth + 1)

        walk(start, 0)
        return rows

    # --- Dependency and coverage -------------------------------------------

    def _all_named(self, name: str) -> list[DesignNode]:
        """Every node with this name, across kinds.

        A manifest may legitimately name an IP and its top module the same
        thing, and a dependency question means "this thing" rather than "this
        thing as a module". Resolving across kinds is what keeps the answer
        right when the name is shared.
        """
        lowered = name.strip().lower()
        found = [n for n in self._graph.nodes.values() if n.name.lower() == lowered]
        if found:
            return found
        single = self.resolve_scope(name)
        return [single] if single is not None else []

    def dependencies_of(self, name: str) -> list[DesignNode]:
        """What a node depends on, one hop out."""
        found: dict[str, DesignNode] = {}
        for node in self._all_named(name):
            for target in self._graph.targets(
                node.id, DesignRelation.DEPENDS_ON, DesignRelation.CONFIGURED_BY
            ):
                found.setdefault(target.id, target)
        return sorted(found.values(), key=lambda n: n.name)

    def dependents_of(self, name: str) -> list[DesignNode]:
        """What depends on a node, one hop in."""
        found: dict[str, DesignNode] = {}
        for node in self._all_named(name):
            for source in self._graph.sources(
                node.id, DesignRelation.DEPENDS_ON, DesignRelation.CONFIGURED_BY
            ):
                found.setdefault(source.id, source)
        return sorted(found.values(), key=lambda n: n.name)

    def assertions_for(self, module_name: str) -> list[DesignNode]:
        node = self._graph.by_name(module_name, NodeKind.MODULE)
        if node is None:
            return []
        return sorted(
            self._graph.sources(node.id, DesignRelation.ASSERTS), key=lambda n: n.name
        )

    def coverage_for(self, module_name: str) -> list[DesignNode]:
        node = self._graph.by_name(module_name, NodeKind.MODULE)
        if node is None:
            return []
        return sorted(
            self._graph.sources(node.id, DesignRelation.COVERS), key=lambda n: n.name
        )

    def protocol_map(self) -> dict[str, list[str]]:
        """Protocol ID -> the interfaces that speak it."""
        found: dict[str, list[str]] = {}
        for interface in self._graph.of_kind(NodeKind.INTERFACE):
            for protocol in self._graph.targets(interface.id, DesignRelation.IMPLEMENTS):
                found.setdefault(protocol.name, []).append(interface.name)
        return {k: sorted(v) for k, v in sorted(found.items())}

    def unverified_modules(self) -> list[DesignNode]:
        """Modules with no assertion group and no coverage group pointing at them.

        A structural risk signal: logic nobody is checking. Derived, not
        guessed, and honest about what the model actually declares.
        """
        found = []
        for module in self._graph.of_kind(NodeKind.MODULE):
            watched = self._graph.edges_to(
                module.id, DesignRelation.ASSERTS, DesignRelation.COVERS
            )
            if not watched:
                found.append(module)
        return sorted(found, key=lambda n: n.name)
