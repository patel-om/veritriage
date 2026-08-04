"""Curated knowledge as plan steps.

The strongest source, because it is the only one whose content was written by a
domain expert rather than assembled from a template. A matched pattern's
playbook is already an ordered debug sequence with the signals worth pulling
up; this source restates those steps as candidates and records exactly which
playbook step each came from.

Nothing is invented here. If the packs say nothing, this source proposes
nothing.
"""

from __future__ import annotations

from veritriage.models import HypothesisCategory, StepKind
from veritriage.planning.context import PlanningContext, StepCandidate
from veritriage.planning.registry import StepSource, register_source

#: Pack ownership label prefix -> the hypothesis category it implicates. The
#: report view carries a display label, so matching is by prefix.
_OWNERSHIP_CATEGORY = (
    ("design", HypothesisCategory.RTL_BUG),
    ("testbench", HypothesisCategory.TESTBENCH_ISSUE),
    ("infrastructure", HypothesisCategory.INFRASTRUCTURE_ISSUE),
    ("build", HypothesisCategory.BUILD_ISSUE),
)

#: How many steps of one playbook enter the plan. A playbook is a full
#: procedure; a plan is the front of it, with the rest reachable in branches.
MAX_STEPS_PER_PLAYBOOK = 3


def _category_for(ownership: str) -> HypothesisCategory | None:
    lowered = ownership.lower()
    for prefix, category in _OWNERSHIP_CATEGORY:
        if lowered.startswith(prefix):
            return category
    return None


@register_source
class KnowledgePlaybookSource(StepSource):
    """Debug playbook steps from the patterns this evidence matched."""

    source_id = "knowledge-playbooks"
    rank = 10  # curated expertise outranks generated templates

    def applies_to(self, context: PlanningContext) -> bool:
        knowledge = context.report.knowledge
        return knowledge is not None and any(p.playbook for p in knowledge.patterns)

    def propose(self, context: PlanningContext) -> list[StepCandidate]:
        knowledge = context.report.knowledge
        if knowledge is None:
            return []
        candidates: list[StepCandidate] = []
        # Strongest match first, so its opening step earns the curated bonus.
        matched = sorted(knowledge.patterns, key=lambda p: (-p.score, p.pattern_id))
        for rank, pattern in enumerate(matched):
            if pattern.playbook is None:
                continue
            category = _category_for(pattern.ownership)
            evidence = sorted(
                {i for ids in pattern.matched_evidence.values() for i in ids}
            )
            for step in pattern.playbook.steps[:MAX_STEPS_PER_PLAYBOOK]:
                first_of_best = rank == 0 and step.order == 1
                candidates.append(
                    StepCandidate(
                        kind=StepKind.INSPECT if step.signals else StepKind.VERIFY,
                        action=step.action,
                        purpose=(
                            step.detail
                            or f"Step {step.order} of the curated '{pattern.playbook.name}' "
                            f"procedure for {pattern.name}."
                        ),
                        derived_from=(
                            f"knowledge:playbook:{pattern.playbook.playbook_id}"
                            f"#{step.order}"
                        ),
                        addresses=[category] if category else [],
                        required_evidence=(
                            [f"waveform coverage of {', '.join(step.signals[:3])}"]
                            if step.signals
                            else []
                        ),
                        expected_observations=[
                            f"Behaviour consistent with '{pattern.name}' confirms the "
                            f"{pattern.pack} diagnosis",
                            "Behaviour inconsistent with it moves the investigation to the "
                            "next competing explanation",
                        ],
                        signals=list(step.signals),
                        module=context.failing_scope(),
                        # A curated procedure's opening step is cheap and decisive;
                        # later steps cost more because they presume the earlier ones.
                        effort=1 if step.order == 1 else 2,
                        evidence_ids=context.resolve(evidence),
                        bonus=1.0 if first_of_best else 0.4,
                        bonus_reason=(
                            f"opening step of the highest-scoring matched pattern "
                            f"('{pattern.name}', {pattern.score:.0%} match)"
                            if first_of_best
                            else f"curated procedure for a matched {pattern.pack} pattern"
                        ),
                    )
                )
        return candidates
