"""Investigation progress: a pure function of a plan and a graph.

No persistent state, nothing recorded between runs. Progress is measured by
asking which of a plan's evidence requests the current Evidence Graph already
satisfies, which is exactly the question a second analysis answers by itself:
supply the waveform the plan asked for, re-run, and the request is satisfied.

This is what lets CI investigation and interactive planning arrive later
without a store: they call the same function with a newer graph.
"""

from __future__ import annotations

from veritriage.graph.graph import EvidenceGraph
from veritriage.graph.model import ArtifactType
from veritriage.models import ConditionKind, DebugPlan, PlanProgress


def plan_progress(plan: DebugPlan, graph: EvidenceGraph) -> PlanProgress:
    """How far along the investigation is, given the evidence available now."""
    present = {
        artifact.value
        for artifact in ArtifactType
        if graph.nodes_of_type(artifact)
    }
    satisfied: list[str] = []
    outstanding: list[str] = []
    for request in plan.evidence_requests:
        if request.satisfied_by and set(request.satisfied_by) & present:
            satisfied.append(request.request_id)
        else:
            outstanding.append(request.request_id)

    questions = [
        step.decision.question
        for step in plan.all_steps()
        if step.decision is not None
        and step.decision.condition is ConditionKind.ASK
        and step.decision.resolved_outcome is None
    ]
    total_requests = len(plan.evidence_requests)
    return PlanProgress(
        total_steps=len(plan.all_steps()),
        satisfied_requests=satisfied,
        outstanding_requests=outstanding,
        open_questions=questions,
        completion=(
            round(len(satisfied) / total_requests, 4) if total_requests else 1.0
        ),
    )
