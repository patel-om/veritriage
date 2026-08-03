"""Regression Agent: have we seen this before, and what was it last time?

Historical precedent is the one input that is about other runs, so this agent
is careful about citation: it cites *this* run's failing evidence, the evidence
that produced the signature which matched history, never a node ID from a past
run that does not exist in this graph.
"""

from __future__ import annotations

from veritriage.agents.base import Agent
from veritriage.agents.context import AgentContext
from veritriage.agents.registry import register_agent
from veritriage.models import (
    AgentDomain,
    AgentHypothesis,
    AgentObservation,
    AgentRecommendation,
    AgentResult,
    HypothesisCategory,
)

#: Historical failure class -> the hypothesis category it implies today.
_HISTORY_CATEGORY = {
    "compile_failure": HypothesisCategory.BUILD_ISSUE,
    "testbench_failure": HypothesisCategory.TESTBENCH_ISSUE,
    "assertion_failure": HypothesisCategory.RTL_BUG,
    "timeout": HypothesisCategory.RTL_BUG,
}


@register_agent
class RegressionAgent(Agent):
    """The historical-memory specialist."""

    agent_id = "regression"
    domain = AgentDomain.REGRESSION

    def applies_to(self, context: AgentContext) -> bool:
        return context.history is not None

    def assess(self, context: AgentContext) -> AgentResult:
        history = context.history
        assert history is not None  # guarded by applies_to
        failing = context.failing_nodes()
        cited = [n.id for n in failing]
        observations: list[AgentObservation] = []
        hypotheses: list[AgentHypothesis] = []
        recommendations: list[AgentRecommendation] = []
        limitations: list[str] = []

        if history.seen_before:
            observations.append(
                AgentObservation(
                    statement=(
                        f"This exact failure signature has been recorded {history.times_seen} "
                        "time(s) before: it is a recurrence, not a new failure."
                    ),
                    evidence_ids=cited,
                )
            )
        else:
            observations.append(
                AgentObservation(
                    statement=(
                        "This failure signature is new to the regression database, so no "
                        "prior diagnosis can be reused."
                    ),
                    evidence_ids=cited,
                )
            )

        for similar in history.similar[:3]:
            observations.append(
                AgentObservation(
                    statement=(
                        f"A prior regression ({similar.regression_id}, "
                        f"{similar.classification}) resembles this one at similarity "
                        f"{similar.score:.2f}; its recorded root cause was: {similar.root_cause}"
                    ),
                    evidence_ids=cited,
                )
            )

        best = next(
            (
                s
                for s in history.similar
                if _HISTORY_CATEGORY.get(s.classification) is not None
            ),
            None,
        )
        if best is not None and cited:
            category = _HISTORY_CATEGORY[best.classification]
            # Precedent is strong evidence but never proof that this run shares
            # that cause; discount it, and discount harder without a signature match.
            factor = 0.80 if best.signature_match else 0.60
            hypotheses.append(
                AgentHypothesis(
                    category=category,
                    statement=(
                        f"History favors {category.display_name}: the most similar prior "
                        f"regression ({best.regression_id}) was classified "
                        f"{best.classification} and was resolved as: {best.root_cause}"
                    ),
                    confidence=round(min(0.80, best.score * factor), 4),
                    evidence_ids=cited,
                )
            )
            recommendations.append(
                AgentRecommendation(
                    action=f"Review the resolution of prior regression {best.regression_id}",
                    rationale=(
                        "The current failure resembles it at similarity "
                        f"{best.score:.2f}"
                        + (" with an identical signature" if best.signature_match else "")
                        + ", so its recorded fix is the cheapest hypothesis to test first."
                    ),
                    priority=1,
                    evidence_ids=cited[:3],
                )
            )
        elif history.similar:
            limitations.append(
                "Similar regressions exist but none carries a failure class that maps to a "
                "hypothesis category, so history informs context here rather than ranking."
            )
        else:
            limitations.append(
                "No similar historical regression was found, so this assessment carries no "
                "precedent-based position."
            )
        if not cited:
            limitations.append(
                "This run produced no failing evidence to attach the historical precedent to."
            )
        return self.build(
            context,
            observations=observations,
            hypotheses=hypotheses,
            recommendations=recommendations,
            limitations=limitations,
        )
