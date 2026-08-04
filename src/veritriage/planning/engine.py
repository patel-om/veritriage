"""The Planner: gather, deduplicate, value, order, branch.

    finished AnalysisReport
        -> StepSources propose candidates (each derived from an existing artifact)
        -> deduplicate by action, keeping the best-provenance version
        -> value each (value / effort, every term recorded)
        -> order deterministically
        -> promote the strongest to root steps, use the rest for branches
        -> DebugPlan

The Planner contributes structure, ordering, branching, and valuation. It never
writes debug advice: every step names the artifact it restates. It never
executes: nothing here opens a file or runs a tool.

Planning is a pure function of the report. The same analysis always produces a
byte-identical plan, including ``plan_id``, which is a content digest.
"""

from __future__ import annotations

import hashlib
import json

from veritriage.models import (
    CompletionCondition,
    DebugPlan,
    DebugStep,
    EvidenceRequest,
    HypothesisCategory,
)
from veritriage.planning.context import PlanningContext, StepCandidate
from veritriage.planning.registry import StepSource, default_sources
from veritriage.planning.sources.gaps import EvidenceGapSource
from veritriage.planning.tree import (
    build_decision,
    completion_statements,
    risks,
)
from veritriage.planning.valuation import plan_effort, sort_key, target_of, value_of

#: How many steps stand at the root of a plan. Beyond this an engineer stops
#: reading; the rest remain reachable inside branches.
MAX_ROOT_STEPS = 6

#: How many follow-up steps are kept per category for branch construction.
MAX_FOLLOWUPS_PER_CATEGORY = 3


