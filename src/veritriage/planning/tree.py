"""Decision points: how a plan branches without executing anything.

Two condition kinds, which is what lets planning branch while remaining both
deterministic and strictly advisory:

* **AUTO** conditions are predicates over evidence already in the Evidence
  Graph. If this run already settles the question, the Planner resolves the
  branch and records why. No tool runs; the answer was already in the evidence.
* **ASK** conditions need a human to look at something. The Planner renders the
  question and leaves both branches standing.

Planning never runs a tool, opens a file, or performs a step. Interactive
planning and live debugging arrive later by supplying observations back into
ASK conditions; the tree structure does not change to accommodate them.
"""

from __future__ import annotations

from veritriage.graph.model import ArtifactType
from veritriage.models import (
    ConditionKind,
    DebugStep,
    DecisionPoint,
    HypothesisCategory,
    PlanBranch,
)
from veritriage.planning.context import PlanningContext

#: How many follow-up steps one branch carries. A branch is a direction, not a
#: second full plan.
MAX_BRANCH_STEPS = 2


def auto_resolution(context: PlanningContext) -> tuple[str, str] | None:
    """A question this run's evidence already answers, if there is one.

    Returns (outcome, reason). Deterministic and read-only: it inspects the
    graph the analysis already produced.
    """
    compile_failures = [
        n
        for n in context.nodes_of_type(ArtifactType.COMPILE_LOG)
        if n.is_failing
    ]
    if compile_failures:
        return (
            "no, the build is not clean",
            f"{len(compile_failures)} compile/elaboration diagnostic(s) are already in "
            "the evidence, so everything downstream is a consequence of the broken "
            "build and runtime investigation is premature.",
        )
    assertions = [
        n for n in context.nodes_of_type(ArtifactType.ASSERTION) if n.is_failing
    ]
    if assertions:
        return (
            "yes, an assertion already fired",
            f"{len(assertions)} assertion(s) fired in this run, pinpointing where "
            "behaviour first diverged from the specified invariant.",
        )
    return None


def build_decision(
    context: PlanningContext,
    parent: DebugStep,
    followups: dict[HypothesisCategory, list[DebugStep]],
) -> DecisionPoint | None:
    """Open a branch under ``parent``, one direction per live explanation.

    The tree's shape follows the competing hypotheses rather than a fixed
    template: two live explanations produce two branches, and a foregone
    conclusion produces none. Branch steps are drawn from the same derived
    candidate pool as the root steps, so nothing in a branch is invented.
    """
    competing = [c for c in context.competing() if followups.get(c)]
    if len(competing) < 2:
        return None

    # A branch that gives the same advice whatever the answer is not a branch.
    # Steps are assigned greedily, most category-specific first, and a step
    # already spent on one outcome is not offered again on another.
    spent: set[str] = set()
    branches: list[PlanBranch] = []
    for category in competing:
        available = [s for s in followups.get(category, []) if s.step_id not in spent]
        # Prefer steps that bear on this explanation alone: those are the ones
        # that actually discriminate once the observation is in.
        available.sort(key=lambda s: (len(s.addresses), -s.valuation.priority_score))
        steps = available[:MAX_BRANCH_STEPS]
        spent.update(s.step_id for s in steps)
        if not steps:
            continue
        branches.append(
            PlanBranch(
                outcome=f"The observation is consistent with {category.display_name}",
                rationale=(
                    f"{category.display_name} is still live at confidence "
                    f"{context.confidence_of(category):.0%}; these are the cheapest "
                    "next steps that would confirm or reject it."
                ),
                steps=steps,
            )
        )
    if len(branches) < 2:
        return None

    resolution = auto_resolution(context)
    condition = ConditionKind.AUTO if resolution is not None else ConditionKind.ASK
    return DecisionPoint(
        decision_id=f"dec-{parent.step_id}",
        question=(
            f"After '{parent.action}', which explanation does the observation support?"
        ),
        condition=condition,
        resolved_outcome=resolution[0] if resolution else None,
        resolved_because=resolution[1] if resolution else None,
        branches=branches,
        evidence_ids=list(parent.evidence_ids),
    )


def completion_statements(context: PlanningContext) -> list[tuple[str, bool, list[str]]]:
    """(statement, already satisfied, evidence) for knowing the work is done.

    Deliberately concrete. "Investigate the failure" is not a completion
    condition; "a specific mechanism explains every failing message" is.
    """
    failing = context.failing_nodes()
    cited = [n.id for n in failing[:3]]
    leading = context.leading
    statements: list[tuple[str, bool, list[str]]] = []

    if leading is not None:
        statements.append(
            (
                f"A concrete mechanism is identified that explains "
                f"{leading.category.display_name}, and it accounts for every failing "
                "message in this run.",
                False,
                cited,
            )
        )
    statements.append(
        (
            "The competing explanations have been reduced to one, with evidence that "
            "rules out the others rather than merely favouring the winner.",
            len(context.competing()) <= 1,
            cited,
        )
    )
    if context.report.knowledge is not None and context.report.knowledge.patterns:
        pattern = context.report.knowledge.patterns[0]
        statements.append(
            (
                f"The behaviour is confirmed to match (or provably not match) the known "
                f"pattern '{pattern.name}'.",
                False,
                context.resolve(
                    sorted({i for ids in pattern.matched_evidence.values() for i in ids})
                )[:3],
            )
        )
    statements.append(
        (
            "A fix or a filed defect exists, with the failing test reproducing before "
            "the change and passing after it.",
            False,
            cited,
        )
    )
    return statements


def risks(context: PlanningContext) -> list[str]:
    """What could make this plan mislead. Stated, never hidden."""
    found: list[str] = []
    if len(context.competing()) >= 3:
        found.append(
            "Three or more explanations remain close in confidence, so the leading "
            "step may not be decisive; expect to work more than one branch."
        )
    if context.report.project is None:
        found.append(
            "No project model was supplied, so scopes were matched by name rather than "
            "resolved against the real DUT hierarchy, and steps may point at the wrong "
            "block."
        )
    if not context.has_artifact(ArtifactType.WAVEFORM_METADATA):
        found.append(
            "No waveform metadata is available, so every signal-level step in this plan "
            "is a request to go and look rather than something already corroborated."
        )
    leading = context.leading
    if leading is not None and leading.confidence < 0.4:
        found.append(
            f"The leading hypothesis sits at only {leading.confidence:.0%} confidence, "
            "so this plan is exploratory: treat early steps as narrowing rather than "
            "confirming."
        )
    if context.report.history is not None and context.report.history.seen_before:
        found.append(
            "This signature has been seen before. If the earlier diagnosis was wrong, "
            "the precedent step will point the same wrong way again."
        )
    return found
