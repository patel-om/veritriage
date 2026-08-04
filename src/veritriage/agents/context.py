"""AgentContext: the only input any agent ever receives.

The context carries normalized evidence and the normalized lenses every other
subsystem already produced (knowledge, project, waveform, engineering,
history). It deliberately carries no path, no file handle, no parser, no
adapter, and no provider, so an agent cannot read a raw artifact: it is never
given one. That is law 2 of the Agent Framework, and it holds by construction
rather than by convention.

Nothing here extracts anything. Every helper is a query over data another
layer already produced.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from veritriage.graph.graph import EvidenceGraph
from veritriage.graph.model import ArtifactType, EvidenceNode
from veritriage.knowledge.graph import KnowledgeGraph
from veritriage.knowledge.model import FailurePattern, KnowledgePack
from veritriage.models import (
    ClassificationResult,
    EngineeringContextView,
    HistoricalContext,
    DesignContext,
    KnowledgeContext,
    LearningContext,
    LearningHint,
    MatchedPattern,
    ProjectContext,
    ReasoningResult,
    ReasoningSignal,
    WaveformContext,
)

#: Pack domains that describe a wire protocol rather than a methodology.
PROTOCOL_DOMAINS = frozenset({"protocol", "interconnect", "memory", "serial_io", "coherency"})

#: Knowledge pack ownership value -> the hypothesis category it corroborates.
#: Kept here (not in knowledge/) so the knowledge layer stays unaware of agents.
OWNERSHIP_CATEGORY = {
    "design": "rtl_bug",
    "testbench": "testbench_issue",
    "infrastructure": "infrastructure_issue",
    "build": "build_issue",
}


class AgentContext(BaseModel):
    """Everything an agent may look at, frozen at construction.

    Frozen prevents field reassignment; the agent laws additionally forbid
    mutating anything reachable through it, which
    ``test_agents_never_mutate_reasoning_or_graph`` pins.
    """

    model_config = ConfigDict(frozen=True)

    graph: EvidenceGraph
    classification: ClassificationResult
    reasoning: ReasoningResult
    knowledge: KnowledgeContext | None = None
    knowledge_graph: KnowledgeGraph | None = None
    project: ProjectContext | None = None
    waveform: WaveformContext | None = None
    engineering: EngineeringContextView | None = None
    history: HistoricalContext | None = None
    #: The structural understanding of the system (M15). Plain data: the agents
    #: package never imports the design package, exactly as it never imports
    #: learning. A specialist gains structure; it stays deterministic.
    design: DesignContext | None = None
    #: What the Learning Engine recalled for this run (M13). Plain data: the
    #: agents package never imports the learning package, exactly as reasoning
    #: never imports knowledge. Agents gain memory; they stay deterministic,
    #: because the same context (hints included) always yields the same result.
    learning: LearningContext | None = None

    # --- Evidence queries ---------------------------------------------------

    def working_nodes(self) -> list[EvidenceNode]:
        """The reasoning working set, resolved to nodes, in selection order."""
        return [
            self.graph.nodes[i]
            for i in self.reasoning.working_set.node_ids
            if i in self.graph.nodes
        ]

    def failing_nodes(self) -> list[EvidenceNode]:
        """Failing evidence from the working set (the agent's focus)."""
        return [n for n in self.working_nodes() if n.is_failing]

    def nodes_of_type(self, *artifact_types: ArtifactType) -> list[EvidenceNode]:
        return self.graph.nodes_of_type(*artifact_types)

    def has_node(self, node_id: str) -> bool:
        return node_id in self.graph.nodes

    # --- Deterministic signal queries ---------------------------------------
    #
    # Agents read the signals the reasoning engine already computed rather than
    # re-deriving them from evidence text. That is what keeps law 2 honest:
    # extraction and pattern detection happened upstream, exactly once.

    def signal(self, name: str) -> ReasoningSignal | None:
        """One deterministic signal by name, if it fired this run."""
        return next((s for s in self.reasoning.signals if s.name == name), None)

    def signals_with_prefix(self, prefix: str) -> list[ReasoningSignal]:
        """Every signal whose name starts with ``prefix`` (subsystem grouping)."""
        return [s for s in self.reasoning.signals if s.name.startswith(prefix)]

    # --- Structural queries (M15) -------------------------------------------

    def design_region(self) -> list[str]:
        """Design elements around this failure, empty without a project model."""
        if self.design is None:
            return []
        return [n.name for n in self.design.affected_region]

    # --- Learned memory (M13) -----------------------------------------------
    #
    # Hints inform an investigation; they can never manufacture evidence for
    # one. An agent may cite a hint in an observation, but a hypothesis still
    # has to cite Evidence Graph nodes from the current run.

    def learning_hints(self, kind: str | None = None) -> list[LearningHint]:
        """What history suggests, strongest first; empty without a learning store."""
        if self.learning is None:
            return []
        return self.learning.hints_of_kind(kind) if kind else list(self.learning.hints)

    # --- Knowledge queries --------------------------------------------------

    def matched_patterns(self) -> list[MatchedPattern]:
        return list(self.knowledge.patterns) if self.knowledge else []

    def pattern_source(self, pattern_id: str) -> tuple[KnowledgePack, FailurePattern] | None:
        """Resolve a matched pattern back to its pack and authoritative record.

        The report view carries a display label for ownership; agents need the
        raw ``Ownership`` value, so they look the pattern up in the Knowledge
        Graph rather than reverse-engineering the label.
        """
        if self.knowledge_graph is None:
            return None
        for pack, pattern in self.knowledge_graph.patterns():
            if pattern.id == pattern_id:
                return pack, pattern
        return None

    def patterns_in_domains(self, domains: frozenset[str]) -> list[MatchedPattern]:
        """Matched patterns whose pack belongs to one of ``domains``."""
        selected: list[MatchedPattern] = []
        for matched in self.matched_patterns():
            source = self.pattern_source(matched.pattern_id)
            if source is not None and source[0].domain in domains:
                selected.append(matched)
        return selected

    def pattern_ownership(self, pattern_id: str) -> str | None:
        """The raw ownership value of a matched pattern ('design', ...)."""
        source = self.pattern_source(pattern_id)
        return source[1].ownership if source is not None else None

    @staticmethod
    def pattern_evidence(matched: MatchedPattern) -> list[str]:
        """Every evidence node ID a pattern match cited, deduplicated."""
        return sorted({i for ids in matched.matched_evidence.values() for i in ids})


def build_agent_context(
    graph: EvidenceGraph,
    classification: ClassificationResult,
    reasoning: ReasoningResult,
    knowledge: KnowledgeContext | None = None,
    knowledge_graph: KnowledgeGraph | None = None,
    project: ProjectContext | None = None,
    waveform: WaveformContext | None = None,
    engineering: EngineeringContextView | None = None,
    history: HistoricalContext | None = None,
    learning: LearningContext | None = None,
    design: DesignContext | None = None,
) -> AgentContext:
    """Assemble the frozen context the Coordinator hands to every agent."""
    return AgentContext(
        graph=graph,
        classification=classification,
        reasoning=reasoning,
        knowledge=knowledge,
        knowledge_graph=knowledge_graph,
        project=project,
        waveform=waveform,
        engineering=engineering,
        history=history,
        learning=learning,
        design=design,
    )
