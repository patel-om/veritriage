"""Recommendation generation: hypotheses become concrete debugging steps.

Deterministic: the same ranked hypotheses always yield the same
recommendations, each categorized by priority, expected effort, propagated
confidence, and affected module, and each citing the evidence it came from.
"""

from __future__ import annotations

from veritriage.graph.graph import EvidenceGraph
from veritriage.models import (
    EngineeringRecommendation,
    Hypothesis,
    HypothesisCategory,
)

#: How much of a hypothesis's confidence its recommendations inherit.
_PROPAGATION = 0.9

#: Only hypotheses at or above this confidence drive recommendations.
_MIN_CONFIDENCE = 0.10


class RecommendationEngine:
    """Turns ranked hypotheses into an ordered debugging plan."""

    def recommend(
        self, hypotheses: list[Hypothesis], graph: EvidenceGraph
    ) -> list[EngineeringRecommendation]:
        """Generate prioritized recommendations from the ranked hypotheses."""
        recommendations: list[EngineeringRecommendation] = []
        priority = 1
        for hypothesis in hypotheses:
            if hypothesis.confidence < _MIN_CONFIDENCE:
                continue
            for action, rationale, effort in self._steps_for(hypothesis, graph):
                recommendations.append(
                    EngineeringRecommendation(
                        action=action,
                        rationale=rationale,
                        priority=priority,
                        effort=effort,
                        confidence=round(hypothesis.confidence * _PROPAGATION, 4),
                        module=self._module_for(hypothesis, graph),
                        evidence_ids=hypothesis.evidence_ids[:3],
                    )
                )
                priority += 1
        return recommendations

    @staticmethod
    def _module_for(hypothesis: Hypothesis, graph: EvidenceGraph) -> str | None:
        for node_id in hypothesis.evidence_ids:
            node = graph.nodes.get(node_id)
            if node is not None and node.module:
                return node.module
        return None

    @staticmethod
    def _steps_for(
        hypothesis: Hypothesis, graph: EvidenceGraph
    ) -> list[tuple[str, str, str]]:
        """(action, rationale, effort) steps for one hypothesis category."""
        first = next(
            (graph.nodes[i] for i in hypothesis.evidence_ids if i in graph.nodes), None
        )
        when = f" around t={first.sim_time}" if first is not None and first.sim_time else ""
        scope = first.module if first is not None and first.module else "the failing scope"
        source = (
            f"{first.attributes.get('source_file')}:{first.attributes.get('source_line')}"
            if first is not None and first.attributes.get("source_file")
            else None
        )

        if hypothesis.category == HypothesisCategory.RTL_BUG:
            steps = [
                (
                    f"Inspect the waveform{when} at {scope}, working backward from the first failure.",
                    "The first failing evidence marks where behavior diverged; upstream of it is the cause.",
                    "medium",
                ),
                (
                    "Review recent RTL changes touching the failing scope.",
                    "New failures usually track recent edits; a diff review is the cheapest first filter.",
                    "low",
                ),
            ]
            if source:
                steps.append(
                    (
                        f"Check the logic at {source} against the specification.",
                        "The failing message points directly at this source location.",
                        "medium",
                    )
                )
            return steps
        if hypothesis.category == HypothesisCategory.TESTBENCH_ISSUE:
            return [
                (
                    "Review the scoreboard/reference-model prediction for the first mismatching transaction.",
                    "If the DUT follows the protocol, the checker's expectation is the prime suspect.",
                    "medium",
                ),
                (
                    "Compare the first mismatching transaction against the specification by hand.",
                    "A manual spec check settles whether the DUT or the predictor is wrong.",
                    "low",
                ),
            ]
        if hypothesis.category == HypothesisCategory.BUILD_ISSUE:
            return [
                (
                    f"Fix the first compile error{f' at {source}' if source else ''} and rebuild.",
                    "Later diagnostics are usually cascades of the first error.",
                    "low",
                ),
            ]
        # INFRASTRUCTURE_ISSUE
        return [
            (
                "Re-run the same test and seed on a different host.",
                "A clean re-run separates environment problems from real failures.",
                "low",
            ),
            (
                "Check license availability, disk space, and memory on the original host.",
                "The failure signatures match environment exhaustion patterns.",
                "low",
            ),
        ]
