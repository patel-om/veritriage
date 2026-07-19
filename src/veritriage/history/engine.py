"""The HistoryEngine: turns each analysis into memory, and memory into context.

Runs strictly *after* the reasoning engine and never modifies it. Its two
jobs:

1. **Record** the completed analysis into the regression database, with its
   deterministic signature and similarity embedding computed up front.
2. **Augment** the report with historical context: whether this exact
   failure signature has been seen before, which past regressions resemble
   it, and (as an *additional* recommendation, never a replacement) a
   pointer at the strongest precedent's known root cause.

Because augmentation only appends to the report's existing vocabulary
(HistoricalContext, EngineeringRecommendation), the reasoning pipeline's
output stays intact and its code stays untouched.
"""

from __future__ import annotations

from datetime import datetime, timezone

from veritriage.history.record import (
    ExecutionMetadata,
    RegressionRecord,
    extract_run_context,
    new_regression_id,
)
from veritriage.models import EngineeringRecommendation, HistoricalContext
from veritriage.pipeline import AnalysisOutcome
from veritriage.signatures import build_signature
from veritriage.similarity import SimilarFailureEngine
from veritriage.storage import RegressionStore

#: A historical pointer is worth surfacing as a step from this similarity up.
_PRECEDENT_THRESHOLD = 0.6
#: Historical confidence is discounted: precedent suggests, it does not prove.
_PRECEDENT_DISCOUNT = 0.85


class HistoryEngine:
    """Records analyses into the regression database and returns their context."""

    def __init__(
        self, store: RegressionStore, similarity: SimilarFailureEngine | None = None
    ) -> None:
        self._store = store
        self._similarity = similarity or SimilarFailureEngine(store)

    def record(
        self,
        outcome: AnalysisOutcome,
        execution: ExecutionMetadata | None = None,
        now: datetime | None = None,
    ) -> tuple[RegressionRecord, HistoricalContext]:
        """Store one completed analysis and compute its historical context.

        Similarity and seen-before counts are computed against history as it
        was *before* this run, then the run itself is saved.
        """
        report, graph = outcome
        signature = build_signature(report, graph)
        test_name, seed, configuration = extract_run_context(graph)
        record = RegressionRecord(
            regression_id=new_regression_id(signature.digest, now=now),
            created_at=now or datetime.now(timezone.utc),
            execution=execution or ExecutionMetadata(),
            test_name=test_name or report.summary.test_name,
            seed=seed,
            configuration=configuration,
            signature=signature,
            report=report,
            graph=graph,
        )
        record.embedding = self._similarity.provider.embed(record)

        times_seen = self._store.count_signature(signature.digest)
        similar = (
            self._similarity.find_similar(record) if record.is_failure else []
        )
        context = HistoricalContext(
            regression_id=record.regression_id,
            signature=signature.digest,
            seen_before=times_seen > 0,
            times_seen=times_seen,
            similar=similar,
        )
        self._store.save(record)
        return record, context

    def augment(self, outcome: AnalysisOutcome, context: HistoricalContext) -> None:
        """Attach historical context to the report, additively.

        The strongest precedent (signature match or high similarity) also
        becomes one extra recommendation so the historical lead shows up in
        the engineer's next-steps list, priced below nothing the reasoning
        engine produced: it is appended after the existing steps and its
        confidence is discounted from the similarity score.
        """
        report = outcome.report
        report.history = context
        if report.reasoning is None or not context.similar:
            return
        best = context.similar[0]
        if not best.signature_match and best.score < _PRECEDENT_THRESHOLD:
            return
        seen = (
            f"identical failure signature ({context.times_seen} prior occurrence"
            f"{'s' if context.times_seen != 1 else ''})"
            if best.signature_match
            else f"{best.score:.0%} similar failure profile"
        )
        recommendations = report.reasoning.recommendations
        recommendations.append(
            EngineeringRecommendation(
                action=(
                    f"Compare against regression {best.regression_id}"
                    + (f" (test {best.test_name})" if best.test_name else "")
                    + f": historically diagnosed as '{best.root_cause}'"
                ),
                rationale=f"Regression database precedent: {seen}.",
                priority=max((r.priority for r in recommendations), default=0) + 1,
                effort="low",
                confidence=round(best.score * _PRECEDENT_DISCOUNT, 4),
                module=None,
            )
        )
