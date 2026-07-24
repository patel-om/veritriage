"""Deterministic pattern matching and state projection over evidence.

Pure functions of (Knowledge Graph, Evidence Graph): no I/O, no randomness,
no AI. The same graphs always produce the same matches, the same scores,
and the same projection, which is what lets knowledge conclusions be cited
like any other evidence.
"""

from __future__ import annotations

import operator
import re
from functools import lru_cache

from pydantic import BaseModel, Field

from veritriage.graph.graph import EvidenceGraph
from veritriage.graph.model import EvidenceNode
from veritriage.knowledge.graph import KnowledgeGraph
from veritriage.knowledge.model import (
    Concept,
    EvidenceClause,
    FailurePattern,
    KnowledgePack,
    StateMachine,
)
from veritriage.models import StateProgress, StateProjection

#: Score of a pattern whose required clauses all matched but no optional did.
_BASE_SCORE = 0.7

#: Comparison operators a NumericConstraint may use.
_NUMERIC_OPS = {
    "gt": operator.gt,
    "ge": operator.ge,
    "lt": operator.lt,
    "le": operator.le,
    "eq": operator.eq,
    "ne": operator.ne,
}

#: First signed integer/decimal in a piece of text (numeric-clause fallback).
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


@lru_cache(maxsize=512)
def _compile(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


def _extract_number(match: re.Match[str]) -> float | None:
    """The number a numeric clause compares: first capture group, else the
    first number anywhere in the matched span."""
    for group in match.groups():
        if group is None:
            continue
        try:
            return float(group)
        except (TypeError, ValueError):
            continue
    fallback = _NUMBER_RE.search(match.group(0))
    return float(fallback.group(0)) if fallback else None


def _clause_matches(clause: EvidenceClause, node: EvidenceNode) -> bool:
    if clause.artifact_types is not None and node.artifact_type.value not in clause.artifact_types:
        return False
    if clause.must_fail and not node.is_failing:
        return False
    regex = _compile(clause.pattern)
    match = regex.search(node.description)
    if match is None and node.raw_line is not None:
        match = regex.search(node.raw_line)
    if match is None:
        return False
    if clause.numeric is not None:
        value = _extract_number(match)
        if value is None or not _NUMERIC_OPS[clause.numeric.op](value, clause.numeric.value):
            return False
    return True


def _clause_hits(clause: EvidenceClause, nodes: list[EvidenceNode]) -> list[str]:
    return [n.id for n in nodes if _clause_matches(clause, n)]


class PatternMatch(BaseModel):
    """One pattern that matched, with the evidence that satisfied each clause."""

    pack: KnowledgePack
    pattern: FailurePattern
    score: float = Field(ge=0.0, le=1.0)
    matched_evidence: dict[str, list[str]] = Field(default_factory=dict)


class ConceptMatch(BaseModel):
    pack: KnowledgePack
    concept: Concept
    evidence_ids: list[str] = Field(default_factory=list)


def match_patterns(knowledge: KnowledgeGraph, graph: EvidenceGraph) -> list[PatternMatch]:
    """Every failure pattern whose clauses the evidence satisfies.

    A pattern matches when all required clauses hit at least one node and no
    forbidden clause hits any. Score = 0.7 + 0.3 * (optional clauses hit /
    optional clauses defined); a pattern with no optional clauses scores 0.7.
    Results are ordered by score descending, then pattern id, so the order
    is reproducible.
    """
    nodes = list(graph.nodes.values())
    matches: list[PatternMatch] = []
    for pack, pattern in knowledge.patterns():
        matched: dict[str, list[str]] = {}
        ok = True
        for clause in pattern.required:
            hits = _clause_hits(clause, nodes)
            if clause.absent:
                # Omission: this expected marker must NOT appear. There is no
                # node to cite for an absence, so it contributes no evidence.
                if hits:
                    ok = False
                    break
                continue
            if not hits:
                ok = False
                break
            matched[clause.name] = hits
        if not ok:
            continue
        if any(_clause_hits(clause, nodes) for clause in pattern.forbidden):
            continue
        optional_hit = 0
        for clause in pattern.optional_:
            hits = _clause_hits(clause, nodes)
            if hits:
                optional_hit += 1
                matched[clause.name] = hits
        bonus = (optional_hit / len(pattern.optional_)) if pattern.optional_ else 0.0
        matches.append(
            PatternMatch(
                pack=pack,
                pattern=pattern,
                score=round(_BASE_SCORE + (1.0 - _BASE_SCORE) * bonus, 4),
                matched_evidence=matched,
            )
        )
    matches.sort(key=lambda m: (-m.score, m.pattern.id))
    return matches


def match_concepts(knowledge: KnowledgeGraph, graph: EvidenceGraph) -> list[ConceptMatch]:
    """Concepts whose markers appear anywhere in the evidence."""
    nodes = list(graph.nodes.values())
    results: list[ConceptMatch] = []
    for pack, concept in knowledge.concepts():
        hit_ids: list[str] = []
        for node in nodes:
            if any(_clause_matches(EvidenceClause(name="m", pattern=m), node) for m in concept.markers):
                hit_ids.append(node.id)
        if hit_ids:
            results.append(ConceptMatch(pack=pack, concept=concept, evidence_ids=hit_ids))
    results.sort(key=lambda c: (-len(c.evidence_ids), c.concept.id))
    return results


def project_states(
    pack: KnowledgePack, machine: StateMachine, graph: EvidenceGraph
) -> StateProjection:
    """Project evidence onto a state machine: which stages were reached.

    A state is reached when any of its markers matches any evidence node.
    ``stopped_at`` is the first unreached state after the last reached one:
    where forward progress stopped against the expected sequence.
    """
    nodes = list(graph.nodes.values())
    states: list[StateProgress] = []
    for state in machine.states:
        hit_ids: list[str] = []
        for node in nodes:
            if any(
                _clause_matches(EvidenceClause(name="m", pattern=marker), node)
                for marker in state.markers
            ):
                hit_ids.append(node.id)
        states.append(
            StateProgress(
                state=state.name,
                description=state.description,
                reached=bool(hit_ids),
                evidence_ids=hit_ids[:4],
            )
        )
    stopped_at = None
    last_reached = max((i for i, s in enumerate(states) if s.reached), default=-1)
    for i, s in enumerate(states):
        if i > last_reached:
            stopped_at = s.state
            break
    return StateProjection(
        machine_id=machine.id,
        name=machine.name,
        pack=pack.id,
        states=states,
        stopped_at=stopped_at,
    )


def best_projection(knowledge: KnowledgeGraph, graph: EvidenceGraph) -> StateProjection | None:
    """The most informative state projection: most reached states, not all reached.

    A projection with zero reached states says nothing; one with every state
    reached shows no stall. The most useful picture is maximal partial
    progress. Ties break on machine id for determinism.
    """
    best: StateProjection | None = None
    best_key: tuple[int, str] | None = None
    for pack, machine in knowledge.state_machines():
        projection = project_states(pack, machine, graph)
        reached = sum(1 for s in projection.states if s.reached)
        if reached == 0 or projection.stopped_at is None:
            continue
        key = (-reached, projection.machine_id)
        if best_key is None or key < best_key:
            best, best_key = projection, key
    return best
