"""Explanatory bundle comparison: what changed, not merely that it differs.

Extends the M8 signature-and-classification comparison across every layer of
an investigation, each as added / removed items, and produces a human summary
sentence so a reviewer reads "same signature; 2 new waveform observations;
diagnosis changed testbench -> RTL" instead of a boolean. Deterministic: the
same pair yields the same explanation.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from veritriage.collab.model import InvestigationBundle
from veritriage.workspace.session import InvestigationSession


class FacetDelta(BaseModel):
    """The change in one facet between two investigations."""

    facet: str
    added: list[str] = Field(default_factory=list)
    removed: list[str] = Field(default_factory=list)
    changed: list[str] = Field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.added or self.removed or self.changed)


class BundleComparison(BaseModel):
    """A structured, explanatory diff of two bundles."""

    bundle_a: str
    bundle_b: str
    summary: str
    deltas: list[FacetDelta] = Field(default_factory=list)


def _failing(session: InvestigationSession) -> set[str]:
    return {n.description for n in session.graph.failing()}


def _patterns(session: InvestigationSession) -> set[str]:
    k = session.report.knowledge
    return {p.pattern_id for p in k.patterns} if k else set()


def _waveform_kinds(session: InvestigationSession) -> set[str]:
    w = session.report.waveform
    return {o.kind for o in w.observations} if w else set()


def _changed_modules(session: InvestigationSession) -> set[str]:
    e = session.report.engineering
    return {m for c in e.commits for f in c.files for m in f.modules} if e else set()


def _recommendations(session: InvestigationSession) -> set[str]:
    r = session.report.reasoning
    return {step.action for step in r.recommendations} if r else set()


def _trace_steps(session: InvestigationSession) -> set[str]:
    t = session.trace
    return {f"{s.step_id}={s.status.value}" for s in t.steps} if t else set()


def _delta(facet: str, a: set[str], b: set[str]) -> FacetDelta:
    return FacetDelta(facet=facet, added=sorted(b - a), removed=sorted(a - b))


def compare_bundles(a: InvestigationBundle, b: InvestigationBundle) -> BundleComparison:
    """Explain what changed between two investigation bundles."""
    sa, sb = a.session, b.session
    deltas: list[FacetDelta] = []

    class_a = sa.report.classification.category.value
    class_b = sb.report.classification.category.value
    if class_a != class_b or sa.report.classification.confidence != sb.report.classification.confidence:
        deltas.append(
            FacetDelta(
                facet="classification",
                changed=[
                    f"{class_a} ({sa.report.classification.confidence}%) -> "
                    f"{class_b} ({sb.report.classification.confidence}%)"
                ],
            )
        )

    for facet, extract in (
        ("evidence", _failing),
        ("knowledge", _patterns),
        ("waveform", _waveform_kinds),
        ("engineering", _changed_modules),
        ("recommendations", _recommendations),
        ("execution-trace", _trace_steps),
    ):
        delta = _delta(facet, extract(sa), extract(sb))
        if not delta.is_empty:
            deltas.append(delta)

    meta = FacetDelta(
        facet="metadata",
        added=sorted(
            {f"review:{r.verdict.value}" for r in b.reviews}
            - {f"review:{r.verdict.value}" for r in a.reviews}
        ),
        removed=sorted(
            {f"review:{r.verdict.value}" for r in a.reviews}
            - {f"review:{r.verdict.value}" for r in b.reviews}
        ),
    )
    if a.metadata.veritriage_version != b.metadata.veritriage_version:
        meta.changed.append(
            f"version {a.metadata.veritriage_version} -> {b.metadata.veritriage_version}"
        )
    if len(a.annotations) != len(b.annotations):
        meta.changed.append(f"annotations {len(a.annotations)} -> {len(b.annotations)}")
    if not meta.is_empty:
        deltas.append(meta)

    return BundleComparison(
        bundle_a=a.bundle_id,
        bundle_b=b.bundle_id,
        summary=_summarize(a, b, deltas),
        deltas=deltas,
    )


def _summarize(a: InvestigationBundle, b: InvestigationBundle, deltas: list[FacetDelta]) -> str:
    """One human sentence describing the comparison."""
    if not deltas:
        return "identical investigations: same classification, evidence, and conclusions"
    same_sig = a.session.session_id == b.session.session_id
    parts: list[str] = ["same investigation" if same_sig else "different investigations"]
    by_facet = {d.facet: d for d in deltas}
    if "classification" in by_facet:
        parts.append(f"diagnosis {by_facet['classification'].changed[0]}")
    for facet, noun in (
        ("waveform", "waveform observation"),
        ("knowledge", "knowledge pattern"),
        ("evidence", "failing-evidence item"),
        ("recommendations", "recommendation"),
    ):
        d = by_facet.get(facet)
        if d and (d.added or d.removed):
            bits = []
            if d.added:
                bits.append(f"{len(d.added)} new")
            if d.removed:
                bits.append(f"{len(d.removed)} fewer")
            parts.append(f"{' and '.join(bits)} {noun}{'s' if (len(d.added) + len(d.removed)) != 1 else ''}")
    return "; ".join(parts)
