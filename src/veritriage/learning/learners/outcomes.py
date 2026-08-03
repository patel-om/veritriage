"""Outcome learners: which advice helped, and which explanations held up.

Both read the half of `feedback/` that M4 designed and deliberately left
unbuilt. `FeedbackRecord.useful_recommendations`,
`false_recommendations`, and `diagnosis` have been written to SQLite since
v0.4.0 and read by nothing. These two learners are the readers.

Neither reweights anything by itself. They produce artifacts; whether a
recommendation is surfaced is a presentation decision made later, from data an
engineer can inspect.
"""

from __future__ import annotations

import hashlib

from veritriage.learning.corpus import Corpus
from veritriage.learning.registry import Learner, register_learner
from veritriage.models import HypothesisHistory, LearningArtifact, RecommendationOutcome


@register_learner
class RecommendationOutcomeLearner(Learner):
    """Which recommended actions engineers found useful, and which wasted time."""

    learner_id = "recommendation-outcomes"
    artifact_kind = "recommendation_outcome"

    def observe(self, corpus: Corpus) -> list[LearningArtifact]:
        useful: dict[str, int] = {}
        false: dict[str, int] = {}
        cited: dict[str, set[str]] = {}

        for item in corpus.feedback:
            for action in item.useful_recommendations:
                useful[action] = useful.get(action, 0) + 1
                cited.setdefault(action, set()).add(item.regression_id)
            for action in item.false_recommendations:
                false[action] = false.get(action, 0) + 1
                cited.setdefault(action, set()).add(item.regression_id)

        artifacts: list[LearningArtifact] = []
        for action in sorted(set(useful) | set(false)):
            up = useful.get(action, 0)
            down = false.get(action, 0)
            total = up + down
            usefulness = round(up / total, 4) if total else None
            digest = hashlib.sha1(action.encode("utf-8")).hexdigest()[:12]
            if usefulness is None:
                summary = f"'{action}' has been recommended but never rated."
            elif usefulness >= 0.5:
                summary = (
                    f"'{action}' helped in {up} of {total} rated investigation(s)."
                )
            else:
                summary = (
                    f"'{action}' wasted time in {down} of {total} rated "
                    "investigation(s); it may deserve revision."
                )
            artifacts.append(
                RecommendationOutcome(
                    artifact_id=f"lp-recommendation_outcome-{digest}",
                    key=action,
                    summary=summary,
                    observations=total,
                    confidence=self._support(total, saturation=4),
                    supporting_regressions=sorted(cited.get(action, set()))[:8],
                    updated_at=corpus.as_of,
                    action=action,
                    useful_votes=up,
                    false_votes=down,
                    usefulness=usefulness,
                )
            )
        return artifacts


@register_learner
class HypothesisHistoryLearner(Learner):
    """How often each hypothesis category led, and how often it held up."""

    learner_id = "hypothesis-history"
    artifact_kind = "hypothesis_history"

    def observe(self, corpus: Corpus) -> list[LearningArtifact]:
        led: dict[str, int] = {}
        judged: dict[str, int] = {}
        confirmed: dict[str, int] = {}
        cited: dict[str, list] = {}

        for record in corpus.failures():
            reasoning = record.report.reasoning
            if reasoning is None or not reasoning.hypotheses:
                continue
            category = reasoning.hypotheses[0].category.value
            led[category] = led.get(category, 0) + 1
            cited.setdefault(category, []).append(record)
            verdict = corpus.diagnosis(record.regression_id)
            if verdict is None:
                continue
            judged[category] = judged.get(category, 0) + 1
            if verdict == "correct":
                confirmed[category] = confirmed.get(category, 0) + 1

        artifacts: list[LearningArtifact] = []
        for category in sorted(led):
            times_judged = judged.get(category, 0)
            times_confirmed = confirmed.get(category, 0)
            rate = round(times_confirmed / times_judged, 4) if times_judged else None
            readable = category.replace("_", " ")
            if rate is None:
                summary = (
                    f"'{readable}' led {led[category]} investigation(s); none judged yet."
                )
            else:
                summary = (
                    f"'{readable}' led {led[category]} investigation(s) and was "
                    f"confirmed in {rate:.0%} of {times_judged} judged."
                )
            artifacts.append(
                HypothesisHistory(
                    artifact_id=f"lp-hypothesis_history-{category}",
                    key=category,
                    summary=summary,
                    observations=led[category],
                    confidence=self._support(times_judged),
                    supporting_regressions=corpus.cite(cited.get(category, [])),
                    updated_at=corpus.as_of,
                    category=category,
                    times_led=led[category],
                    times_confirmed=times_confirmed,
                    confirmation_rate=rate,
                    details={"times_judged_by_an_engineer": times_judged},
                )
            )
        return artifacts
