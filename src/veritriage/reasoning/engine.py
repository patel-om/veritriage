"""The reasoning engine: orchestrates the multi-stage pipeline.

    Evidence Graph -> Evidence Selection -> Rule Evaluation (signals)
        -> Hypothesis Generation -> Hypothesis Ranking
        -> Recommendation Generation -> ReasoningResult

Every stage is an injectable, independently testable component; the engine
itself only sequences them. The optional AI review runs strictly after this
engine and cannot modify its output (see :mod:`veritriage.reasoning.ai`).
"""

from __future__ import annotations

from veritriage.graph.graph import EvidenceGraph
from veritriage.models import ReasoningResult
from veritriage.reasoning.hypotheses import (
    HypothesisGenerator,
    generate_hypotheses,
    rank_hypotheses,
)
from veritriage.reasoning.recommend import RecommendationEngine
from veritriage.reasoning.selection import EvidenceSelector
from veritriage.reasoning.signals import ReasoningRule, evaluate_signals


class ReasoningEngine:
    """Runs the deterministic reasoning pipeline over an Evidence Graph."""

    def __init__(
        self,
        selector: EvidenceSelector | None = None,
        rules: list[ReasoningRule] | None = None,
        generators: list[HypothesisGenerator] | None = None,
        recommender: RecommendationEngine | None = None,
    ) -> None:
        self._selector = selector or EvidenceSelector()
        self._rules = rules  # None -> defaults, resolved per run for purity
        self._generators = generators
        self._recommender = recommender or RecommendationEngine()

    def reason(self, graph: EvidenceGraph) -> ReasoningResult:
        """Run selection, signals, generation, ranking, and recommendation.

        Pure function of the graph: the same graph always produces the same
        result, byte for byte.
        """
        working_set = self._selector.select(graph)
        signals = evaluate_signals(graph, working_set, self._rules)
        candidates = generate_hypotheses(graph, working_set, self._generators)
        hypotheses = rank_hypotheses(candidates, signals, graph)
        recommendations = self._recommender.recommend(hypotheses, graph)
        return ReasoningResult(
            working_set=working_set,
            signals=signals,
            hypotheses=hypotheses,
            recommendations=recommendations,
        )
