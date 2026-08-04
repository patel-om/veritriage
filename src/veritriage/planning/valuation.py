"""Explainable valuation: what a step is worth against what it costs.

The whole optimization, stated once:

    value          = discrimination + confidence + curated bonus + historical
    effort         = 1 low, 2 medium, 3 high   (from the source, never invented)
    priority_score = value / effort

High confidence and low cost sort earlier; low confidence and high effort sort
later. Every term is recorded in :class:`StepValuation` with a plain-language
reason, so a step's position in the plan reads line by line exactly like a
`ConfidenceTrace` or an `AgentContribution`.

Integers and bounded floats throughout. There are no learned weights, no
opaque scores, and nothing here that cannot be printed in a report.
"""

from __future__ import annotations

from veritriage.models import HypothesisCategory, StepValuation
from veritriage.planning.context import PlanningContext, StepCandidate

#: A step that separates two live explanations is worth more than one that
#: confirms a foregone conclusion. Paid per competing category it addresses.
DISCRIMINATION_WEIGHT = 0.5

#: How much the served hypothesis's own confidence contributes.
CONFIDENCE_WEIGHT = 1.0

#: Ceiling on what curated provenance (a playbook) may add.
MAX_CURATED_BONUS = 1.0

#: Ceiling on what history may move a step, in either direction. Bounded for
#: the same reason M13 calibration is: no amount of history should silence a
#: step the current evidence justifies.
MAX_HISTORICAL = 0.5


def value_of(candidate: StepCandidate, context: PlanningContext) -> StepValuation:
    """Compute and explain one candidate's priority."""
    terms: list[str] = []
    competing = set(context.competing())
    addressed = [c for c in candidate.addresses if c in competing]

    discrimination = DISCRIMINATION_WEIGHT * len(addressed)
    if addressed:
        names = ", ".join(sorted(c.display_name for c in addressed))
        terms.append(
            f"+{discrimination:.2f} separates {len(addressed)} live explanation(s): {names}"
        )

    confidence = 0.0
    if candidate.addresses:
        best = max(context.confidence_of(c) for c in candidate.addresses)
        confidence = round(CONFIDENCE_WEIGHT * best, 4)
        if confidence:
            leader = max(candidate.addresses, key=context.confidence_of)
            terms.append(
                f"+{confidence:.2f} serves {leader.display_name}, the strongest "
                f"hypothesis it bears on"
            )

    bonus = min(MAX_CURATED_BONUS, candidate.bonus)
    if bonus:
        terms.append(f"+{bonus:.2f} {candidate.bonus_reason or 'curated provenance'}")

    historical = round(
        max(-MAX_HISTORICAL, min(MAX_HISTORICAL, context.learning_strength(candidate.action))),
        4,
    )
    if historical > 0:
        terms.append(f"+{historical:.2f} engineers rated this action useful before")
    elif historical < 0:
        terms.append(f"{historical:.2f} engineers rated this action a dead end before")

    value = max(0.0, round(discrimination + confidence + bonus + historical, 4))
    effort = candidate.effort
    terms.append(
        f"/ effort {effort} ({'low' if effort == 1 else 'medium' if effort == 2 else 'high'})"
    )
    return StepValuation(
        value=value,
        effort=effort,
        priority_score=round(value / effort, 4),
        terms=terms,
    )


def sort_key(step) -> tuple:
    """Total, deterministic ordering: value density, then cheapness, then ID.

    Ties never resolve by chance: the third term is the content-derived step
    ID, so two runs over the same report always order identically.
    """
    return (-step.valuation.priority_score, step.valuation.effort, step.step_id)


def plan_effort(steps) -> int:
    """Total relative effort of a plan's root steps."""
    return sum(step.valuation.effort for step in steps)


def target_of(context: PlanningContext) -> HypothesisCategory | None:
    """The hypothesis a plan is built to confirm or reject."""
    leading = context.leading
    return leading.category if leading is not None else None
