"""Project lifecycle projection: where in the expected flow did the run stop?

A pure projection of the Evidence Graph onto the project's expected
``SimulationLifecycle``, the same algorithm the Knowledge Engine uses to project
evidence onto a protocol state machine (``knowledge.matcher.project_states``),
applied to the whole-simulation lifecycle instead of one protocol. It never
mutates the graph.

This is what lets reasoning say "the run stopped between connect_phase and reset,
before any traffic" instead of only "it timed out": a diagnosis a generic rule
cannot reach.
"""

from __future__ import annotations

import re
from functools import lru_cache

from veritriage.graph.graph import EvidenceGraph
from veritriage.models import LifecycleProjection, StateProgress
from veritriage.project.model import ProjectModel


@lru_cache(maxsize=256)
def _compile(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


def _phase_reached(markers: tuple[str, ...], texts: list[str]) -> list[str]:
    """Node-less marker check: which texts show this phase was reached."""
    hits: list[str] = []
    for idx, text in enumerate(texts):
        if any(_compile(m).search(text) for m in markers):
            hits.append(str(idx))
    return hits


def project_lifecycle(model: ProjectModel, graph: EvidenceGraph) -> LifecycleProjection | None:
    """Project the graph's evidence onto the project's expected lifecycle.

    A phase is reached when any of its markers matches any evidence node's
    description or raw line. ``stopped_at`` is the first phase after the last
    reached one: where forward progress stopped against the expected sequence.
    Returns None when the project declares no lifecycle.
    """
    phases = model.lifecycle.phases
    if not phases:
        return None
    nodes = list(graph.nodes.values())
    texts = [f"{n.description} {n.raw_line or ''}" for n in nodes]

    progress: list[StateProgress] = []
    for phase in phases:
        hit_idx = _phase_reached(phase.markers, texts)
        evidence_ids = [nodes[int(i)].id for i in hit_idx[:4]]
        progress.append(
            StateProgress(
                state=phase.name,
                reached=bool(hit_idx),
                evidence_ids=evidence_ids,
            )
        )

    last_reached = max((i for i, p in enumerate(progress) if p.reached), default=-1)
    stopped_at = None
    for i, p in enumerate(progress):
        if i > last_reached:
            stopped_at = p.state
            break
    return LifecycleProjection(
        phases=progress,
        last_reached=progress[last_reached].state if last_reached >= 0 else None,
        stopped_at=stopped_at,
    )
