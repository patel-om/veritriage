"""Deterministic search over evidence and the knowledge base.

Substring matching, case-insensitive, results ordered by (kind, id): the same
query always returns the same hits in the same order. No scoring model, no
AI; a hit is a citation, not a conclusion.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from veritriage.workspace.session import InvestigationSession


class EvidenceHit(BaseModel):
    """One evidence node matching a search query."""

    node_id: str
    artifact_type: str
    severity: str | None = None
    description: str
    source_path: str
    line_number: int | None = None


class KnowledgeHit(BaseModel):
    """One knowledge-base object matching a search query."""

    kind: str = Field(description="'concept', 'pattern', or 'playbook'.")
    id: str
    name: str
    pack: str
    summary: str


def search_evidence(session: InvestigationSession, query: str) -> list[EvidenceHit]:
    """Evidence nodes whose description or module contains the query."""
    lowered = query.lower()
    hits: list[EvidenceHit] = []
    for node in session.graph.nodes.values():
        haystack = f"{node.description} {node.module or ''}".lower()
        if lowered in haystack:
            hits.append(
                EvidenceHit(
                    node_id=node.id,
                    artifact_type=node.artifact_type.value,
                    severity=node.severity.value if node.severity else None,
                    description=node.description,
                    source_path=node.source_path,
                    line_number=node.line_number,
                )
            )
    hits.sort(key=lambda h: h.node_id)
    return hits


def search_knowledge(query: str) -> list[KnowledgeHit]:
    """Concepts, patterns, and playbooks matching the query, across all packs.

    Searches names and summaries (playbooks: names and step actions). The
    knowledge base is deterministic and versioned, so this search is too.
    """
    from veritriage.knowledge import load_packs

    lowered = query.lower()
    hits: list[KnowledgeHit] = []
    for pack in load_packs():
        for concept in pack.concepts:
            if lowered in f"{concept.name} {concept.summary}".lower():
                hits.append(
                    KnowledgeHit(
                        kind="concept",
                        id=concept.id,
                        name=concept.name,
                        pack=pack.id,
                        summary=concept.summary,
                    )
                )
        for pattern in pack.patterns:
            if lowered in f"{pattern.name} {pattern.summary}".lower():
                hits.append(
                    KnowledgeHit(
                        kind="pattern",
                        id=pattern.id,
                        name=pattern.name,
                        pack=pack.id,
                        summary=pattern.summary,
                    )
                )
        for playbook in pack.playbooks:
            haystack = playbook.name + " " + " ".join(s.action for s in playbook.steps)
            if lowered in haystack.lower():
                hits.append(
                    KnowledgeHit(
                        kind="playbook",
                        id=playbook.id,
                        name=playbook.name,
                        pack=pack.id,
                        summary="; ".join(s.action for s in playbook.steps[:3]),
                    )
                )
    hits.sort(key=lambda h: (h.kind, h.id))
    return hits


def search_playbooks(query: str) -> list[KnowledgeHit]:
    """The playbook slice of the knowledge search."""
    return [hit for hit in search_knowledge(query) if hit.kind == "playbook"]
