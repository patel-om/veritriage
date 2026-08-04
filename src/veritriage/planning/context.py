"""PlanningContext: the finished analysis, and the candidate a source returns.

The context is everything the Planner and its sources may read: one completed
`AnalysisReport` plus the Evidence Graph it was derived from. No path, no file
handle, no store. Planning is a pure function of a finished analysis.

`StepCandidate` is the intermediate a source returns. It carries what the step
is and where it came from, but deliberately no priority: valuation and ordering
are the Planner's job, so no source can promote its own suggestions.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from veritriage.graph.graph import EvidenceGraph
from veritriage.graph.model import ArtifactType, EvidenceNode
from veritriage.models import (
    AnalysisReport,
    HypothesisCategory,
    Hypothesis,
    StepKind,
)


class PlanningContext(BaseModel):
    """Everything a step source may look at, frozen at construction."""

    model_config = ConfigDict(frozen=True)

    report: AnalysisReport
    graph: EvidenceGraph

    # --- Conclusions the plan is built to serve -----------------------------

    @property
    def hypotheses(self) -> list[Hypothesis]:
        if self.report.reasoning is None:
            return []
        return list(self.report.reasoning.hypotheses)

    @property
    def leading(self) -> Hypothesis | None:
        return self.hypotheses[0] if self.hypotheses else None

    def confidence_of(self, category: HypothesisCategory) -> float:
        for hypothesis in self.hypotheses:
            if hypothesis.category == category:
                return hypothesis.confidence
        return 0.0

    def competing(
        self, margin: float = 0.15, ratio: float = 0.5
    ) -> list[HypothesisCategory]:
        """Categories still live enough that evidence must separate them.

        A hypothesis competes when it is close to the leader in absolute terms
        *or* holds a meaningful fraction of the leader's confidence. Both tests
        are needed: the absolute margin catches a near tie at high confidence,
        and the ratio catches a genuine second explanation trailing a strong
        leader (48% against 71% is a real alternative, not a foregone one).

        This is what makes a step *discriminating*: a plan is most valuable
        when it tells two live explanations apart, not when it confirms one
        that was never in doubt.
        """
        if not self.hypotheses:
            return []
        top = self.hypotheses[0].confidence
        if top <= 0:
            return []
        return [
            h.category
            for h in self.hypotheses
            if h.confidence > 0 and (top - h.confidence <= margin or h.confidence >= top * ratio)
        ]

    # --- Evidence queries ---------------------------------------------------

    def failing_nodes(self) -> list[EvidenceNode]:
        return self.graph.failing()

    def nodes_of_type(self, *artifact_types: ArtifactType) -> list[EvidenceNode]:
        return self.graph.nodes_of_type(*artifact_types)

    def has_artifact(self, artifact_type: ArtifactType) -> bool:
        return bool(self.graph.nodes_of_type(artifact_type))

    def has_node(self, node_id: str) -> bool:
        return node_id in self.graph.nodes

    def resolve(self, node_ids: list[str]) -> list[str]:
        """Keep only citations that resolve to a node actually in the graph."""
        return sorted({i for i in node_ids if self.has_node(i)})

    def failing_scope(self) -> str | None:
        for node in self.failing_nodes():
            if node.module:
                return node.module
        return None

    def first_sim_time(self) -> str | None:
        for node in self.failing_nodes():
            if node.sim_time:
                return node.sim_time
        return None

    # --- Lenses -------------------------------------------------------------

    @property
    def protocols(self) -> list[str]:
        """Protocol pack IDs in play, from the project model or matched patterns."""
        found: set[str] = set()
        if self.report.project is not None:
            found.update(p.protocol_id for p in self.report.project.identified_protocols)
        if self.report.knowledge is not None:
            found.update(p.pack for p in self.report.knowledge.patterns)
        return sorted(found)

    def learning_strength(self, action: str) -> float:
        """How well an action has historically worked, in [-1, 1]; 0 without history.

        Positive means engineers rated it useful, negative means it wasted time.
        Learning contributes priority, never steps: this only ever reweights a
        candidate some other source already proposed.
        """
        learning = self.report.learning
        if learning is None:
            return 0.0
        for outcome in learning.common_recommendations:
            if outcome.action == action and outcome.usefulness is not None:
                return round(outcome.usefulness * 2 - 1, 4)
        return 0.0


class StepCandidate(BaseModel):
    """What a step source returns: content plus provenance, and no priority.

    Sources cannot rank themselves. Valuation and ordering belong to the
    Planner, so a source has no way to promote its own suggestions.
    """

    kind: StepKind
    action: str
    purpose: str
    derived_from: str = Field(
        description="The artifact this restates, e.g. 'knowledge:playbook:pb-x#1'."
    )
    addresses: list[HypothesisCategory] = Field(default_factory=list)
    required_evidence: list[str] = Field(default_factory=list)
    expected_observations: list[str] = Field(default_factory=list)
    signals: list[str] = Field(default_factory=list)
    module: str | None = None
    effort: int = Field(default=2, ge=1, le=3, description="1 low, 2 medium, 3 high.")
    evidence_ids: list[str] = Field(default_factory=list)
    #: Optional extra value the source can justify, e.g. a curated playbook's
    #: opening step. Bounded by the valuation layer, never unbounded.
    bonus: float = Field(default=0.0, ge=0.0, le=1.0)
    bonus_reason: str | None = None
