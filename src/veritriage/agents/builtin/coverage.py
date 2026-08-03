"""Coverage Agent: is the logic around this failure under-exercised?

Coverage rarely explains a failure on its own, so this agent deliberately
holds a modest position and says so. Its value is corroboration: a hole
overlapping the failing scope makes a latent design bug more plausible and a
missing stimulus scenario more plausible at the same time.
"""

from __future__ import annotations

from veritriage.agents.base import Agent
from veritriage.agents.context import AgentContext
from veritriage.agents.registry import register_agent
from veritriage.graph.model import ArtifactType
from veritriage.models import (
    AgentDomain,
    AgentHypothesis,
    AgentObservation,
    AgentRecommendation,
    AgentResult,
    HypothesisCategory,
)


@register_agent
class CoverageAgent(Agent):
    """The coverage specialist."""

    agent_id = "coverage"
    domain = AgentDomain.COVERAGE

    def applies_to(self, context: AgentContext) -> bool:
        return bool(context.nodes_of_type(ArtifactType.COVERAGE))

    def assess(self, context: AgentContext) -> AgentResult:
        coverage_nodes = context.nodes_of_type(ArtifactType.COVERAGE)
        holes = [n for n in coverage_nodes if bool(n.attributes.get("is_hole"))]
        observations: list[AgentObservation] = []
        hypotheses: list[AgentHypothesis] = []
        recommendations: list[AgentRecommendation] = []
        limitations: list[
            str
        ] = [
            "Coverage input is a scope-level summary, so this assessment cannot name the "
            "specific uncovered bins or crosses."
        ]

        if not holes:
            observations.append(
                AgentObservation(
                    statement=(
                        f"{len(coverage_nodes)} coverage scope(s) were reported and none "
                        "fell below the hole threshold."
                    ),
                    evidence_ids=[n.id for n in coverage_nodes],
                )
            )
            return self.build(
                context,
                observations=observations,
                limitations=[
                    *limitations,
                    "No coverage holes were present, so coverage neither supports nor "
                    "weakens any hypothesis for this failure.",
                ],
            )

        scopes = sorted({n.module for n in holes if n.module})
        observations.append(
            AgentObservation(
                statement=(
                    f"{len(holes)} coverage hole(s) were reported"
                    + (f" in {', '.join(scopes[:4])}" if scopes else "")
                    + "."
                ),
                evidence_ids=[n.id for n in holes],
            )
        )

        correlated = context.signal("coverage-hole-near-failure")
        if correlated is not None:
            observations.append(
                AgentObservation(
                    statement=(
                        "At least one coverage hole overlaps the failing scope: the logic "
                        "around this failure is under-exercised."
                    ),
                    evidence_ids=list(correlated.evidence_ids),
                )
            )
            cited = sorted(set(correlated.evidence_ids) or {n.id for n in holes})
            hypotheses.append(
                AgentHypothesis(
                    category=HypothesisCategory.RTL_BUG,
                    statement=(
                        "A latent design bug is plausible in logic the regression barely "
                        "exercises: the failing scope overlaps a coverage hole, so this "
                        "path has had little opportunity to be proven correct."
                    ),
                    confidence=0.35,
                    evidence_ids=cited,
                )
            )
            hypotheses.append(
                AgentHypothesis(
                    category=HypothesisCategory.TESTBENCH_ISSUE,
                    statement=(
                        "The stimulus may be missing scenarios around the failing scope, so "
                        "the failure could be an artifact of an incompletely constrained test "
                        "rather than of the design."
                    ),
                    confidence=0.28,
                    evidence_ids=cited,
                )
            )
            recommendations.append(
                AgentRecommendation(
                    action="Add directed stimulus for the uncovered scope around the failure",
                    rationale=(
                        "The failing logic overlaps a coverage hole; closing it either "
                        "reproduces the failure deterministically or proves the path correct."
                    ),
                    priority=3,
                    evidence_ids=cited[:3],
                )
            )
        else:
            limitations.append(
                "No coverage hole could be correlated to a failing scope, so the reported "
                "holes are not evidence about this particular failure."
            )
        return self.build(
            context,
            observations=observations,
            hypotheses=hypotheses,
            recommendations=recommendations,
            limitations=limitations,
        )
