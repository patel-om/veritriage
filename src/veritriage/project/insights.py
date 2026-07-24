"""Source-agnostic project insights: derivations over the merged model.

Insights never read files. They consume the normalized ProjectModel and enrich
it with derived structure. The flagship insight is protocol identification,
which reuses Knowledge Pack concept markers (the packs are the authority on what
a protocol looks like), so no protocol-specific logic lives in the project core
and adding a protocol pack automatically improves project understanding.

Extensible by ``@register_insight``: a new derivation is one registered function.
"""

from __future__ import annotations

import re
from functools import lru_cache
from typing import Callable

from veritriage.project.model import Interface, ProjectModel

#: An insight refines a model and returns a new one (models are frozen).
Insight = Callable[[ProjectModel], ProjectModel]

_INSIGHTS: dict[str, Insight] = {}


def register_insight(name: str) -> Callable[[Insight], Insight]:
    """Decorator registering a named project insight."""

    def _register(fn: Insight) -> Insight:
        if name in _INSIGHTS and _INSIGHTS[name] is not fn:
            raise ValueError(f"Project insight {name!r} is already registered")
        _INSIGHTS[name] = fn
        return fn

    return _register


def unregister_insight(name: str) -> None:
    """Remove an insight (used by tests to clean up throwaway insights)."""
    _INSIGHTS.pop(name, None)


def available_insights() -> tuple[str, ...]:
    return tuple(sorted(_INSIGHTS))


def apply_insights(model: ProjectModel) -> ProjectModel:
    """Run every registered insight in deterministic (sorted-name) order."""
    for name in sorted(_INSIGHTS):
        model = _INSIGHTS[name](model)
    return model


@lru_cache(maxsize=256)
def _compile(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


@lru_cache(maxsize=1)
def _protocol_markers() -> tuple[tuple[str, tuple[str, ...]], ...]:
    """(pack_id, markers) for every pack, from the Knowledge Graph, cached.

    Reuses the knowledge base as the authority on protocol shape. Ordered by
    pack id so identification is deterministic.
    """
    from veritriage.knowledge.graph import KnowledgeGraph

    knowledge = KnowledgeGraph.build()
    by_pack: dict[str, list[str]] = {}
    for pack, concept in knowledge.concepts():
        by_pack.setdefault(pack.id, []).extend(concept.markers)
    return tuple((pid, tuple(markers)) for pid, markers in sorted(by_pack.items()))


def _identify_protocol(interface: Interface) -> tuple[str | None, float]:
    """The protocol a bare interface most likely carries, and a confidence.

    Declared protocols are kept as-is (confidence 1.0). Otherwise the interface
    name and signal names are matched against pack markers; the pack with the
    most marker hits wins. Ties break on pack id for determinism.
    """
    if interface.protocol_id:
        return interface.protocol_id, 1.0
    haystack = " ".join([interface.name, *interface.signals])
    best_pack: str | None = None
    best_hits = 0
    for pack_id, markers in _protocol_markers():
        hits = sum(1 for m in markers if _compile(m).search(haystack))
        if hits > best_hits:
            best_pack, best_hits = pack_id, hits
    if best_pack is None:
        return None, 0.0
    # Inferred: confidence grows with marker hits but stays below declared.
    return best_pack, round(min(0.9, 0.5 + 0.1 * best_hits), 4)


@register_insight("protocol-identification")
def identify_protocols(model: ProjectModel) -> ProjectModel:
    """Fill undeclared interface protocols by matching Knowledge Pack markers."""
    if not model.dut.interfaces:
        return model
    updated: list[Interface] = []
    changed = False
    for interface in model.dut.interfaces:
        protocol_id, _ = _identify_protocol(interface)
        if protocol_id and protocol_id != interface.protocol_id:
            updated.append(interface.model_copy(update={"protocol_id": protocol_id}))
            changed = True
        else:
            updated.append(interface)
    if not changed:
        return model
    return model.model_copy(
        update={"dut": model.dut.model_copy(update={"interfaces": tuple(updated)})}
    )
