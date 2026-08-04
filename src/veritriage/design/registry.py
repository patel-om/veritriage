"""The structure-extractor plugin table.

A ``StructureExtractor`` turns one facet of the Project Model into typed nodes
and edges. It is source-agnostic by construction: its only input is an
already-normalized :class:`ProjectModel`, so it cannot read a file, a build
script, or a source language even by accident. That is the milestone's central
law made mechanical rather than merely stated.

Extractors run in registered ID order and share one graph, so a later extractor
may attach edges to nodes an earlier one created. Node merging in
``DesignGraph.add_node`` is what lets them stay independent while describing the
same module from different angles.

``@register_extractor`` is the plugin seam, identical in spirit to the parser,
pack, adapter, provider, step, profile, tool, annotation-target, agent, learner,
and step-source registries already in the platform.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar, TypeVar

if TYPE_CHECKING:  # pragma: no cover - typing only
    from veritriage.design.model import DesignGraph
    from veritriage.project.model import ProjectModel

_E = TypeVar("_E", bound=type["StructureExtractor"])

_REGISTRY: dict[str, type["StructureExtractor"]] = {}


class StructureExtractor(ABC):
    """One facet of project structure, normalized into graph nodes and edges."""

    #: Unique registered extractor ID.
    extractor_id: ClassVar[str]

    #: Lower runs earlier. Extractors that create the nodes others attach to
    #: (hierarchy, interfaces) run before those that only add edges.
    order: ClassVar[int] = 50

    @abstractmethod
    def extract(self, model: "ProjectModel", graph: "DesignGraph") -> None:
        """Add this facet's nodes and edges to the graph. Pure: no I/O."""
        raise NotImplementedError


def register_extractor(extractor_cls: _E) -> _E:
    """Class decorator adding an extractor to the registry.

    Raises:
        ValueError: If another extractor already registered the same ID.
    """
    existing = _REGISTRY.get(extractor_cls.extractor_id)
    if existing is not None and existing is not extractor_cls:
        raise ValueError(
            f"Extractor ID {extractor_cls.extractor_id!r} is already registered by {existing!r}"
        )
    _REGISTRY[extractor_cls.extractor_id] = extractor_cls
    return extractor_cls


def unregister_extractor(extractor_id: str) -> None:
    """Remove an extractor (used by tests to clean up throwaway extractors)."""
    _REGISTRY.pop(extractor_id, None)


def available_extractors() -> dict[str, type[StructureExtractor]]:
    """All registered extractors, keyed by ID."""
    return dict(_REGISTRY)


def get_extractor(extractor_id: str) -> StructureExtractor:
    """Instantiate a registered extractor.

    Raises:
        KeyError: If no extractor with that ID is registered.
    """
    try:
        return _REGISTRY[extractor_id]()
    except KeyError:
        known = ", ".join(sorted(_REGISTRY)) or "<none>"
        raise KeyError(f"Unknown extractor {extractor_id!r}. Registered: {known}") from None


def default_extractors() -> list[StructureExtractor]:
    """Every registered extractor, in deterministic (order, id) sequence."""
    instances = [cls() for cls in _REGISTRY.values()]
    return sorted(instances, key=lambda e: (e.order, e.extractor_id))
