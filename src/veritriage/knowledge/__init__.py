"""The Verification Knowledge Engine.

Structured, versioned verification knowledge (Knowledge Packs) normalized
into a queryable Knowledge Graph, matched deterministically against
evidence, and fed to reasoning through standard rule interfaces. Fully
independent of any LLM. Design rationale: docs/KNOWLEDGE_ENGINE.md.
"""

from veritriage.knowledge.graph import KnowledgeGraph
from veritriage.knowledge.inference import (
    KnowledgeEngine,
    KnowledgePatternRule,
    knowledge_reasoning_rules,
)
from veritriage.knowledge.matcher import (
    best_projection,
    match_concepts,
    match_patterns,
    project_states,
)
from veritriage.knowledge.model import (
    Concept,
    DebugPlaybook,
    EvidenceClause,
    FailurePattern,
    KnowledgePack,
    NumericConstraint,
    PlaybookStep,
    ProtocolSignal,
    ProtocolState,
    Reference,
    StateMachine,
)
from veritriage.knowledge.registry import (
    available_packs,
    load_packs,
    register_pack,
    unregister_pack,
)

__all__ = [
    "Concept",
    "DebugPlaybook",
    "EvidenceClause",
    "FailurePattern",
    "KnowledgeEngine",
    "KnowledgeGraph",
    "KnowledgePack",
    "KnowledgePatternRule",
    "NumericConstraint",
    "PlaybookStep",
    "ProtocolSignal",
    "ProtocolState",
    "Reference",
    "StateMachine",
    "available_packs",
    "best_projection",
    "knowledge_reasoning_rules",
    "load_packs",
    "match_concepts",
    "match_patterns",
    "project_states",
    "register_pack",
    "unregister_pack",
]
