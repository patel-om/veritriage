"""The learner plugin table.

A ``Learner`` is a pure function from recorded history to learning artifacts.
It receives every `RegressionRecord` and every `FeedbackRecord` and returns
artifacts; it performs no I/O, keeps no state between calls, and never sees a
raw artifact (the records it reads contain only normalized platform objects).

Batch rather than incremental on purpose: recomputation from the corpus is what
makes the milestone's central law hold. Given the same history, the same
artifacts, byte for byte, regardless of the order runs happened to arrive in.

``@register_learner`` is the plugin seam, identical in spirit to the parser,
pack, adapter, provider, step, profile, tool, annotation-target, and agent
registries already in the platform.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, ClassVar, TypeVar

from veritriage.models import LearningArtifact

if TYPE_CHECKING:  # pragma: no cover - typing only
    from veritriage.learning.corpus import Corpus

_L = TypeVar("_L", bound=type["Learner"])

_REGISTRY: dict[str, type["Learner"]] = {}


class Learner(ABC):
    """One family of learned artifacts, derived from recorded history."""

    #: Unique registered learner ID.
    learner_id: ClassVar[str]

    #: The artifact kind this learner produces.
    artifact_kind: ClassVar[str]

    @abstractmethod
    def observe(self, corpus: "Corpus") -> list[LearningArtifact]:
        """Derive artifacts from the whole corpus. Pure: no I/O, no clock."""
        raise NotImplementedError

    @staticmethod
    def _support(count: int, saturation: int = 8) -> float:
        """Map an observation count to a bounded support confidence.

        Deliberately simple and printable: confidence rises with evidence and
        saturates, so one lucky observation never looks like a law.
        """
        if count <= 0:
            return 0.0
        return round(min(1.0, count / saturation), 4)


def register_learner(learner_cls: _L) -> _L:
    """Class decorator adding a learner to the registry.

    Raises:
        ValueError: If another learner already registered the same ID.
    """
    existing = _REGISTRY.get(learner_cls.learner_id)
    if existing is not None and existing is not learner_cls:
        raise ValueError(
            f"Learner ID {learner_cls.learner_id!r} is already registered by {existing!r}"
        )
    _REGISTRY[learner_cls.learner_id] = learner_cls
    return learner_cls


def unregister_learner(learner_id: str) -> None:
    """Remove a learner (used by tests to clean up throwaway learners)."""
    _REGISTRY.pop(learner_id, None)


def available_learners() -> dict[str, type[Learner]]:
    """All registered learners, keyed by ID."""
    return dict(_REGISTRY)


def get_learner(learner_id: str) -> Learner:
    """Instantiate a registered learner.

    Raises:
        KeyError: If no learner with that ID is registered.
    """
    try:
        return _REGISTRY[learner_id]()
    except KeyError:
        known = ", ".join(sorted(_REGISTRY)) or "<none>"
        raise KeyError(f"Unknown learner {learner_id!r}. Registered: {known}") from None


def default_learners() -> list[Learner]:
    """One instance of every registered learner, in deterministic ID order."""
    return [_REGISTRY[learner_id]() for learner_id in sorted(_REGISTRY)]
