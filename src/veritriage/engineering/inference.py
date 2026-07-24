"""Engineering inference: how change context reaches the reasoning engine.

Mirrors ``knowledge/inference.py`` and ``waveform/inference.py`` exactly:
``engineering_reasoning_rules()`` returns standard :class:`ReasoningRule`s
composed in ``pipeline.py``; the reasoning engine keeps zero engineering
dependency and just receives more rules.

Change proximity is suggestive, not probative, so every weight here is modest
by design: deterministic log, waveform, and knowledge evidence should keep
dominating the ranking. Signals cite the commit/CI evidence nodes AND the
failures they correlate with; like every rule, they only shift ranking and
never conclude. This is also how the platform separates verification failures
from infrastructure/environment failures: CI-context evidence weights the
existing INFRASTRUCTURE and BUILD hypothesis categories rather than growing a
new classifier.
"""

from __future__ import annotations

from veritriage.graph.graph import EvidenceGraph
from veritriage.graph.model import ArtifactType, EvidenceNode, RelationType
from veritriage.models import HypothesisCategory, ReasoningSignal, WorkingSet
from veritriage.reasoning.signals import ReasoningRule


def _correlated_commits(graph: EvidenceGraph) -> list[tuple[EvidenceNode, list[str]]]:
    """Commit nodes with the failing node IDs they correlate to, in order."""
    out: list[tuple[EvidenceNode, list[str]]] = []
    failing_ids = {n.id for n in graph.failing()}
    for node in graph.nodes_of_type(ArtifactType.ENGINEERING_CHANGE):
        if node.attributes.get("kind") != "commit":
            continue
        correlated = sorted(
            e.target_id
            for e in graph.edges_from(node.id)
            if e.relation == RelationType.CORRELATES_WITH and e.target_id in failing_ids
        )
        if correlated:
            out.append((node, correlated))
    return out


class _CorrelatedChangeRule(ReasoningRule):
    """Shared shape: a correlated commit whose files match a category."""

    #: Subclasses set these.
    category_value: str
    weights: dict[HypothesisCategory, float]
    story: str

    def evaluate(self, graph: EvidenceGraph, working_set: WorkingSet) -> ReasoningSignal | None:
        hits: list[tuple[EvidenceNode, list[str]]] = [
            (node, correlated)
            for node, correlated in _correlated_commits(graph)
            if self.category_value in (node.attributes.get("categories") or [])
        ]
        if not hits:
            return None
        evidence_ids = sorted(
            {node.id for node, _ in hits} | {i for _, ids in hits for i in ids}
        )
        titles = "; ".join(dict.fromkeys(node.description for node, _ in hits))
        return ReasoningSignal(
            name=self.name,
            description=f"Engineering context: {titles}. {self.story}",
            evidence_ids=evidence_ids,
            weights=dict(self.weights),
            confidence=0.8,
        )


class RecentRtlChangeInFailingScopeRule(_CorrelatedChangeRule):
    """A recent RTL change touched the scope that is now failing."""

    name = "engineering:recent-change-in-failing-scope"
    category_value = "rtl"
    weights = {HypothesisCategory.RTL_BUG: 0.15}
    story = (
        "Recently modified RTL sits in the failing scope; fresh design changes "
        "are the most common origin of new failures there."
    )


class RecentTestbenchChangeInFailingScopeRule(_CorrelatedChangeRule):
    """A recent testbench change touched the scope that is now failing."""

    name = "engineering:recent-testbench-change-in-failing-scope"
    category_value = "testbench"
    weights = {HypothesisCategory.TESTBENCH_ISSUE: 0.15}
    story = (
        "Recently modified verification code sits in the failing scope; the "
        "checker may have changed, not the design."
    )


class BuildFlowChangeRule(_CorrelatedChangeRule):
    """A correlated change touched build files while a compile failure exists."""

    name = "engineering:build-flow-change"
    category_value = "build"
    weights = {HypothesisCategory.BUILD_ISSUE: 0.15}
    story = "Build/flow files changed recently, which can break compilation before any RTL is at fault."

    def evaluate(self, graph: EvidenceGraph, working_set: WorkingSet) -> ReasoningSignal | None:
        has_compile_failure = any(
            n.is_failing for n in graph.nodes_of_type(ArtifactType.COMPILE_LOG)
        )
        if not has_compile_failure:
            return None
        return super().evaluate(graph, working_set)


class EnvironmentDriftRule(ReasoningRule):
    """The CI run declares its environment changed since the previous run."""

    name = "engineering:environment-drift"

    def evaluate(self, graph: EvidenceGraph, working_set: WorkingSet) -> ReasoningSignal | None:
        drifted = [
            n
            for n in graph.nodes_of_type(ArtifactType.ENGINEERING_CHANGE)
            if n.attributes.get("kind") == "ci_run" and n.attributes.get("environment_changes")
        ]
        if not drifted:
            return None
        changes = "; ".join(
            c for n in drifted for c in n.attributes.get("environment_changes", [])
        )
        return ReasoningSignal(
            name=self.name,
            description=(
                f"Engineering context: the execution environment changed since the previous "
                f"run ({changes}); environment drift can break runs with no code change at all."
            ),
            evidence_ids=[n.id for n in drifted],
            weights={HypothesisCategory.INFRASTRUCTURE_ISSUE: 0.20},
            confidence=0.85,
        )


def engineering_reasoning_rules() -> list[ReasoningRule]:
    """The engineering-context reasoning rules, in deterministic order."""
    return [
        RecentRtlChangeInFailingScopeRule(),
        RecentTestbenchChangeInFailingScopeRule(),
        BuildFlowChangeRule(),
        EnvironmentDriftRule(),
    ]
