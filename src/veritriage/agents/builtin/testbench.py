"""Testbench Agent: is the checking environment wrong rather than the DUT?

Reads the deterministic scoreboard-mismatch signal, methodology pack matches,
and the project's log-origin classification. It never re-derives a mismatch
from message text: extraction happened once, upstream.
"""

from __future__ import annotations

from veritriage.agents.base import Agent
from veritriage.agents.context import OWNERSHIP_CATEGORY, AgentContext
from veritriage.agents.registry import register_agent
from veritriage.models import (
    AgentDomain,
    AgentHypothesis,
    AgentObservation,
    AgentRecommendation,
    AgentResult,
    HypothesisCategory,
)

#: Knowledge pack domains that describe verification methodology, not a wire
#: protocol: UVM, RAL, phasing, TLM, coverage, DFT, and friends.
_METHODOLOGY_DOMAINS = frozenset({"methodology", "coverage", "verification"})


@register_agent
class TestbenchAgent(Agent):
    """The verification environment specialist."""

    agent_id = "testbench"
    domain = AgentDomain.TESTBENCH

    def applies_to(self, context: AgentContext) -> bool:
        if context.signal("scoreboard-mismatch") is not None:
            return True
        if context.patterns_in_domains(_METHODOLOGY_DOMAINS):
            return True
        origins = context.project.log_origins if context.project else {}
        return bool(origins.get("testbench") or origins.get("vip"))

    def assess(self, context: AgentContext) -> AgentResult:
        observations: list[AgentObservation] = []
        hypotheses: list[AgentHypothesis] = []
        recommendations: list[AgentRecommendation] = []
        limitations: list[str] = []
        confidence = 0.25
        cited: set[str] = set()

        mismatch = context.signal("scoreboard-mismatch")
        if mismatch is not None:
            observations.append(
                AgentObservation(
                    statement=(
                        "Expected-versus-actual mismatches were reported by the checking "
                        "environment, which implicates the reference model or predictor "
                        "as readily as the DUT datapath."
                    ),
                    evidence_ids=list(mismatch.evidence_ids),
                )
            )
            cited.update(mismatch.evidence_ids)
            confidence += 0.25

        methodology = context.patterns_in_domains(_METHODOLOGY_DOMAINS)
        for matched in methodology:
            evidence = context.pattern_evidence(matched)
            observations.append(
                AgentObservation(
                    statement=(
                        f"Methodology pattern '{matched.name}' ({matched.pack}) matched at "
                        f"score {matched.score:.2f}: {matched.summary}"
                    ),
                    evidence_ids=evidence,
                    knowledge_ids=[matched.pattern_id],
                )
            )
            cited.update(evidence)
            if matched.playbook is not None:
                first = matched.playbook.steps[0]
                recommendations.append(
                    AgentRecommendation(
                        action=first.action,
                        rationale=(
                            f"Opening step of the '{matched.playbook.name}' playbook for "
                            f"the matched {matched.pack} pattern."
                        ),
                        priority=1,
                        evidence_ids=evidence[:3],
                    )
                )
        if methodology:
            confidence += 0.15

        origin = context.signal("project:log-origin")
        if origin is not None:
            observations.append(
                AgentObservation(
                    statement=(
                        "Per the project's log profile the failing messages originate "
                        "outside the DUT, in the verification environment or its VIP."
                    ),
                    evidence_ids=list(origin.evidence_ids),
                )
            )
            cited.update(origin.evidence_ids)
            confidence += 0.20

        # Ownership declared by the matched methodology patterns can point at a
        # non-testbench class; respect the pack rather than assuming.
        declared = {
            OWNERSHIP_CATEGORY.get(context.pattern_ownership(m.pattern_id) or "")
            for m in methodology
        }
        if cited:
            hypotheses.append(
                AgentHypothesis(
                    category=HypothesisCategory.TESTBENCH_ISSUE,
                    statement=(
                        "The checking environment may be flagging correct DUT behavior: a "
                        "stale reference model, a mispredicted transaction, a misconfigured "
                        "register model, or an incorrectly encoded assertion would produce "
                        "exactly this evidence."
                    ),
                    confidence=round(min(0.85, confidence), 4),
                    evidence_ids=sorted(cited),
                    knowledge_ids=[m.pattern_id for m in methodology],
                )
            )
        if "build_issue" in declared:
            limitations.append(
                "At least one matched methodology pattern is owned by the build flow, so "
                "a clean build should be confirmed before pursuing the testbench."
            )
        if context.project is None:
            limitations.append(
                "No Project Model was supplied, so message origin (DUT versus VIP versus "
                "testbench) could not be resolved from the project's log profile."
            )
        if mismatch is None:
            limitations.append(
                "No scoreboard mismatch was reported, so the position rests on methodology "
                "patterns rather than on a direct comparison failure."
            )
        return self.build(
            context,
            observations=observations,
            hypotheses=hypotheses,
            recommendations=recommendations,
            limitations=limitations,
        )
