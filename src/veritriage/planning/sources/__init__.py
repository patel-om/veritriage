"""The built-in step sources.

Importing this package registers every built-in source. Each reaches the
Planner through ``@register_source`` alone, so adding a fifth source means
adding a module here (or anywhere else) and nothing more, which
``test_new_step_source_needs_only_registration`` proves.
"""

from veritriage.planning.sources.gaps import EvidenceGapSource
from veritriage.planning.sources.knowledge import KnowledgePlaybookSource
from veritriage.planning.sources.upstream import (
    AgentRecommendationSource,
    ReasoningRecommendationSource,
)

__all__ = [
    "AgentRecommendationSource",
    "EvidenceGapSource",
    "KnowledgePlaybookSource",
    "ReasoningRecommendationSource",
]
