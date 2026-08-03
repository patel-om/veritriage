"""RTL Agent: is the design itself the thing that misbehaved?

Localizes failing evidence to design scopes, corroborates with waveform
observations and fired assertions, and states honestly when scope attribution
is heuristic because no Project Model was supplied.
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

#: Scope-name fragments that mark a verification component rather than the DUT.
#: Used only when no Project Model is available to resolve scopes structurally.
_TESTBENCH_FRAGMENTS = (
    "env",
    "test",
    "tb_",
    "_tb",
    "vip",
    "agent",
    "monitor",
    "driver",
    "sequencer",
    "scoreboard",
    "predictor",
)

#: Waveform observation kinds that describe design-side loss of progress.
_DESIGN_SIDE_KINDS = frozenset(
    {"dead_clock", "stalled_fsm", "incomplete_handshake", "unretired_transaction"}
)


@register_agent
class RtlAgent(Agent):
    """The design specialist."""

    agent_id = "rtl"
    domain = AgentDomain.RTL

    def applies_to(self, context: AgentContext) -> bool:
        return bool(context.failing_nodes())

    def assess(self, context: AgentContext) -> AgentResult:
        failing = context.failing_nodes()
        observations: list[AgentObservation] = []
        limitations: list[str] = []
        confidence = 0.30

        dut_scoped = self._dut_scoped(context, failing)
        if dut_scoped:
            scopes = sorted({n.module for n in dut_scoped if n.module})
            observations.append(
                AgentObservation(
                    statement=(
                        f"{len(dut_scoped)} failing message(s) are scoped to design logic "
                        f"({', '.join(scopes[:4])})."
                    ),
                    evidence_ids=[n.id for n in dut_scoped],
                )
            )
            confidence += 0.20
        if context.project is None:
            limitations.append(
                "No Project Model was supplied, so design scopes were identified by name "
                "heuristics rather than resolved against the real DUT hierarchy."
            )

        assertions = [
            n
            for n in failing
            if n.artifact_type == ArtifactType.ASSERTION
        ]
        if assertions:
            observations.append(
                AgentObservation(
                    statement=(
                        f"{len(assertions)} assertion(s) fired, pinpointing where behavior "
                        "first diverged from the specified invariant."
                    ),
                    evidence_ids=[n.id for n in assertions],
                )
            )
            confidence += 0.15

        design_side = self._waveform_observations(context)
        if design_side:
            kinds = sorted({o.kind for o in design_side})
            observations.append(
                AgentObservation(
                    statement=(
                        "Waveform metadata shows design-side loss of forward progress "
                        f"({', '.join(kinds)})."
                    ),
                    evidence_ids=[n.id for n in context.nodes_of_type(ArtifactType.WAVEFORM_METADATA)],
                )
            )
            confidence += 0.15
        elif context.waveform is None:
            limitations.append(
                "No waveform metadata was supplied, so signal-level corroboration of a "
                "design-side stall was not possible."
            )

        deadlock = context.signal("timeout-deadlock")
        if deadlock is not None:
            observations.append(
                AgentObservation(
                    statement=(
                        "The run stopped making progress with no protocol assertion fired, "
                        "which fits a design-side deadlock or stall."
                    ),
                    evidence_ids=list(deadlock.evidence_ids),
                )
            )
            confidence += 0.10

        cited = dut_scoped or assertions or failing
        hypotheses: list[AgentHypothesis] = []
        if cited:
            where = sorted({n.module for n in cited if n.module})
            hypotheses.append(
                AgentHypothesis(
                    category=HypothesisCategory.RTL_BUG,
                    statement=(
                        "The design deviated from intended behavior"
                        + (f" in {', '.join(where[:3])}" if where else "")
                        + ". The failing evidence fits a logic, FSM, or protocol "
                        "implementation error in the DUT rather than in the checking "
                        "environment."
                    ),
                    confidence=round(min(0.85, confidence), 4),
                    evidence_ids=[n.id for n in cited],
                )
            )

        recommendations: list[AgentRecommendation] = []
        if hypotheses:
            recommendations.append(
                AgentRecommendation(
                    action="Open the waveform at the first failing scope and walk the FSM backward",
                    rationale=(
                        "The design-side position rests on where progress stopped; the "
                        "state before the failure is what discriminates a design bug from "
                        "a stimulus problem."
                    ),
                    priority=1,
                    evidence_ids=[n.id for n in cited[:3]],
                )
            )
        return self.build(
            context,
            observations=observations,
            hypotheses=hypotheses,
            recommendations=recommendations,
            limitations=limitations,
        )

    @staticmethod
    def _dut_scoped(context: AgentContext, failing) -> list:
        """Failing nodes whose scope belongs to the design, not the testbench."""
        dut_names: set[str] = set()
        if context.project is not None:
            dut_names = {m.name.lower() for m in context.project.dut.modules}
            dut_names |= {b.lower() for b in context.project.dut.ip_blocks}
            if context.project.dut.top:
                dut_names.add(context.project.dut.top.lower())

        scoped = []
        for node in failing:
            if not node.module:
                continue
            lowered = node.module.lower()
            if dut_names:
                segments = {s for s in lowered.replace("/", ".").split(".") if s}
                if segments & dut_names:
                    scoped.append(node)
                continue
            if not any(fragment in lowered for fragment in _TESTBENCH_FRAGMENTS):
                scoped.append(node)
        return scoped

    @staticmethod
    def _waveform_observations(context: AgentContext) -> list:
        if context.waveform is None:
            return []
        return [o for o in context.waveform.observations if o.kind in _DESIGN_SIDE_KINDS]
