"""Building the Design Graph from a Project Model.

The whole build, stated once: run every registered extractor over one already
normalized Project Model, in deterministic order, sharing one graph.

No source is read here or anywhere below here. The Project Model is the input,
and it was produced by a `ProjectProvider`, which is the only component in the
platform permitted to touch a source language or a build tool. That law belongs
to M11 and stays there.
"""

from __future__ import annotations

from veritriage.design.model import DesignGraph
from veritriage.design.registry import StructureExtractor, default_extractors
from veritriage.project.model import ProjectModel


def build_design_graph(
    model: ProjectModel, extractors: list[StructureExtractor] | None = None
) -> DesignGraph:
    """Derive the structural graph of one project. Pure function of the model.

    A broken extractor is isolated rather than fatal: a partial graph is more
    useful than none, and the same reasoning that keeps one failing agent from
    ending an investigation applies here.
    """
    graph = DesignGraph(project_id=model.project_id)
    for extractor in extractors if extractors is not None else default_extractors():
        try:
            extractor.extract(model, graph)
        except Exception:  # one broken extractor must not cost the whole graph
            continue
    return graph
