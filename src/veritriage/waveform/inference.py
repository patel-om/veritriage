"""Waveform inference: how waveform observations reach reasoning and reports.

Two additive integration surfaces, mirroring the knowledge engine exactly:

1. **Reasoning signals.** ``waveform_reasoning_rules()`` wraps each ranking
   relevant observation kind in a standard :class:`ReasoningRule`, so a waveform
   observation contributes evidence-cited ranking weight through the same
   interface as every built-in rule. The reasoning engine has no idea waveforms
   exist; it just receives more rules. Waveform findings are evidence, never
   hidden prompt text.

2. **Report context.** ``build_waveform_context()`` assembles the report-facing
   :class:`WaveformContext` from the parse results (observations, honest
   unavailable-analysis notes, and per-adapter capabilities).

Nothing here imports an LLM, and the reasoning package never imports this
module, so the "reasoning has no waveform dependency" law holds.
"""

from __future__ import annotations

from veritriage.graph.graph import EvidenceGraph
from veritriage.graph.model import ArtifactType
from veritriage.models import (
    HypothesisCategory,
    ReasoningSignal,
    WorkingSet,
)
from veritriage.models.waveform import (
    WaveformCapabilityView,
    WaveformContext,
    WaveformObservationView,
    WaveformUnavailableView,
)
from veritriage.parsers.base import ParseResult
from veritriage.reasoning.signals import ReasoningRule
from veritriage.waveform.model import ObservationKind
from veritriage.waveform.parser import stored_metadata, stored_observations

#: Per-observation-kind ranking weights. Kinds absent here are still evidence in
#: the report but contribute no ranking push (e.g. a completed handshake, which
#: is positive progress and should not blame any category).
_KIND_WEIGHTS: dict[ObservationKind, dict[HypothesisCategory, float]] = {
    ObservationKind.SIGNAL_NEVER_TOGGLED: {
        HypothesisCategory.RTL_BUG: 0.12,
        HypothesisCategory.TESTBENCH_ISSUE: 0.12,
    },
    ObservationKind.CLOCK_STOPPED: {
        HypothesisCategory.RTL_BUG: 0.20,
        HypothesisCategory.TESTBENCH_ISSUE: 0.10,
    },
    ObservationKind.HANDSHAKE_INCOMPLETE: {
        HypothesisCategory.RTL_BUG: 0.25,
    },
    ObservationKind.FSM_STALLED: {
        HypothesisCategory.RTL_BUG: 0.22,
    },
    ObservationKind.TRANSACTION_NOT_RETIRED: {
        HypothesisCategory.RTL_BUG: 0.25,
    },
    ObservationKind.UNEXPECTED_RESET: {
        HypothesisCategory.TESTBENCH_ISSUE: 0.15,
        HypothesisCategory.INFRASTRUCTURE_ISSUE: 0.05,
    },
    ObservationKind.REPEATED_RETRIES: {
        HypothesisCategory.RTL_BUG: 0.12,
        HypothesisCategory.TESTBENCH_ISSUE: 0.08,
    },
    ObservationKind.PROTOCOL_SEQUENCE_INCOMPLETE: {
        HypothesisCategory.TESTBENCH_ISSUE: 0.15,
        HypothesisCategory.RTL_BUG: 0.05,
    },
}


class WaveformObservationRule(ReasoningRule):
    """Adapter: waveform observations of one kind exposed as a reasoning rule.

    When observation evidence of this kind is in the working set, the rule emits
    one signal whose weights are the kind's ranking modifiers, whose evidence IDs
    are the observation nodes, and whose confidence is the strongest observation
    of that kind. Like every rule, it only shifts ranking; it never concludes.
    """

    def __init__(self, kind: ObservationKind) -> None:
        self._kind = kind
        self.name = f"waveform:{kind.value}"

    def evaluate(self, graph: EvidenceGraph, working_set: WorkingSet) -> ReasoningSignal | None:
        weights = _KIND_WEIGHTS.get(self._kind)
        if not weights:
            return None
        nodes = [
            graph.nodes[i]
            for i in working_set.node_ids
            if i in graph.nodes
            and graph.nodes[i].artifact_type == ArtifactType.WAVEFORM_METADATA
            and graph.nodes[i].attributes.get("waveform_kind") == self._kind.value
        ]
        if not nodes:
            return None
        confidence = max(n.confidence for n in nodes)
        descriptions = "; ".join(dict.fromkeys(n.description for n in nodes))
        return ReasoningSignal(
            name=self.name,
            description=f"Waveform intelligence: {descriptions}",
            evidence_ids=[n.id for n in nodes],
            weights=dict(weights),
            confidence=confidence,
        )


def waveform_reasoning_rules() -> list[ReasoningRule]:
    """One reasoning rule per ranking-relevant observation kind, sorted."""
    return [
        WaveformObservationRule(kind)
        for kind in sorted(_KIND_WEIGHTS, key=lambda k: k.value)
    ]


def build_waveform_context(results: list[ParseResult]) -> WaveformContext | None:
    """Assemble the report-facing waveform context from waveform parse results.

    Returns None when no waveform artifact was analyzed, so the report's
    ``waveform`` field stays absent on non-waveform runs.
    """
    observation_views: list[WaveformObservationView] = []
    unavailable_views: list[WaveformUnavailableView] = []
    capability_views: list[WaveformCapabilityView] = []
    dump_windows: dict[str, tuple[int | None, int | None]] = {}
    saw_waveform = False

    for result in results:
        metadata = stored_metadata(result)
        if metadata is None:
            continue
        saw_waveform = True
        capability_views.append(
            WaveformCapabilityView(
                adapter=metadata.adapter,
                format=metadata.format,
                source=metadata.source_path,
                simulator=metadata.simulator,
                signal_count=len(metadata.signals),
                dump_start=metadata.dump_start,
                dump_end=metadata.dump_end,
                capabilities=sorted(c.value for c in metadata.capabilities),
            )
        )
        obs_result = stored_observations(result)
        for obs in obs_result.observations:
            observation_views.append(
                WaveformObservationView(
                    observation_id=obs.observation_id,
                    kind=obs.kind.value,
                    category=obs.category.value,
                    description=obs.description,
                    severity=obs.severity.value,
                    confidence=obs.confidence,
                    detector=obs.detector,
                    source_adapter=obs.source_adapter,
                    scope=obs.scope,
                    signals=obs.input_signals,
                    sim_time_start=obs.sim_time_start,
                    sim_time_end=obs.sim_time_end,
                )
            )
        for note in obs_result.unavailable:
            unavailable_views.append(
                WaveformUnavailableView(
                    detector=note.detector,
                    required_capability=note.required_capability.value,
                    adapter=note.adapter,
                    reason=note.reason,
                )
            )

    if not saw_waveform:
        return None
    return WaveformContext(
        adapters=capability_views,
        observations=observation_views,
        unavailable=unavailable_views,
    )
