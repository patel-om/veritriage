"""Design hierarchy: modules, IP blocks, and what instantiates what.

Resolves ``DesignModule.parent`` and ``IpBlock.modules``, two fields the Project
Model has carried since M11 and that nothing has ever walked.
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


@register_extractor
class HierarchyExtractor(StructureExtractor):
    """Modules, IP blocks, instantiation, and ownership."""

    extractor_id = "hierarchy"
    order = 10  # creates the nodes most other extractors attach to

    def extract(self, model: ProjectModel, graph: DesignGraph) -> None:
        owners = {o.scope.lower(): o.owner for o in model.engineering.owners}

        for module in model.dut.modules:
            graph.add_node(
                DesignNode(
                    id=make_node_id(NodeKind.MODULE, module.name),
                    kind=NodeKind.MODULE,
                    name=module.name,
                    qualified_name=self._qualified(model, module.name),
                    source_file=module.source_file,
                    owner=owners.get(module.name.lower()),
                    attributes=(
                        {"role": module.role} if module.role else {}
                    )
                    | ({"is_top": "true"} if module.name == model.dut.top else {}),
                    extracted_by=self.extractor_id,
                )
            )

        for module in model.dut.modules:
            if not module.parent:
                continue
            graph.add_edge(
                DesignEdge(
                    source_id=make_node_id(NodeKind.MODULE, module.parent),
                    target_id=make_node_id(NodeKind.MODULE, module.name),
                    relation=DesignRelation.INSTANTIATES,
                    rationale=f"dut.modules[{module.name}].parent declares {module.parent}",
                )
            )

        for ip in model.dut.ip_blocks:
            graph.add_node(
                DesignNode(
                    id=make_node_id(NodeKind.IP, ip.name),
                    kind=NodeKind.IP,
                    name=ip.name,
                    owner=ip.owner or owners.get(ip.name.lower()),
                    attributes={"kind": ip.kind} if ip.kind else {},
                    extracted_by=self.extractor_id,
                )
            )
            for member in ip.modules:
                graph.add_edge(
                    DesignEdge(
                        source_id=make_node_id(NodeKind.IP, ip.name),
                        target_id=make_node_id(NodeKind.MODULE, member),
                        relation=DesignRelation.OWNS,
                        rationale=f"dut.ips[{ip.name}].modules lists {member}",
                    )
                )

    @staticmethod
    def _qualified(model: ProjectModel, name: str) -> str | None:
        """Walk parents to build the full hierarchical path.

        Guarded against cycles: a malformed manifest must produce a smaller
        graph, never an infinite loop.
        """
        parents = {m.name: m.parent for m in model.dut.modules}
        if name not in parents:
            return None
        path = [name]
        seen = {name}
        current = parents.get(name)
        while current and current not in seen:
            path.append(current)
            seen.add(current)
            current = parents.get(current)
        return ".".join(reversed(path)) if len(path) > 1 else None
