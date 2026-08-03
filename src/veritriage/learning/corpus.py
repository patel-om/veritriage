"""The Corpus: an indexed, read-only view over recorded history.

Everything a learner is allowed to see. It contains only normalized platform
objects (stored reports, stored Evidence Graphs, engineer feedback), so a
learner physically cannot reach a raw artifact: the regression database never
held one.

The Corpus is also where the milestone's central law is made mechanical.
``as_of`` is the newest recorded run's timestamp, not the wall clock, so
recomputing artifacts from the same history produces byte-identical output no
matter when the recomputation happens.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, Sequence

if TYPE_CHECKING:  # pragma: no cover - typing only
    from veritriage.feedback import FeedbackRecord
    from veritriage.history.record import RegressionRecord

#: Cap on how many regression IDs an artifact cites. Enough to audit a claim,
#: bounded so a large corpus cannot bloat the store or the report.
MAX_CITED = 8


class Corpus:
    """Recorded history, indexed for the learners."""

    def __init__(
        self,
        records: Sequence["RegressionRecord"],
        feedback: Sequence["FeedbackRecord"] = (),
    ) -> None:
        # Sorted by ID so every derived artifact is order-independent: the same
        # history learned in a different insertion order yields the same result.
        self.records = sorted(records, key=lambda r: r.regression_id)
        self.feedback = sorted(
            feedback, key=lambda f: (f.regression_id, f.created_at.isoformat())
        )
        self._feedback_by_regression: dict[str, list["FeedbackRecord"]] = {}
        for item in self.feedback:
            self._feedback_by_regression.setdefault(item.regression_id, []).append(item)

    # --- Shape --------------------------------------------------------------

    def __len__(self) -> int:
        return len(self.records)

    @property
    def as_of(self) -> str:
        """Newest recorded run's timestamp; the corpus clock, never the real one."""
        if not self.records:
            return ""
        return max(r.created_at for r in self.records).isoformat()

    def failures(self) -> list["RegressionRecord"]:
        return [r for r in self.records if r.is_failure]

    # --- Feedback -----------------------------------------------------------

    def feedback_for(self, regression_id: str) -> list["FeedbackRecord"]:
        return list(self._feedback_by_regression.get(regression_id, ()))

    def diagnosis(self, regression_id: str) -> str | None:
        """The engineer's verdict on a run: 'correct', 'incorrect', or None.

        The newest judgment wins when an engineer revised their opinion.
        """
        judged = [f.diagnosis for f in self.feedback_for(regression_id) if f.diagnosis]
        return judged[-1] if judged else None

    def confirmed_cause(self, regression_id: str) -> str | None:
        """The engineer-recorded root cause for a run, if one exists."""
        causes = [
            f.actual_root_cause
            for f in self.feedback_for(regression_id)
            if f.actual_root_cause
        ]
        return causes[-1] if causes else None

    def was_confirmed(self, regression_id: str) -> bool:
        """True when an engineer explicitly marked the diagnosis correct."""
        return self.diagnosis(regression_id) == "correct"

    # --- Helpers shared by learners -----------------------------------------

    @staticmethod
    def cite(records: Iterable["RegressionRecord"]) -> list[str]:
        """A bounded, sorted sample of regression IDs backing a claim."""
        return sorted({r.regression_id for r in records})[:MAX_CITED]

    @staticmethod
    def top_counts(tally: dict[str, int], limit: int) -> list[str]:
        """The most frequent keys, ties broken alphabetically for determinism."""
        return [
            key
            for key, _ in sorted(tally.items(), key=lambda pair: (-pair[1], pair[0]))[:limit]
        ]
