"""Design Intelligence (M15): the platform understands the system, not just the run.

The third graph in the platform. The Evidence Graph says what happened in one
run; the Knowledge Graph says what is generally true of a protocol; the Design
Graph says what this system *is*.

The law, pinned by tests: **the Design Graph is derived, never extracted.**
This package performs no source reading whatsoever. It normalizes the Project
Model (M11) into a typed, queryable graph, resolving every dangling string into
a real edge. If a structural fact is missing, the fix is a ``ProjectProvider``,
not a new parser. Only a provider may touch a source language or build tool, and
that law stays exactly where M11 put it.

The Design Graph never enters the Evidence Graph: evidence is what happened,
design is what the system is, and they reference each other by ID.

Importing this package registers the six built-in structure extractors.
"""

from veritriage.design import extractors  # noqa: F401  (registers the built-ins)
from veritriage.design.builder import build_design_graph
from veritriage.design.inference import build_design_view, failing_scopes
from veritriage.design.model import (
    DesignEdge,
    DesignGraph,
    DesignNode,
    DesignRelation,
    NodeKind,
    make_node_id,
)
from veritriage.design.query import DesignQuery
from veritriage.design.registry import (
    StructureExtractor,
    available_extractors,
    default_extractors,
    get_extractor,
    register_extractor,
    unregister_extractor,
)

__all__ = [
    "DesignEdge",
    "DesignGraph",
    "DesignNode",
    "DesignQuery",
    "DesignRelation",
    "NodeKind",
    "StructureExtractor",
    "available_extractors",
    "build_design_graph",
    "build_design_view",
    "default_extractors",
    "failing_scopes",
    "get_extractor",
    "make_node_id",
    "register_extractor",
    "unregister_extractor",
]
