"""Project memory: what a project characteristically looks like.

Projects develop personalities. One fails mostly in the scoreboard after cache
configuration changes; another spends its life in reset sequencing. The Project
Model (M11) captures structure but carries no history, so this learner supplies
the other half: what has actually happened here, repeatedly.

Runs carrying a Project Model are keyed by its project ID. Runs without one are
grouped under a clearly labelled unscoped profile rather than being dropped, so
a team gets project memory before it writes a manifest.
"""

from __future__ import annotations

from veritriage.learning.corpus import Corpus
from veritriage.learning.registry import Learner, register_learner
from veritriage.models import LearningArtifact, ProjectProfile

#: Key used for runs that carry no Project Model.
UNSCOPED_KEY = "unscoped"

#: Corpus sizes at which a project's verification effort is described
#: differently. Labels are explainable, never scores.
ESTABLISHING_BELOW = 5
DEVELOPING_UNKNOWN_RATE = 0.30
MATURING_UNKNOWN_RATE = 0.10


@register_learner
class ProjectProfileLearner(Learner):
    """Dominant failure classes, common scopes, protocols, and maturity."""

    learner_id = "project-profiles"
    artifact_kind = "project_profile"

    def observe(self, corpus: Corpus) -> list[LearningArtifact]:
        by_project: dict[str, list] = {}
        for record in corpus.records:
            project = record.report.project
            key = project.project_id if project is not None else UNSCOPED_KEY
            by_project.setdefault(key, []).append(record)

        artifacts: list[LearningArtifact] = []
        for key in sorted(by_project):
            group = by_project[key]
            failures = [r for r in group if r.is_failure]

            classifications: dict[str, int] = {}
            modules: dict[str, int] = {}
            protocols: dict[str, int] = {}
            signatures: dict[str, int] = {}
            for record in failures:
                classifications[record.classification] = (
                    classifications.get(record.classification, 0) + 1
                )
                signatures[record.signature.digest] = (
                    signatures.get(record.signature.digest, 0) + 1
                )
                for module in record.signature.modules:
                    modules[module] = modules.get(module, 0) + 1
                knowledge = record.report.knowledge
                if knowledge is not None:
                    for pattern in knowledge.patterns:
                        protocols[pattern.pack] = protocols.get(pattern.pack, 0) + 1

            unknown = sum(
                1 for r in failures if r.classification == "unknown_failure"
            )
            unknown_rate = round(unknown / len(failures), 4) if failures else 0.0
            maturity = self._maturity(len(group), unknown_rate)
            recurring = sorted(d for d, count in signatures.items() if count >= 2)

            dominant = Corpus.top_counts(classifications, 3)
            label = "this project" if key != UNSCOPED_KEY else "runs without a project model"
            summary = (
                f"Across {len(group)} recorded run(s), {label} fails most often as "
                + (
                    ", ".join(c.replace("_", " ") for c in dominant)
                    if dominant
                    else "no recorded failures"
                )
                + f". Verification maturity: {maturity}."
            )
            artifacts.append(
                ProjectProfile(
                    artifact_id=f"lp-project_profile-{key}",
                    key=key,
                    summary=summary,
                    observations=len(group),
                    confidence=self._support(len(group)),
                    supporting_regressions=corpus.cite(group),
                    updated_at=corpus.as_of,
                    project_key=key,
                    dominant_classifications=dominant,
                    common_modules=Corpus.top_counts(modules, 5),
                    protocols=Corpus.top_counts(protocols, 5),
                    recurring_signatures=recurring[:6],
                    verification_maturity=maturity,
                    details={
                        "runs": len(group),
                        "failures": len(failures),
                        "unknown_failure_rate": unknown_rate,
                        "distinct_signatures": len(signatures),
                    },
                )
            )
        return artifacts

    @staticmethod
    def _maturity(runs: int, unknown_rate: float) -> str:
        """An explainable label, derived from corpus size and unexplained rate.

        The unknown-failure rate is the platform's own health metric: it
        measures how much of this project's failure population the
        deterministic rule set cannot yet explain.
        """
        if runs < ESTABLISHING_BELOW:
            return "establishing (too few runs to characterize)"
        if unknown_rate > DEVELOPING_UNKNOWN_RATE:
            return "developing (many failures still unexplained)"
        if unknown_rate > MATURING_UNKNOWN_RATE:
            return "maturing (most failures explained)"
        return "mature (failures are consistently explained)"
