"""The Agent interface and the builder that enforces its output contract.

An agent is a specialized reasoning component with one responsibility: form an
evidence-backed position about one verification domain. It consumes structured
evidence, queries the Knowledge Graph, contributes observations, produces
hypotheses, assigns confidence, exposes its reasoning, and states what it could
not determine. It never reads a raw artifact, never parses, and never
classifies: those already happened, deterministically, upstream.

The contract is enforced here rather than trusted:

* citations are filtered against the real graph, so a fabricated node ID cannot
  reach a result (law 3);
* a hypothesis with no surviving citation is dropped, and an agent left with no
  hypothesis abstains (law 4);
* hypotheses are sorted by confidence, so ``leading_category`` is meaningful and
  the Coordinator's merge is order-independent.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar, Iterable

from veritriage.agents.context import AgentContext
from veritriage.models import (
    AgentDomain,
    AgentHypothesis,
    AgentObservation,
    AgentRecommendation,
    AgentResult,
)


class Agent(ABC):
    """One specialized reasoning component over the shared evidence."""

    #: Unique registered agent ID, e.g. "protocol".
    agent_id: ClassVar[str]

    #: The verification domain this agent is responsible for.
    domain: ClassVar[AgentDomain]

    def applies_to(self, context: AgentContext) -> bool:
        """Whether this agent has anything in scope to assess.

        Returning False is a first-class outcome: the Coordinator records the
        agent as not applicable rather than silently skipping it, so a report
        always says which specialists were consulted and which had no data.
        """
        return True

    @abstractmethod
    def assess(self, context: AgentContext) -> AgentResult:
        """Form this agent's position; must be a pure function of the context."""
        raise NotImplementedError

    # --- Result construction ------------------------------------------------

    def build(
        self,
        context: AgentContext,
        observations: Iterable[AgentObservation] = (),
        hypotheses: Iterable[AgentHypothesis] = (),
        recommendations: Iterable[AgentRecommendation] = (),
        limitations: Iterable[str] = (),
    ) -> AgentResult:
        """Assemble a contract-compliant result, filtering unresolvable citations."""
        kept_observations = [
            observation.model_copy(
                update={"evidence_ids": self._resolve(context, observation.evidence_ids)}
            )
            for observation in observations
        ]
        kept_hypotheses: list[AgentHypothesis] = []
        for hypothesis in hypotheses:
            resolved = self._resolve(context, hypothesis.evidence_ids)
            if not resolved:
                continue  # a position with nothing to cite is not a position
            kept_hypotheses.append(hypothesis.model_copy(update={"evidence_ids": resolved}))
        kept_hypotheses.sort(key=lambda h: (-h.confidence, h.category.value))

        kept_recommendations = [
            recommendation.model_copy(
                update={"evidence_ids": self._resolve(context, recommendation.evidence_ids)}
            )
            for recommendation in recommendations
        ]
        kept_recommendations.sort(key=lambda r: (r.priority, r.action))

        evidence_ids = sorted(
            {i for o in kept_observations for i in o.evidence_ids}
            | {i for h in kept_hypotheses for i in h.evidence_ids}
            | {i for r in kept_recommendations for i in r.evidence_ids}
        )
        knowledge_ids = sorted(
            {i for o in kept_observations for i in o.knowledge_ids}
            | {i for h in kept_hypotheses for i in h.knowledge_ids}
        )
        declared = list(dict.fromkeys(limitations))
        if not kept_hypotheses:
            declared.append(
                "No position formed: the available evidence did not support a "
                "hypothesis in this domain."
            )
        return AgentResult(
            agent_id=self.agent_id,
            domain=self.domain,
            applicable=True,
            abstained=not kept_hypotheses,
            confidence=kept_hypotheses[0].confidence if kept_hypotheses else 0.0,
            observations=kept_observations,
            hypotheses=kept_hypotheses,
            recommendations=kept_recommendations,
            evidence_ids=evidence_ids,
            knowledge_ids=knowledge_ids,
            limitations=declared,
        )

    def not_applicable(self, reason: str) -> AgentResult:
        """The result for an agent with nothing in scope."""
        return AgentResult(
            agent_id=self.agent_id,
            domain=self.domain,
            applicable=False,
            abstained=False,
            confidence=0.0,
            limitations=[reason],
        )

    @staticmethod
    def _resolve(context: AgentContext, node_ids: Iterable[str]) -> list[str]:
        """Keep only citations that resolve to a node actually in the graph."""
        return sorted({i for i in node_ids if context.has_node(i)})
