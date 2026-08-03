"""Project Intelligence Agent: did this run ever reach real design traffic?

The cheapest question in verification debug and the one most often skipped. A
run that died in connect_phase never exercised the DUT, so every design-side
hypothesis is premature no matter how alarming the messages look.
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

#: Lifecycle phase names that mean real design traffic was exercised.
_TRAFFIC_PHASES = frozenset(
    {"traffic", "stimulus", "sequence", "check", "checking", "report"}
)

#: Log origin -> the hypothesis category it implicates.
_ORIGIN_CATEGORY = {
    "vip": HypothesisCategory.TESTBENCH_ISSUE,
    "testbench": HypothesisCategory.TESTBENCH_ISSUE,
    "infrastructure": HypothesisCategory.INFRASTRUCTURE_ISSUE,
    "simulator": HypothesisCategory.INFRASTRUCTURE_ISSUE,
}


@register_agent
class ProjectIntelligenceAgent(Agent):
    """The project-structure specialist."""

    agent_id = "project"
    domain = AgentDomain.PROJECT

    def applies_to(self, context: AgentContext) -> bool:
        return context.project is not None

    def assess(self, context: AgentContext) -> AgentResult:
        project = context.project
        assert project is not None  # guarded by applies_to
        observations: list[AgentObservation] = []
        hypotheses: list[AgentHypothesis] = []
        recommendations: list[AgentRecommendation] = []
        limitations: list[str] = []

        if project.identified_protocols:
            named = ", ".join(
                f"{p.name} on {', '.join(p.interfaces[:2])}"
                for p in project.identified_protocols[:3]
            )
            observations.append(
                AgentObservation(
                    statement=(
                        f"The project's DUT ({project.dut_top or 'unnamed top'}) exposes "
                        f"identified protocol interfaces: {named}."
                    ),
                    evidence_ids=[],
                )
            )

        lifecycle = project.lifecycle
        if lifecycle is not None and lifecycle.stopped_at:
            reached_traffic = any(
                p.reached and p.state.lower() in _TRAFFIC_PHASES for p in lifecycle.phases
            )
            evidence = sorted({i for p in lifecycle.phases if p.reached for i in p.evidence_ids})
            observations.append(
                AgentObservation(
                    statement=(
                        f"Against the expected simulation lifecycle the run reached "
                        f"'{lifecycle.last_reached}' and stopped at '{lifecycle.stopped_at}'."
                    ),
                    evidence_ids=evidence,
                )
            )
            if not reached_traffic and evidence:
                hypotheses.append(
                    AgentHypothesis(
                        category=HypothesisCategory.BUILD_ISSUE,
                        statement=(
                            "The run stopped before any design traffic was driven, so the "
                            "failure precedes real DUT activity: a build, elaboration, or "
                            "environment-construction problem explains it better than a "
                            "design bug."
                        ),
                        confidence=0.55,
                        evidence_ids=evidence,
                    )
                )
                recommendations.append(
                    AgentRecommendation(
                        action=(
                            f"Investigate the '{lifecycle.stopped_at}' phase before opening "
                            "any waveform"
                        ),
                        rationale=(
                            "No design traffic ran, so waveform and RTL analysis cannot yet "
                            "be productive."
                        ),
                        priority=1,
                        evidence_ids=evidence[:3],
                    )
                )
        elif lifecycle is None:
            limitations.append(
                "The project model declares no simulation lifecycle, so how far this run "
                "progressed could not be established."
            )

        origins = {k: v for k, v in project.log_origins.items() if v}
        if origins:
            shown = ", ".join(f"{origin} ({count})" for origin, count in sorted(origins.items()))
            observations.append(
                AgentObservation(
                    statement=f"Failing evidence by origin, per the project's log profile: {shown}.",
                    evidence_ids=[n.id for n in context.failing_nodes()],
                )
            )
        origin_signal = context.signal("project:log-origin")
        if origin_signal is not None:
            leading_origin = max(
                (o for o in origins if o in _ORIGIN_CATEGORY),
                key=lambda o: origins[o],
                default=None,
            )
            if leading_origin is not None and origin_signal.evidence_ids:
                hypotheses.append(
                    AgentHypothesis(
                        category=_ORIGIN_CATEGORY[leading_origin],
                        statement=(
                            f"Most failing messages originate in {leading_origin} code per the "
                            "project's log profile, which points away from the design and "
                            "toward the environment that produced them."
                        ),
                        confidence=0.50,
                        evidence_ids=list(origin_signal.evidence_ids),
                    )
                )
        scope_signal = context.signal("project:scope-ownership")
        if scope_signal is not None and scope_signal.evidence_ids:
            hypotheses.append(
                AgentHypothesis(
                    category=HypothesisCategory.RTL_BUG,
                    statement=(
                        "The failing scope resolves to a specific DUT IP block in the project "
                        "model, which localizes the failure to design logic rather than to "
                        "the surrounding environment."
                    ),
                    confidence=0.45,
                    evidence_ids=list(scope_signal.evidence_ids),
                )
            )
        if not project.dut.modules:
            limitations.append(
                "The project model carries no DUT hierarchy, so failing scopes could not be "
                "resolved to design modules."
            )
        return self.build(
            context,
            observations=observations,
            hypotheses=hypotheses,
            recommendations=recommendations,
            limitations=limitations,
        )
