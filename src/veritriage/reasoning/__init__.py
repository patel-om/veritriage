"""The Verification Reasoning Engine.

Multi-stage, evidence-first reasoning over the Evidence Graph:

    selection -> signals -> hypothesis generation -> ranking
        -> recommendations -> (optional, strictly downstream) AI review

Design rationale and extension guide: docs/REASONING_ENGINE.md.
"""

from veritriage.reasoning.ai import AIReasoner, AIReasoningError, build_ai_payload
from veritriage.reasoning.engine import ReasoningEngine
from veritriage.reasoning.hypotheses import (
    HypothesisGenerator,
    available_generators,
    generate_hypotheses,
    rank_hypotheses,
    register_generator,
)
from veritriage.reasoning.recommend import RecommendationEngine
from veritriage.reasoning.selection import EvidenceSelector
from veritriage.reasoning.signals import (
    ReasoningRule,
    default_reasoning_rules,
    evaluate_signals,
)

__all__ = [
    "AIReasoner",
    "AIReasoningError",
    "EvidenceSelector",
    "HypothesisGenerator",
    "ReasoningEngine",
    "ReasoningRule",
    "RecommendationEngine",
    "available_generators",
    "build_ai_payload",
    "default_reasoning_rules",
    "evaluate_signals",
    "generate_hypotheses",
    "rank_hypotheses",
    "register_generator",
]
