"""Evidence gaps: what the platform does not have, and why it matters.

The one source that proposes steps for information rather than for analysis.
Each gap becomes both an :class:`EvidenceRequest` (what is missing, why, and
which hypotheses it would separate) and a COLLECT candidate (go get it).

Gaps are detected from what the Evidence Graph *lacks*, never from a filesystem
probe: planning opens nothing. A gap is only raised when it would actually
discriminate between live explanations, so a plan never asks for a waveform on
a clean compile failure.
"""

from __future__ import annotations

from veritriage.graph.model import ArtifactType
from veritriage.models import EvidenceRequest, HypothesisCategory, StepKind
from veritriage.planning.context import PlanningContext, StepCandidate
from veritriage.planning.registry import StepSource, register_source

RTL = HypothesisCategory.RTL_BUG
TB = HypothesisCategory.TESTBENCH_ISSUE
BUILD = HypothesisCategory.BUILD_ISSUE
INFRA = HypothesisCategory.INFRASTRUCTURE_ISSUE


def _gap_specs() -> tuple[tuple, ...]:
    """(id, artifact, what, why, discriminates, effort, kind) for each gap.

    Declared as data rather than branching code so a new gap is one row.
    """
    return (
        (
            "waveform",
            ArtifactType.WAVEFORM_METADATA,
            "A waveform dump covering the failing time window",
            "Signal activity around the failure separates a design-side stall from a "
            "checker disagreement: a dead clock, a stalled FSM, or a handshake that "
            "never completed points at the DUT, while clean signalling points at the "
            "checking environment.",
            (RTL, TB),
            2,
        ),
        (
            "engineering",
            ArtifactType.ENGINEERING_CHANGE,
            "Recent commit history for the failing scope",
            "Knowing what changed before the failure is the cheapest filter available: "
            "a new failure in freshly edited logic is a different investigation from a "
            "new failure in untouched logic.",
            (RTL, TB, BUILD),
            1,
        ),
        (
            "coverage",
            ArtifactType.COVERAGE,
            "A coverage summary for the failing module",
            "A coverage hole overlapping the failing scope means this path is barely "
            "exercised, which raises the odds of a latent design bug and of missing "
            "stimulus at the same time.",
            (RTL, TB),
            1,
        ),
        (
            "formal",
            ArtifactType.FORMAL_RESULT,
            "A formal property run over the failing scope",
            "A counterexample is proof of a design bug rather than an inference from "
            "one simulation, and a vacuous pass would show the property itself is "
            "wrong. Either verdict settles what simulation can only suggest.",
            (RTL, TB),
            3,
        ),
    )


@register_source
class EvidenceGapSource(StepSource):
    """Missing information the current investigation would benefit from."""

    source_id = "evidence-gaps"
    rank = 40

    def propose(self, context: PlanningContext) -> list[StepCandidate]:
        candidates: list[StepCandidate] = []
        for request, effort in self._gaps(context):
            candidates.append(
                StepCandidate(
                    kind=StepKind.COLLECT,
                    action=f"Collect {request.what.lower()}",
                    purpose=request.why,
                    derived_from=f"evidence-gap:{request.request_id}",
                    addresses=list(request.would_discriminate),
                    required_evidence=[request.what],
                    expected_observations=[
                        "Once available, VeriTriage can analyze it in the next run and "
                        "the competing explanations narrow"
                    ],
                    module=context.failing_scope(),
                    effort=effort,
                    evidence_ids=list(request.evidence_ids),
                )
            )
        return candidates

    def requests(self, context: PlanningContext) -> list[EvidenceRequest]:
        """The same gaps, as explicit requests for the report."""
        return [request for request, _ in self._gaps(context)]

    @staticmethod
    def _gaps(context: PlanningContext) -> list[tuple[EvidenceRequest, int]]:
        if not context.failing_nodes():
            return []
        competing = set(context.competing())
        cited = [n.id for n in context.failing_nodes()[:3]]
        found: list[tuple[EvidenceRequest, int]] = []

        for gap_id, artifact, what, why, discriminates, effort in _gap_specs():
            if context.has_artifact(artifact):
                continue
            relevant = [c for c in discriminates if c in competing]
            if not relevant:
                continue  # would not separate anything still in play
            found.append(
                (
                    EvidenceRequest(
                        request_id=f"req-{gap_id}",
                        what=what,
                        why=why,
                        would_discriminate=relevant,
                        satisfied_by=[artifact.value],
                        evidence_ids=cited,
                    ),
                    effort,
                )
            )

        # A waveform that was supplied but could not answer a question is its own
        # kind of gap, and the adapter already declared it honestly.
        waveform = context.report.waveform
        if waveform is not None and waveform.unavailable:
            missing = sorted({u.required_capability for u in waveform.unavailable})
            found.append(
                (
                    EvidenceRequest(
                        request_id="req-waveform-capability",
                        what=(
                            "A richer waveform export providing "
                            f"{', '.join(missing)}"
                        ),
                        why=(
                            "The supplied dump did not carry the information these "
                            "analyses need, so they were skipped rather than guessed. "
                            "A fuller export would let them run."
                        ),
                        would_discriminate=sorted(
                            set(context.competing()) & {RTL, TB},
                            key=lambda c: c.value,
                        ),
                        satisfied_by=[ArtifactType.WAVEFORM_METADATA.value],
                        evidence_ids=cited,
                    ),
                    2,
                )
            )
        return found
