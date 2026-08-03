"""Formal Agent: what did the formal tool actually prove?

Formal verdicts carry information simulation cannot: a counterexample is a
proof of a design bug, while a vacuous pass is a proof that the *property* was
wrong. Those two point in opposite directions, which is exactly why they
deserve a specialist rather than a shared rule.
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
class FormalAgent(Agent):
    """The formal-verification specialist."""

    agent_id = "formal"
    domain = AgentDomain.FORMAL

    def applies_to(self, context: AgentContext) -> bool:
        return bool(context.nodes_of_type(ArtifactType.FORMAL_RESULT))

    def assess(self, context: AgentContext) -> AgentResult:
        nodes = context.nodes_of_type(ArtifactType.FORMAL_RESULT)
        by_status: dict[str, list] = {}
        for node in nodes:
            status = str(node.attributes.get("status", "unknown"))
            by_status.setdefault(status, []).append(node)

        observations: list[AgentObservation] = []
        hypotheses: list[AgentHypothesis] = []
        recommendations: list[AgentRecommendation] = []
        limitations: list[str] = []

        for status in sorted(by_status):
            group = by_status[status]
            properties = sorted(
                {str(n.attributes.get("property", "")) for n in group if n.attributes.get("property")}
            )
            observations.append(
                AgentObservation(
                    statement=(
                        f"{len(group)} formal property verdict(s) came back '{status}'"
                        + (f": {', '.join(properties[:4])}" if properties else "")
                        + "."
                    ),
                    evidence_ids=[n.id for n in group],
                )
            )

        falsified = by_status.get("falsified", [])
        if falsified:
            hypotheses.append(
                AgentHypothesis(
                    category=HypothesisCategory.RTL_BUG,
                    statement=(
                        "A formal engine produced a counterexample: the design provably "
                        "violates a stated property, which is direct evidence of a design "
                        "bug rather than a probabilistic inference from simulation."
                    ),
                    confidence=0.88,
                    evidence_ids=[n.id for n in falsified],
                )
            )
            recommendations.append(
                AgentRecommendation(
                    action="Replay the formal counterexample trace against the RTL",
                    rationale=(
                        "A counterexample is a minimal, reproducible failure trace; it is "
                        "the shortest path from symptom to root cause available."
                    ),
                    priority=1,
                    evidence_ids=[n.id for n in falsified[:3]],
                )
            )

        vacuous = by_status.get("vacuous", [])
        if vacuous:
            hypotheses.append(
                AgentHypothesis(
                    category=HypothesisCategory.TESTBENCH_ISSUE,
                    statement=(
                        "One or more properties passed vacuously: their antecedent was never "
                        "satisfied, so the property proved nothing about the design and the "
                        "checking code itself is what needs attention."
                    ),
                    confidence=0.70,
                    evidence_ids=[n.id for n in vacuous],
                )
            )
            recommendations.append(
                AgentRecommendation(
                    action="Fix the vacuous properties before trusting the formal result",
                    rationale=(
                        "A vacuous pass is indistinguishable from a real pass in a summary "
                        "table, so the current proof status overstates real coverage."
                    ),
                    priority=2,
                    evidence_ids=[n.id for n in vacuous[:3]],
                )
            )

        inconclusive = by_status.get("inconclusive", []) + by_status.get("unreachable", [])
        if inconclusive:
            limitations.append(
                f"{len(inconclusive)} property verdict(s) were inconclusive or unreachable, "
                "so the formal result is incomplete: absence of a counterexample here is "
                "not evidence of correctness."
            )
        if not falsified and not vacuous:
            limitations.append(
                "No counterexample and no vacuous pass were reported, so formal evidence "
                "does not discriminate between the competing hypotheses for this run."
            )
        return self.build(
            context,
            observations=observations,
            hypotheses=hypotheses,
            recommendations=recommendations,
            limitations=limitations,
        )