class Planner:
    """Builds one investigation plan from one finished analysis."""

    def __init__(self, sources: list[StepSource] | None = None) -> None:
        self._sources = sources  # None -> registry defaults, resolved per run

    def plan(self, context: PlanningContext) -> DebugPlan:
        """Derive the investigation plan. Pure function of the context."""
        sources = self._sources if self._sources is not None else default_sources()
        sources = sorted(sources, key=lambda s: (s.rank, s.source_id))

        candidates: list[StepCandidate] = []
        contributed: list[str] = []
        requests: list[EvidenceRequest] = []
        for source in sources:
            try:
                if not source.applies_to(context):
                    continue
                proposed = source.propose(context)
            except Exception:  # one broken source must not cost a plan
                continue
            if isinstance(source, EvidenceGapSource):
                requests.extend(source.requests(context))
            if proposed:
                contributed.append(source.source_id)
                candidates.extend(proposed)

        steps = self._to_steps(self._deduplicate(candidates), context)
        steps.sort(key=sort_key)

        root = steps[:MAX_ROOT_STEPS]
        remainder = steps[MAX_ROOT_STEPS:]
        if root:
            followups = self._followups(root[1:] + remainder)
            decision = build_decision(context, root[0], followups)
            if decision is not None:
                root[0] = root[0].model_copy(update={"decision": decision})

        target = target_of(context)
        plan = DebugPlan(
            plan_id="",
            objective=self._objective(context, target),
            strategy=self._strategy(context, contributed),
            steps=root,
            evidence_requests=requests,
            completion_conditions=[
                CompletionCondition(
                    statement=statement, satisfied=satisfied, evidence_ids=evidence
                )
                for statement, satisfied, evidence in completion_statements(context)
            ],
            estimated_effort=plan_effort(root),
            confidence_target=target,
            risks=risks(context),
            historical_success=self._historical_success(context),
            sources=contributed,
        )
        return plan.model_copy(update={"plan_id": _digest(plan)})

    # --- Assembly -----------------------------------------------------------

    @staticmethod
    def _deduplicate(candidates: list[StepCandidate]) -> list[StepCandidate]:
        """One step per action, keeping the best-provenance version.

        Sources are visited in rank order, so the first proposal of an action
        is the most authoritative one (curated knowledge before a specialist's
        suggestion before a generic template). Later duplicates only widen the
        surviving candidate's citations: two producers agreeing is
        corroboration, not repetition.
        """
        kept: dict[str, StepCandidate] = {}
        for candidate in candidates:
            key = candidate.action.strip().lower()
            existing = kept.get(key)
            if existing is None:
                kept[key] = candidate
                continue
            kept[key] = existing.model_copy(
                update={
                    "evidence_ids": sorted(
                        set(existing.evidence_ids) | set(candidate.evidence_ids)
                    ),
                    "addresses": sorted(
                        set(existing.addresses) | set(candidate.addresses),
                        key=lambda c: c.value,
                    ),
                    "signals": sorted(set(existing.signals) | set(candidate.signals)),
                }
            )
        return list(kept.values())

    @staticmethod
    def _to_steps(
        candidates: list[StepCandidate], context: PlanningContext
    ) -> list[DebugStep]:
        steps: list[DebugStep] = []
        for candidate in candidates:
            step_id = "step-" + hashlib.sha1(
                f"{candidate.derived_from}|{candidate.action}".encode("utf-8")
            ).hexdigest()[:10]
            steps.append(
                DebugStep(
                    step_id=step_id,
                    kind=candidate.kind,
                    action=candidate.action,
                    purpose=candidate.purpose,
                    derived_from=candidate.derived_from,
                    addresses=list(candidate.addresses),
                    required_evidence=list(candidate.required_evidence),
                    expected_observations=list(candidate.expected_observations),
                    signals=list(candidate.signals),
                    module=candidate.module,
                    valuation=value_of(candidate, context),
                    evidence_ids=context.resolve(list(candidate.evidence_ids)),
                )
            )
        return steps

    @staticmethod
    def _followups(steps: list[DebugStep]) -> dict[HypothesisCategory, list[DebugStep]]:
        """Remaining steps grouped by the explanation they bear on."""
        grouped: dict[HypothesisCategory, list[DebugStep]] = {}
        for step in steps:
            for category in step.addresses:
                bucket = grouped.setdefault(category, [])
                if len(bucket) < MAX_FOLLOWUPS_PER_CATEGORY:
                    bucket.append(step)
        return grouped

    # --- Narrative (assembled from conclusions, never invented) -------------

    @staticmethod
    def _objective(
        context: PlanningContext, target: HypothesisCategory | None
    ) -> str:
        classification = context.report.classification.category.display_name
        if target is None:
            return f"Establish the root cause of this {classification.lower()}."
        confidence = context.confidence_of(target)
        competing = [c for c in context.competing() if c != target]
        objective = (
            f"Confirm or reject {target.display_name} as the cause of this "
            f"{classification.lower()} (currently {confidence:.0%} confidence)"
        )
        if competing:
            names = ", ".join(sorted(c.display_name for c in competing))
            objective += f", separating it from {names}"
        return objective + "."

    @staticmethod
    def _strategy(context: PlanningContext, contributed: list[str]) -> str:
        protocols = context.protocols
        parts: list[str] = []
        if "knowledge-playbooks" in contributed:
            parts.append(
                "lead with the curated debug procedure for the matched pattern"
            )
        if protocols:
            parts.append(
                f"scoped to the {', '.join(protocols[:3])} interface(s) this project uses"
            )
        if "evidence-gaps" in contributed:
            parts.append("collect the missing evidence that would settle the question")
        if not parts:
            parts.append("work the highest-value, lowest-cost checks first")
        competing = len(context.competing())
        closing = (
            f" Two or more explanations remain live ({competing}), so the opening step "
            "is chosen to tell them apart rather than to confirm the leader."
            if competing >= 2
            else " One explanation dominates, so the plan aims at confirming it directly."
        )
        return "Work cheapest-decisive-first: " + "; then ".join(parts) + "." + closing

    @staticmethod
    def _historical_success(context: PlanningContext) -> float | None:
        """How often the leading approach worked before, when learning knows."""
        learning = context.report.learning
        if learning is None:
            return None
        rated = [
            outcome.usefulness
            for outcome in learning.common_recommendations
            if outcome.usefulness is not None
        ]
        if not rated:
            return None
        return round(sum(rated) / len(rated), 4)


def _digest(plan: DebugPlan) -> str:
    """Content digest over the plan's structure, excluding the ID itself."""
    payload = plan.model_dump(mode="json", exclude={"plan_id"})
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "dbg-" + hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:12]


def build_plan(report, graph) -> DebugPlan:
    """Convenience entry point: plan one finished analysis."""
    return Planner().plan(PlanningContext(report=report, graph=graph))
