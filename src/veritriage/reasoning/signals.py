"""Deterministic reasoning rules: they emit signals, never conclusions.

A reasoning rule observes the working set and, when its pattern holds, emits
a :class:`~veritriage.models.ReasoningSignal`: an evidence-cited observation
with per-category confidence weights. Signals only influence hypothesis
ranking; they cannot create or veto a hypothesis on their own. They run
before (and independently of) any AI.

New rules plug in via ``ReasoningRule`` subclasses added to
``default_reasoning_rules()``; nothing else changes.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import ClassVar

from veritriage.graph.graph import EvidenceGraph
from veritriage.graph.model import ArtifactType, EvidenceNode
from veritriage.models import HypothesisCategory, ReasoningSignal, WorkingSet


class ReasoningRule(ABC):
    """One deterministic observation over the working set."""

    name: ClassVar[str]

    @abstractmethod
    def evaluate(self, graph: EvidenceGraph, working_set: WorkingSet) -> ReasoningSignal | None:
        """Return a signal when the pattern holds, else None."""
        raise NotImplementedError

    @staticmethod
    def _nodes(graph: EvidenceGraph, working_set: WorkingSet) -> list[EvidenceNode]:
        return [graph.nodes[i] for i in working_set.node_ids if i in graph.nodes]


def _match(nodes: list[EvidenceNode], pattern: re.Pattern[str]) -> list[EvidenceNode]:
    return [
        n
        for n in nodes
        if pattern.search(n.description) or (n.raw_line is not None and pattern.search(n.raw_line))
    ]


_TIMEOUT_RE = re.compile(r"time[- ]?out|watchdog|PH_TIMEOUT", re.IGNORECASE)
_MISMATCH_RE = re.compile(
    r"scoreboard|mismatch|miscompare|compare (?:fail|error)|expected\b.*\b(?:got|actual)",
    re.IGNORECASE,
)
_INFRA_RE = re.compile(
    r"license|no space|disk (?:full|quota)|quota exceeded|killed|core dump(?:ed)?|"
    r"segmentation fault|hostname|nfs|connection refused",
    re.IGNORECASE,
)
_PENDING_RE = re.compile(r"outstanding|pending|await|in flight|issued", re.IGNORECASE)


class TimeoutDeadlockRule(ReasoningRule):
    """Timeout + pending activity + no protocol violation points at a hang.

    The canonical example: timeout AND outstanding transactions AND no
    assertion fired -> raise the probability of an RTL deadlock/stall.
    """

    name = "timeout-deadlock"

    def evaluate(self, graph: EvidenceGraph, working_set: WorkingSet) -> ReasoningSignal | None:
        nodes = self._nodes(graph, working_set)
        timeouts = [n for n in _match(nodes, _TIMEOUT_RE) if n.is_failing]
        if not timeouts:
            return None
        assertions = [
            n for n in nodes if n.artifact_type == ArtifactType.ASSERTION and n.is_failing
        ]
        if assertions:
            return None
        pending = _match(nodes, _PENDING_RE)
        weight = 0.30 if pending else 0.22
        detail = " with transactions still in flight" if pending else ""
        return ReasoningSignal(
            name=self.name,
            description=(
                f"The run timed out{detail} and no protocol assertion fired: forward progress "
                "stopped without a detected protocol violation, which fits a design-side "
                "deadlock or stall more than a checking error."
            ),
            evidence_ids=[n.id for n in timeouts + pending[:2]],
            weights={
                HypothesisCategory.RTL_BUG: weight,
                HypothesisCategory.TESTBENCH_ISSUE: 0.05,
            },
        )


class ProtocolViolationRule(ReasoningRule):
    """A fired assertion means an invariant was violated at a specific point."""

    name = "protocol-violation"

    def evaluate(self, graph: EvidenceGraph, working_set: WorkingSet) -> ReasoningSignal | None:
        nodes = self._nodes(graph, working_set)
        assertions = [
            n for n in nodes if n.artifact_type == ArtifactType.ASSERTION and n.is_failing
        ]
        if not assertions:
            return None
        return ReasoningSignal(
            name=self.name,
            description=(
                "A protocol/invariant assertion fired, pinpointing where behavior first "
                "diverged; assertion failures most often expose a design bug, with a smaller "
                "chance the assertion encoding itself is wrong."
            ),
            evidence_ids=[n.id for n in assertions],
            weights={
                HypothesisCategory.RTL_BUG: 0.25,
                HypothesisCategory.TESTBENCH_ISSUE: 0.08,
            },
        )


class ScoreboardMismatchRule(ReasoningRule):
    """Expected-vs-actual mismatches implicate the predictor or the DUT datapath."""

    name = "scoreboard-mismatch"

    def evaluate(self, graph: EvidenceGraph, working_set: WorkingSet) -> ReasoningSignal | None:
        nodes = self._nodes(graph, working_set)
        mismatches = [n for n in _match(nodes, _MISMATCH_RE) if n.is_failing]
        if not mismatches:
            return None
        assertions = [
            n for n in nodes if n.artifact_type == ArtifactType.ASSERTION and n.is_failing
        ]
        if assertions:
            weights = {
                HypothesisCategory.TESTBENCH_ISSUE: 0.18,
                HypothesisCategory.RTL_BUG: 0.15,
            }
            description = (
                "Scoreboard mismatches occurred alongside protocol violations; the mismatch "
                "may be a downstream symptom of the violated protocol."
            )
        else:
            weights = {
                HypothesisCategory.TESTBENCH_ISSUE: 0.30,
                HypothesisCategory.RTL_BUG: 0.10,
            }
            description = (
                "Scoreboard expected-vs-actual mismatches with no protocol assertion fired: "
                "the DUT followed the protocol while the checker disagreed on data, which "
                "points first at the prediction/reference model."
            )
        return ReasoningSignal(
            name=self.name,
            description=description,
            evidence_ids=[n.id for n in mismatches],
            weights=weights,
        )


class CompileDiagnosticsRule(ReasoningRule):
    """Compile/elaboration errors mean the failure predates simulation."""

    name = "compile-diagnostics"

    def evaluate(self, graph: EvidenceGraph, working_set: WorkingSet) -> ReasoningSignal | None:
        nodes = self._nodes(graph, working_set)
        compile_errors = [
            n for n in nodes if n.artifact_type == ArtifactType.COMPILE_LOG and n.is_failing
        ]
        if not compile_errors:
            return None
        return ReasoningSignal(
            name=self.name,
            description=(
                "Compile/elaboration diagnostics are present: the failure occurred before "
                "simulation, so runtime hypotheses are secondary until the build is clean."
            ),
            evidence_ids=[n.id for n in compile_errors],
            weights={
                HypothesisCategory.BUILD_ISSUE: 0.40,
                HypothesisCategory.RTL_BUG: -0.10,
                HypothesisCategory.TESTBENCH_ISSUE: -0.10,
            },
        )


class InfrastructurePatternRule(ReasoningRule):
    """License/disk/host patterns implicate the compute environment, not the design."""

    name = "infrastructure-pattern"

    def evaluate(self, graph: EvidenceGraph, working_set: WorkingSet) -> ReasoningSignal | None:
        nodes = self._nodes(graph, working_set)
        infra = [n for n in _match(nodes, _INFRA_RE) if n.is_failing]
        if not infra:
            return None
        return ReasoningSignal(
            name=self.name,
            description=(
                "Failure messages match infrastructure signatures (license, disk, host, or "
                "process kill), which implicate the environment rather than the design."
            ),
            evidence_ids=[n.id for n in infra],
            weights={
                HypothesisCategory.INFRASTRUCTURE_ISSUE: 0.40,
                HypothesisCategory.RTL_BUG: -0.10,
            },
        )


class CoverageHoleNearFailureRule(ReasoningRule):
    """A coverage hole correlated with the failing scope means under-tested logic."""

    name = "coverage-hole-near-failure"

    def evaluate(self, graph: EvidenceGraph, working_set: WorkingSet) -> ReasoningSignal | None:
        nodes = self._nodes(graph, working_set)
        holes = [
            n
            for n in nodes
            if n.artifact_type == ArtifactType.COVERAGE
            and bool(n.attributes.get("is_hole"))
            and any(e.relation.value == "correlates_with" for e in graph.edges_from(n.id))
        ]
        if not holes:
            return None
        return ReasoningSignal(
            name=self.name,
            description=(
                "Coverage holes overlap the failing scope: the logic around the failure is "
                "under-exercised, so a latent design bug there is plausible and the stimulus "
                "may also be missing scenarios."
            ),
            evidence_ids=[n.id for n in holes],
            weights={
                HypothesisCategory.RTL_BUG: 0.10,
                HypothesisCategory.TESTBENCH_ISSUE: 0.05,
            },
            confidence=0.7,  # scope matching is heuristic; propagate that uncertainty
        )


def default_reasoning_rules() -> list[ReasoningRule]:
    """Built-in reasoning rules, in deterministic evaluation order."""
    return [
        TimeoutDeadlockRule(),
        ProtocolViolationRule(),
        ScoreboardMismatchRule(),
        CompileDiagnosticsRule(),
        InfrastructurePatternRule(),
        CoverageHoleNearFailureRule(),
    ]


def evaluate_signals(
    graph: EvidenceGraph,
    working_set: WorkingSet,
    rules: list[ReasoningRule] | None = None,
) -> list[ReasoningSignal]:
    """Run every reasoning rule; collect the signals that fired."""
    rules = rules if rules is not None else default_reasoning_rules()
    signals: list[ReasoningSignal] = []
    for rule in rules:
        signal = rule.evaluate(graph, working_set)
        if signal is not None:
            signals.append(signal)
    return signals
