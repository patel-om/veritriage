"""Protocol statistics: which Knowledge Packs actually earn their place.

42 packs and 92 patterns ship today with no record of which ever fire, and no
record of which fire and mislead. This learner supplies both, which is exactly
the labelled data a future pack author needs: a pattern that matches often but
never accompanies a confirmed diagnosis is a candidate for revision.

Curated knowledge stays curated. This learner reports on packs; it never edits
one.
"""

from __future__ import annotations

from veritriage.learning.corpus import Corpus
from veritriage.learning.registry import Learner, register_learner
from veritriage.models import LearningArtifact, ProtocolStatistics


@register_learner
class ProtocolStatisticsLearner(Learner):
    """Per-pack match counts and how often those matches were confirmed."""

    learner_id = "protocol-statistics"
    artifact_kind = "protocol_statistics"

    def observe(self, corpus: Corpus) -> list[LearningArtifact]:
        matched: dict[str, int] = {}
        confirmed: dict[str, int] = {}
        patterns: dict[str, set[str]] = {}
        cited: dict[str, list] = {}

        for record in corpus.records:
            knowledge = record.report.knowledge
            if knowledge is None or not knowledge.patterns:
                continue
            was_confirmed = corpus.was_confirmed(record.regression_id)
            for pack in sorted({p.pack for p in knowledge.patterns}):
                matched[pack] = matched.get(pack, 0) + 1
                cited.setdefault(pack, []).append(record)
                if was_confirmed:
                    confirmed[pack] = confirmed.get(pack, 0) + 1
            for pattern in knowledge.patterns:
                patterns.setdefault(pattern.pack, set()).add(pattern.pattern_id)

        artifacts: list[LearningArtifact] = []
        for pack in sorted(matched):
            times_matched = matched[pack]
            times_confirmed = confirmed.get(pack, 0)
            summary = (
                f"The {pack} pack matched evidence in {times_matched} recorded run(s)"
                + (
                    f", {times_confirmed} of which an engineer confirmed."
                    if times_confirmed
                    else "; none has been confirmed by an engineer yet."
                )
            )
            artifacts.append(
                ProtocolStatistics(
                    artifact_id=f"lp-protocol_statistics-{pack}",
                    key=pack,
                    summary=summary,
                    observations=times_matched,
                    confidence=self._support(times_matched),
                    supporting_regressions=corpus.cite(cited.get(pack, [])),
                    updated_at=corpus.as_of,
                    pack=pack,
                    times_matched=times_matched,
                    times_with_confirmation=times_confirmed,
                    pattern_ids=sorted(patterns.get(pack, set()))[:8],
                    details={"distinct_patterns_matched": len(patterns.get(pack, set()))},
                )
            )
        return artifacts
