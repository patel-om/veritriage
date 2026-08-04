"""The step-source plugin table.

A ``StepSource`` turns one upstream producer's output into candidate debug
steps. It is the mechanism behind the milestone's central law: a source may
only *restate* something an existing artifact already said, and must record
where it came from in ``derived_from``. The Planner then arranges, values,
orders, and branches those candidates.

Sources never invent advice, never read a file, and never execute anything.

``@register_source`` is the plugin seam, identical in spirit to the parser,
pack, adapter, provider, step, profile, tool, annotation-target, agent, and
learner registries already in the platform.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar, TypeVar

if TYPE_CHECKING:  # pragma: no cover - typing only
    from veritriage.planning.context import PlanningContext, StepCandidate

_S = TypeVar("_S", bound=type["StepSource"])

_REGISTRY: dict[str, type["StepSource"]] = {}


class StepSource(ABC):
    """One producer of candidate debug steps, derived from existing artifacts."""

    #: Unique registered source ID.
    source_id: ClassVar[str]

    #: Rough ordering hint when two candidates tie on value and effort; lower
    #: wins. Curated knowledge outranks generic templates by default.
    rank: ClassVar[int] = 50

    def applies_to(self, context: "PlanningContext") -> bool:
        """Whether this source has anything to contribute to this analysis."""
        return True

    @abstractmethod
    def propose(self, context: "PlanningContext") -> list["StepCandidate"]:
        """Restate what an upstream artifact already said, as candidate steps."""
        raise NotImplementedError


def register_source(source_cls: _S) -> _S:
    """Class decorator adding a step source to the registry.

    Raises:
        ValueError: If another source already registered the same ID.
    """
    existing = _REGISTRY.get(source_cls.source_id)
    if existing is not None and existing is not source_cls:
        raise ValueError(
            f"Step source ID {source_cls.source_id!r} is already registered by {existing!r}"
        )
    _REGISTRY[source_cls.source_id] = source_cls
    return source_cls


def unregister_source(source_id: str) -> None:
    """Remove a source (used by tests to clean up throwaway sources)."""
    _REGISTRY.pop(source_id, None)


def available_sources() -> dict[str, type[StepSource]]:
    """All registered step sources, keyed by ID."""
    return dict(_REGISTRY)


def get_source(source_id: str) -> StepSource:
    """Instantiate a registered step source.

    Raises:
        KeyError: If no source with that ID is registered.
    """
    try:
        return _REGISTRY[source_id]()
    except KeyError:
        known = ", ".join(sorted(_REGISTRY)) or "<none>"
        raise KeyError(f"Unknown step source {source_id!r}. Registered: {known}") from None


def default_sources() -> list[StepSource]:
    """One instance of every registered source, in deterministic ID order."""
    return [_REGISTRY[source_id]() for source_id in sorted(_REGISTRY)]
