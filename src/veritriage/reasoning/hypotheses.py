"""Hypothesis generation and ranking.

Generators produce competing, evidence-backed explanations; the ranker then
applies signal weights and evidence confidence to produce final, traceable
confidence values. The two stages are separate on purpose: generation is
about *what could explain this*, ranking is about *how strongly the
deterministic signals support each candidate*.

New generators plug in with the ``@register_generator`` decorator; neither
the engine, the ranker, nor existing generators change.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar, TypeVar

from veritriage.graph.graph import EvidenceGraph
from veritriage.graph.model import ArtifactType, EvidenceNode
from veritriage.models import (
    ConfidenceContribution,
    ConfidenceTrace,
    Hypothesis,
    HypothesisCategory,
    ReasoningSignal,
    WorkingSet,
)

_G = TypeVar("_G", bound="type[HypothesisGenerator]")

_GENERATORS: dict[str, "type[HypothesisGenerator]"] = {}


def register_generator(generator_cls: _G) -> _G:
    """Class decorator adding a hypothesis generator to the registry.

    Raises:
        ValueError: If another generator already registered the same name.
    """
    existing = _GENERATORS.get(generator_cls.name)
    if existing is not None and existing is not generator_cls:
        raise ValueError(
            f"Generator name {generator_cls.name!r} is already registered by {existing!r}"
        )
    _GENERATORS[generator_cls.name] = generator_cls
    return generator_cls


def available_generators() -> dict[str, "type[HypothesisGenerator]"]:
    """All registered generators, keyed by name."""
    return dict(_GENERATORS)


class HypothesisGenerator(ABC):
    """Produces zero or one candidate hypothesis for its category.

    A generator must abstain (return ``None``) when it cannot cite evidence:
    a hypothesis without ``evidence_ids`` is architecturally invalid.
    """

    name: ClassVar[str]
    category: ClassVar[HypothesisCategory]

    #: Prior plausibility before any signal weighs in.
    base_confidence: ClassVar[float] = 0.2

    @abstractmethod
    def generate(self, graph: EvidenceGraph, working_set: WorkingSet) -> Hypothesis | None:
        """Return a candidate hypothesis with evidence, or None to abstain."""
        raise NotImplementedError

    def _working_nodes(self, graph: EvidenceGraph, working_set: WorkingSet) -> list[EvidenceNode]:
        return [graph.nodes[i] for i in working_set.node_ids if i in graph.nodes]

    def _build(self, *, title: str, statement: str, evidence: list[EvidenceNode]) -> Hypothesis | None:
        if not evidence:
            return None
        # Confidence here is provisional: the ranker recomputes it with
        # signal contributions and the evidence factor, filling the trace.
        trace = ConfidenceTrace(
            base=self.base_confidence, evidence_factor=1.0, final=self.base_confidence
        )
        return Hypothesis(
            id=f"hyp-{self.category.value}",
            category=self.category,
            title=title,
            statement=statement,
            confidence=self.base_confidence,
            evidence_ids=[n.id for n in evidence[:8]],
            confidence_trace=trace,
            generated_by=self.name,
        )


@register_generator
class RtlBugGenerator(HypothesisGenerator):
    """The design itself misbehaves."""

    name = "rtl-bug"
    category = HypothesisCategory.RTL_BUG
    base_confidence = 0.25

    def generate(self, graph: EvidenceGraph, working_set: WorkingSet) -> Hypothesis | None:
        nodes = self._working_nodes(graph, working_set)
        failing = [n for n in nodes if n.is_failing]
        if not failing:
            return None
        scopes = sorted({n.module for n in failing if n.module})
        where = f" in {', '.join(scopes[:3])}" if scopes else ""
        when = next((n.sim_time for n in failing if n.sim_time), None)
        at = f" around t={when}" if when else ""
        return self._build(
            title="Likely RTL bug",
            statement=(
                f"The design deviated from intended behavior{where}{at}. The failing "
                "evidence is consistent with a logic, FSM, or protocol implementation "
                "error in the DUT rather than in the checking environment."
            ),
            evidence=failing,
        )


@register_generator
class TestbenchIssueGenerator(HypothesisGenerator):
    """The checking environment (predictor, scoreboard, assertions) is wrong."""

    name = "testbench-issue"
    category = HypothesisCategory.TESTBENCH_ISSUE
    base_confidence = 0.25

    def generate(self, graph: EvidenceGraph, working_set: WorkingSet) -> Hypothesis | None:
        nodes = self._working_nodes(graph, working_set)
        failing = [n for n in nodes if n.is_failing]
        if not failing:
            return None
        tb_scopes = sorted(
            {n.module for n in failing if n.module and ("env" in n.module or "test" in n.module)}
        )
        where = f" ({', '.join(tb_scopes[:3])})" if tb_scopes else ""
        return self._build(
            title="Likely testbench issue",
            statement=(
                f"The checking environment{where} may be flagging correct DUT behavior: "
                "a stale reference model, a mispredicted transaction, or an incorrectly "
                "encoded assertion would produce exactly this failure evidence."
            ),
            evidence=failing,
        )


@register_generator
class InfrastructureIssueGenerator(HypothesisGenerator):
    """The compute environment (host, license, storage) broke the run."""

    name = "infrastructure-issue"
    category = HypothesisCategory.INFRASTRUCTURE_ISSUE
    base_confidence = 0.08

    def generate(self, graph: EvidenceGraph, working_set: WorkingSet) -> Hypothesis | None:
        nodes = self._working_nodes(graph, working_set)
        failing = [n for n in nodes if n.is_failing]
        if not failing:
            return None
        meta = [n for n in nodes if n.artifact_type == ArtifactType.TEST_METADATA]
        return self._build(
            title="Infrastructure issue",
            statement=(
                "The run may have been disturbed by its environment (license drop, disk "
                "or memory exhaustion, host problem) rather than by the design or the "
                "testbench; a clean re-run on a different host would discriminate."
            ),
            evidence=failing[:3] + meta,
        )


@register_generator
class BuildIssueGenerator(HypothesisGenerator):
    """The failure happened before simulation: compile or elaboration."""

    name = "build-issue"
    category = HypothesisCategory.BUILD_ISSUE
    base_confidence = 0.10

    def generate(self, graph: EvidenceGraph, working_set: WorkingSet) -> Hypothesis | None:
        nodes = self._working_nodes(graph, working_set)
        compile_errors = [
            n for n in nodes if n.artifact_type == ArtifactType.COMPILE_LOG and n.is_failing
        ]
        if not compile_errors:
            return None
        first = compile_errors[0]
        where = (
            f" (first at {first.attributes.get('source_file')}:{first.attributes.get('source_line')})"
            if first.attributes.get("source_file")
            else ""
        )
        return self._build(
            title="Build/compile issue",
            statement=(
                f"Compilation or elaboration failed{where}, so the design never simulated; "
                "everything downstream is a consequence of the broken build."
            ),
            evidence=compile_errors,
        )


def default_generators() -> list[HypothesisGenerator]:
    """Instances of every registered generator, in registration order."""
    return [cls() for cls in _GENERATORS.values()]


def generate_hypotheses(
    graph: EvidenceGraph,
    working_set: WorkingSet,
    generators: list[HypothesisGenerator] | None = None,
) -> list[Hypothesis]:
    """Run every generator; collect the candidates that produced evidence."""
    generators = generators if generators is not None else default_generators()
    hypotheses: list[Hypothesis] = []
    for generator in generators:
        hypothesis = generator.generate(graph, working_set)
        if hypothesis is not None:
            hypotheses.append(hypothesis)
    return hypotheses


def rank_hypotheses(
    hypotheses: list[Hypothesis],
    signals: list[ReasoningSignal],
    graph: EvidenceGraph,
) -> list[Hypothesis]:
    """Apply signal weights and evidence confidence; return ranked copies.

    Confidence propagation, fully traceable per hypothesis:

        final = clamp01(base + sum(weight * signal.confidence)) * evidence_factor

    where evidence_factor is the mean extraction confidence of the cited
    nodes (parser confidence propagating upward).
    """
    ranked: list[Hypothesis] = []
    for hypothesis in hypotheses:
        base = hypothesis.confidence_trace.base
        contributions: list[ConfidenceContribution] = []
        for signal in signals:
            weight = signal.weights.get(hypothesis.category)
            if weight is None:
                continue
            delta = round(weight * signal.confidence, 4)
            contributions.append(
                ConfidenceContribution(
                    source=signal.name, delta=delta, reason=signal.description
                )
            )
        cited = [graph.nodes[i] for i in hypothesis.evidence_ids if i in graph.nodes]
        evidence_factor = (
            round(sum(n.confidence for n in cited) / len(cited), 4) if cited else 0.0
        )
        raw = base + sum(c.delta for c in contributions)
        final = round(max(0.0, min(1.0, raw)) * evidence_factor, 4)
        ranked.append(
            hypothesis.model_copy(
                update={
                    "confidence": final,
                    "confidence_trace": ConfidenceTrace(
                        base=base,
                        contributions=contributions,
                        evidence_factor=evidence_factor,
                        final=final,
                    ),
                }
            )
        )
    # Stable sort keeps generator registration order on ties: deterministic.
    ranked.sort(key=lambda h: -h.confidence)
    return ranked
