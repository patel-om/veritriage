"""Verification topology: who watches, drives, predicts, covers, and asserts.

Resolves ``UvmComponent.parent`` and ``UvmComponent.interface``, the two fields
that make "which agent owns this interface?" answerable at all, plus VIP
bindings, coverage groups, assertion groups, sequences, tests, and configuration
objects.
"""

from __future__ import annotations

from veritriage.design.model import (
    DesignEdge,
    DesignGraph,
    DesignNode,
    DesignRelation,
    NodeKind,
    make_node_id,
)
from veritriage.design.registry import StructureExtractor, register_extractor
from veritriage.project.model import ProjectModel

#: UVM component type -> the relationship it has with the interface it names.
#: Anything else that names an interface merely connects to it.
_ROLE_RELATION = {
    "monitor": DesignRelation.MONITORS,
    "subscriber": DesignRelation.MONITORS,
    "driver": DesignRelation.DRIVES,
    "sequencer": DesignRelation.DRIVES,
    "predictor": DesignRelation.PREDICTS,
    "scoreboard": DesignRelation.PREDICTS,
}


@register_extractor
class VerificationTopologyExtractor(StructureExtractor):
    """UVM components, VIPs, and what each observes."""

    extractor_id = "verification"
    order = 40

    def extract(self, model: ProjectModel, graph: DesignGraph) -> None:
        for component in model.env.components:
            qualified = (
                f"{component.parent}.{component.name}" if component.parent else component.name
            )
            component_id = make_node_id(NodeKind.UVM_COMPONENT, qualified)
            graph.add_node(
                DesignNode(
                    id=component_id,
                    kind=NodeKind.UVM_COMPONENT,
                    name=component.name,
                    qualified_name=qualified,
                    attributes={"type": component.type},
                    extracted_by=self.extractor_id,
                )
            )

        for component in model.env.components:
            qualified = (
                f"{component.parent}.{component.name}" if component.parent else component.name
            )
            component_id = make_node_id(NodeKind.UVM_COMPONENT, qualified)

            if component.parent:
                parent_id = self._resolve_parent(model, component.parent)
                if parent_id is not None:
                    graph.add_edge(
                        DesignEdge(
                            source_id=parent_id,
                            target_id=component_id,
                            relation=DesignRelation.OWNS,
                            rationale=(
                                f"env.components[{component.name}].parent declares "
                                f"{component.parent}"
                            ),
                        )
                    )

            if component.interface:
                relation = _ROLE_RELATION.get(
                    component.type.lower(), DesignRelation.CONNECTS
                )
                graph.add_edge(
                    DesignEdge(
                        source_id=component_id,
                        target_id=make_node_id(NodeKind.INTERFACE, component.interface),
                        relation=relation,
                        rationale=(
                            f"env.components[{component.name}] is a {component.type} "
                            f"bound to interface {component.interface}"
                        ),
                    )
                )

        for vip in model.env.vips:
            vip_id = make_node_id(NodeKind.VIP, vip.name)
            graph.add_node(
                DesignNode(
                    id=vip_id,
                    kind=NodeKind.VIP,
                    name=vip.name,
                    protocol_id=vip.protocol_id,
                    extracted_by=self.extractor_id,
                )
            )
            if vip.interface:
                graph.add_edge(
                    DesignEdge(
                        source_id=vip_id,
                        target_id=make_node_id(NodeKind.INTERFACE, vip.interface),
                        relation=DesignRelation.MONITORS,
                        rationale=f"env.vips[{vip.name}] is bound to {vip.interface}",
                    )
                )
            if vip.protocol_id:
                graph.add_edge(
                    DesignEdge(
                        source_id=vip_id,
                        target_id=make_node_id(NodeKind.PROTOCOL, vip.protocol_id),
                        relation=DesignRelation.IMPLEMENTS,
                        rationale=f"env.vips[{vip.name}].protocol is {vip.protocol_id}",
                    )
                )

    @staticmethod
    def _resolve_parent(model: ProjectModel, parent: str) -> str | None:
        """Resolve a parent path to the component node it refers to.

        A parent is written either as a bare name ("env") or as a path
        ("env.axi_agent"), and the component it names was itself keyed by its
        own qualified path. Try the path as given, then its last segment.
        """
        for component in model.env.components:
            qualified = (
                f"{component.parent}.{component.name}" if component.parent else component.name
            )
            if qualified == parent or component.name == parent.split(".")[-1]:
                return make_node_id(NodeKind.UVM_COMPONENT, qualified)
        return None


@register_extractor
class VerificationAssetExtractor(StructureExtractor):
    """Coverage, assertions, sequences, tests, and configuration objects."""

    extractor_id = "verification-assets"
    order = 50

    def extract(self, model: ProjectModel, graph: DesignGraph) -> None:
        module_names = {m.name.lower(): m.name for m in model.dut.modules}

        for group, kind, relation, field in (
            (model.env.coverage, NodeKind.COVERAGE_GROUP, DesignRelation.COVERS, "coverage"),
            (
                model.env.assertions,
                NodeKind.ASSERTION_GROUP,
                DesignRelation.ASSERTS,
                "assertions",
            ),
        ):
            for name in group:
                node_id = make_node_id(kind, name)
                graph.add_node(
                    DesignNode(
                        id=node_id,
                        kind=kind,
                        name=name,
                        extracted_by=self.extractor_id,
                    )
                )
                # A group named after a module covers or asserts that module.
                for segment in name.lower().replace(".", "_").split("_"):
                    target = module_names.get(segment)
                    if target is None:
                        continue
                    graph.add_edge(
                        DesignEdge(
                            source_id=node_id,
                            target_id=make_node_id(NodeKind.MODULE, target),
                            relation=relation,
                            rationale=f"env.{field}[{name}] names module {target}",
                            inferred=True,
                        )
                    )

        for name in model.testbench.sequences:
            graph.add_node(
                DesignNode(
                    id=make_node_id(NodeKind.SEQUENCE, name),
                    kind=NodeKind.SEQUENCE,
                    name=name,
                    extracted_by=self.extractor_id,
                )
            )
        for name in model.testbench.tests:
            graph.add_node(
                DesignNode(
                    id=make_node_id(NodeKind.TEST, name),
                    kind=NodeKind.TEST,
                    name=name,
                    extracted_by=self.extractor_id,
                )
            )

        for name in model.testbench.config_objects:
            config_id = make_node_id(NodeKind.CONFIG_OBJECT, name)
            graph.add_node(
                DesignNode(
                    id=config_id,
                    kind=NodeKind.CONFIG_OBJECT,
                    name=name,
                    extracted_by=self.extractor_id,
                )
            )
            # Every UVM component is reachable by configuration; record the
            # relationship at the environment root so "what does this
            # configuration reach?" has an answer without inventing detail.
            for component in model.env.components:
                if component.parent:
                    continue
                graph.add_edge(
                    DesignEdge(
                        source_id=make_node_id(NodeKind.UVM_COMPONENT, component.name),
                        target_id=config_id,
                        relation=DesignRelation.CONFIGURED_BY,
                        rationale=(
                            f"testbench.config_objects lists {name}, which configures "
                            f"the environment rooted at {component.name}"
                        ),
                        inferred=True,
                    )
                )
