"""The Verification Knowledge Graph.

Packs are the storage format; this graph is what reasoning actually queries.
It normalizes every pack into typed nodes (concepts, signals, state
machines, patterns, playbooks) with typed edges (pack CONTAINS item,
pattern SUGGESTS playbook, state FOLLOWS state), so consumers ask questions
("which patterns exist?", "what playbook goes with this match?", "what is
the expected sequence?") instead of walking raw pack data.

The graph is immutable during reasoning: it is built once from packs and
only ever read afterward. ``fingerprint()`` exists so tests can prove it.
"""

from __future__ import annotations

import hashlib
import json
from typing import Iterator, Literal

from pydantic import BaseModel, Field

from veritriage.knowledge.model import (
    Concept,
    DebugPlaybook,
    FailurePattern,
    KnowledgePack,
    ProtocolSignal,
    StateMachine,
)
from veritriage.knowledge.registry import load_packs

KnowledgeRelation = Literal["contains", "suggests_playbook", "follows"]


class KnowledgeEdge(BaseModel):
    source_id: str
    target_id: str
    relation: KnowledgeRelation


class KnowledgeGraph(BaseModel):
    """Read-only queryable view over every loaded Knowledge Pack."""

    packs: dict[str, KnowledgePack] = Field(default_factory=dict)
    edges: list[KnowledgeEdge] = Field(default_factory=list)

    model_config = {"frozen": True}

    # --- Construction ------------------------------------------------------

    @classmethod
    def build(cls, packs: list[KnowledgePack] | None = None) -> "KnowledgeGraph":
        """Build the graph from packs (all registered packs by default)."""
        packs = packs if packs is not None else load_packs()
        edges: list[KnowledgeEdge] = []
        for pack in packs:
            for item_id in cls._item_ids(pack):
                edges.append(
                    KnowledgeEdge(source_id=pack.id, target_id=item_id, relation="contains")
                )
            for pattern in pack.patterns:
                if pattern.playbook_id:
                    edges.append(
                        KnowledgeEdge(
                            source_id=pattern.id,
                            target_id=pattern.playbook_id,
                            relation="suggests_playbook",
                        )
                    )
            for machine in pack.state_machines:
                for a, b in zip(machine.states, machine.states[1:]):
                    edges.append(
                        KnowledgeEdge(
                            source_id=f"{machine.id}#{a.name}",
                            target_id=f"{machine.id}#{b.name}",
                            relation="follows",
                        )
                    )
        return cls(packs={p.id: p for p in packs}, edges=edges)

    @staticmethod
    def _item_ids(pack: KnowledgePack) -> list[str]:
        return [
            *(c.id for c in pack.concepts),
            *(m.id for m in pack.state_machines),
            *(p.id for p in pack.patterns),
            *(b.id for b in pack.playbooks),
        ]

    # --- Queries -----------------------------------------------------------

    def concepts(self) -> Iterator[tuple[KnowledgePack, Concept]]:
        for pack in self.packs.values():
            for concept in pack.concepts:
                yield pack, concept

    def patterns(self) -> Iterator[tuple[KnowledgePack, FailurePattern]]:
        for pack in self.packs.values():
            for pattern in pack.patterns:
                yield pack, pattern

    def state_machines(self) -> Iterator[tuple[KnowledgePack, StateMachine]]:
        for pack in self.packs.values():
            for machine in pack.state_machines:
                yield pack, machine

    def signals(self) -> Iterator[tuple[KnowledgePack, ProtocolSignal]]:
        for pack in self.packs.values():
            for signal in pack.signals:
                yield pack, signal

    def playbook(self, playbook_id: str) -> tuple[KnowledgePack, DebugPlaybook] | None:
        for pack in self.packs.values():
            for playbook in pack.playbooks:
                if playbook.id == playbook_id:
                    return pack, playbook
        return None

    def playbook_for(self, pattern_id: str) -> tuple[KnowledgePack, DebugPlaybook] | None:
        """The playbook a pattern suggests, resolved through the graph edges."""
        for edge in self.edges:
            if edge.source_id == pattern_id and edge.relation == "suggests_playbook":
                return self.playbook(edge.target_id)
        return None

    def expected_sequence(self, machine_id: str) -> list[str]:
        """State names in protocol order, from the FOLLOWS edges."""
        ordered: list[str] = []
        for edge in self.edges:
            if edge.relation != "follows" or not edge.source_id.startswith(f"{machine_id}#"):
                continue
            src = edge.source_id.split("#", 1)[1]
            dst = edge.target_id.split("#", 1)[1]
            if not ordered:
                ordered.append(src)
            ordered.append(dst)
        return ordered

    def pack_versions(self) -> dict[str, str]:
        return {pack_id: pack.version for pack_id, pack in sorted(self.packs.items())}

    def fingerprint(self) -> str:
        """Stable digest of the entire graph; unchanged means unmutated."""
        canonical = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha1(canonical.encode("utf-8")).hexdigest()
