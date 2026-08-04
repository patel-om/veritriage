"""Agent reliability: which specialists have historically been right.

This is the question that structurally cannot be answered inside an agent,
because it is a question *about* agents. It needs a component that observes all
of them from above, which is exactly what the Learning Engine is.

"Correct" is defined conservatively and explainably: an agent led an
investigation when its leading category matched the merged top category, and it
was correct when an engineer subsequently marked that investigation's diagnosis
correct. Runs no engineer judged count toward neither, so reliability reflects
confirmed outcomes rather than the platform grading its own homework.
"""

from __future__ import annotations

from veritriage.learning.calibration import calibration_multiplier
from veritriage.learning.corpus import Corpus
from veritriage.learning.registry import Learner, register_learner
from veritriage.models import AgentReliability, LearningArtifact


@register_learner
class AgentReliabilityLearner(Learner):
    """Per-specialist track record, and the calibration it earns."""

    learner_id = "agent-reliability"
    artifact_kind = "agent_reliability"

    def observe(self, corpus: Corpus) -> list[LearningArtifact]:
        applicable: dict[str, int] = {}
        led: dict[str, int] = {}
        correct: dict[str, int] = {}
        judged: dict[str, int] = {}
        cited: dict[str, list] = {}

        for record in corpus.records:
            assessment = record.report.agents
            if assessment is None:
                continue
            verdict = corpus.diagnosis(record.regression_id)
            for result in assessment.results:
                if not result.applicable:
                    continue
                applicable[result.agent_id] = applicable.get(result.agent_id, 0) + 1
                # Cite on applicability, not on leading: the artifact reports how
                # often the specialist was applicable, so those are the runs it
                # must link back to. Citing only leading runs left an artifact
                # with observations and no provenance whenever a specialist was
                # consulted but never led.
                cited.setdefault(result.agent_id, []).append(record)
                if result.abstained or result.leading_category is None:
                    continue
                if result.leading_category != assessment.top_category:
                    continue
                led[result.agent_id] = led.get(result.agent_id, 0) + 1
                if verdict is None:
                    continue
                judged[result.agent_id] = judged.get(result.agent_id, 0) + 1
                if verdict == "correct":
                    correct[result.agent_id] = correct.get(result.agent_id, 0) + 1

        artifacts: list[LearningArtifact] = []
        for agent_id in sorted(applicable):
            times_led = led.get(agent_id, 0)
            times_judged = judged.get(agent_id, 0)
            times_correct = correct.get(agent_id, 0)
            # Accuracy is measured only over investigations an engineer judged.
            accuracy = (
                round(times_correct / times_judged, 4) if times_judged > 0 else None
            )
            multiplier = calibration_multiplier(accuracy, times_judged)
            if accuracy is None:
                summary = (
                    f"The {agent_id} specialist has been applicable in "
                    f"{applicable[agent_id]} recorded run(s) and led {times_led} of "
                    "them; no engineer feedback yet, so its influence is uncalibrated."
                )
            else:
                summary = (
                    f"The {agent_id} specialist's leading position matched the "
                    f"confirmed outcome in {accuracy:.0%} of {times_judged} judged "
                    f"investigation(s)."
                )
            artifacts.append(
                AgentReliability(
                    artifact_id=f"lp-agent_reliability-{agent_id}",
                    key=agent_id,
                    summary=summary,
                    observations=applicable[agent_id],
                    confidence=self._support(times_judged),
                    supporting_regressions=corpus.cite(cited.get(agent_id, [])),
                    updated_at=corpus.as_of,
                    agent_id=agent_id,
                    times_applicable=applicable[agent_id],
                    times_led=times_judged,
                    times_correct=times_correct,
                    accuracy=accuracy,
                    calibration_multiplier=multiplier,
                    details={
                        "times_leading_overall": times_led,
                        "times_judged_by_an_engineer": times_judged,
                    },
                )
            )
        return artifacts
