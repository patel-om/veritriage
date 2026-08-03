"""Pattern learners: what recurs, and what a combination of evidence means.

Two families that answer the questions the regression database stores the data
for but never asks: which failure modes keep coming back (and what actually
fixed them), and which evidence combinations historically imply which outcome.
"""

from __future__ import annotations

import hashlib

from veritriage.learning.corpus import Corpus
from veritriage.learning.registry import Learner, register_learner
from veritriage.models import EvidencePattern, InvestigationPattern, LearningArtifact

#: A signature must appear at least this often before it counts as recurring.
RECURRENCE_THRESHOLD = 2

#: An evidence combination must appear at least this often to be a pattern.
COOCCURRENCE_THRESHOLD = 2


@register_learner
class InvestigationPatternLearner(Learner):
    """Recurring failure modes, their confirmed causes, and what worked."""

    learner_id = "investigation-patterns"
    artifact_kind = "investigation_pattern"

    def observe(self, corpus: Corpus) -> list[LearningArtifact]:
        by_signature: dict[str, list] = {}
        for record in corpus.failures():
            by_signature.setdefault(record.signature.digest, []).append(record)

        artifacts: list[LearningArtifact] = []
        for digest in sorted(by_signature):
            group = by_signature[digest]
            if len(group) < RECURRENCE_THRESHOLD:
                continue
            causes = sorted(
                {
                    cause
                    for r in group
                    if (cause := corpus.confirmed_cause(r.regression_id)) is not None
                }
            )
            actions = sorted(
                {
                    action
                    for r in group
                    for f in corpus.feedback_for(r.regression_id)
                    for action in f.useful_recommendations
                }
            )
            first = group[0]
            classification = first.classification
            modules = sorted({m for r in group for m in r.signature.modules})
            summary = (
                f"This failure signature has recurred {len(group)} times, always "
                f"classified as {classification.replace('_', ' ')}"
                + (f", affecting {', '.join(modules[:3])}" if modules else "")
                + "."
            )
            if causes:
                summary += f" Previously diagnosed as: {causes[0]}"
            artifacts.append(
                InvestigationPattern(
                    artifact_id=f"lp-investigation_pattern-{digest}",
                    key=digest,
                    summary=summary,
                    observations=len(group),
                    confidence=self._support(len(group)),
                    supporting_regressions=corpus.cite(group),
                    updated_at=corpus.as_of,
                    signature=digest,
                    classification=classification,
                    confirmed_root_causes=causes,
                    successful_actions=actions,
                    typical_modules=modules[:6],
                    details={
                        "occurrences": len(group),
                        "confirmed_diagnoses": sum(
                            1 for r in group if corpus.was_confirmed(r.regression_id)
                        ),
                    },
                )
            )
        return artifacts


@register_learner
class EvidencePatternLearner(Learner):
    """Which co-occurring evidence combinations imply which outcome.

    The combination is the *set of deterministic signals that fired*, which is
    already normalized, already explainable, and already the vocabulary the
    reasoning engine reasons in. No text mining is involved.
    """

    learner_id = "evidence-patterns"
    artifact_kind = "evidence_pattern"

    def observe(self, corpus: Corpus) -> list[LearningArtifact]:
        by_signals: dict[tuple[str, ...], list] = {}
        for record in corpus.failures():
            report = record.report
            if report.reasoning is None or not report.reasoning.signals:
                continue
            key = tuple(sorted({s.name for s in report.reasoning.signals}))
            by_signals.setdefault(key, []).append(record)

        artifacts: list[LearningArtifact] = []
        for signals in sorted(by_signals):
            group = by_signals[signals]
            if len(group) < COOCCURRENCE_THRESHOLD:
                continue
            tally: dict[str, int] = {}
            for record in group:
                tally[record.classification] = tally.get(record.classification, 0) + 1
            dominant = Corpus.top_counts(tally, 1)[0]
            share = round(tally[dominant] / len(group), 4)
            key = "+".join(signals)
            # A content digest, never builtin hash(): str hashing is salted per
            # process, which would make artifact IDs differ between runs and
            # break the milestone's purity law.
            digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]
            artifacts.append(
                EvidencePattern(
                    artifact_id=f"lp-evidence_pattern-{digest}",
                    key=key,
                    summary=(
                        f"When {', '.join(signals)} fire together, the outcome has been "
                        f"{dominant.replace('_', ' ')} in {share:.0%} of "
                        f"{len(group)} recorded runs."
                    ),
                    observations=len(group),
                    confidence=round(self._support(len(group)) * share, 4),
                    supporting_regressions=corpus.cite(group),
                    updated_at=corpus.as_of,
                    signal_set=list(signals),
                    dominant_classification=dominant,
                    share=share,
                    details={"outcomes": dict(sorted(tally.items()))},
                )
            )
        return artifacts
