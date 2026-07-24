"""Reviews: structured verdicts layered on top of an investigation.

A review records a reviewer's judgement (approved, needs investigation,
incorrect diagnosis, incomplete evidence, false positive) plus a comment. It
is metadata: a reviewer disagreeing with a diagnosis records
``INCORRECT_DIAGNOSIS``, they never edit the hypothesis. Adding a review
returns a new, resealed bundle; the session and its reasoning are untouched
(``test_reviews_never_affect_reasoning``).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from veritriage.collab.model import (
    InvestigationBundle,
    Review,
    ReviewVerdict,
    seal_bundle,
)


def make_review_id(verdict: ReviewVerdict, reviewer: str, comment: str, ordinal: int) -> str:
    digest = hashlib.sha1(
        f"{verdict.value}|{reviewer}|{comment}|{ordinal}".encode("utf-8")
    ).hexdigest()
    return f"rev-{digest[:12]}"


def add_review(
    bundle: InvestigationBundle,
    verdict: ReviewVerdict | str,
    reviewer: str,
    comment: str = "",
    now: datetime | None = None,
) -> InvestigationBundle:
    """Append a review and return a new, resealed bundle.

    Raises:
        ValueError: If ``verdict`` is not a known review verdict.
    """
    try:
        resolved = ReviewVerdict(verdict) if not isinstance(verdict, ReviewVerdict) else verdict
    except ValueError:
        known = ", ".join(v.value for v in ReviewVerdict)
        raise ValueError(f"Unknown review verdict {verdict!r}; expected one of: {known}") from None
    review = Review(
        id=make_review_id(resolved, reviewer, comment, len(bundle.reviews)),
        verdict=resolved,
        reviewer=reviewer,
        comment=comment,
        created_at=now or datetime.now(timezone.utc),
    )
    return seal_bundle(bundle.model_copy(update={"reviews": (*bundle.reviews, review)}))


def review_status(bundle: InvestigationBundle) -> str:
    """The bundle's current review posture, for display.

    The most recent review's verdict wins; unreviewed bundles read as pending.
    """
    if not bundle.reviews:
        return "unreviewed"
    return bundle.reviews[-1].verdict.value
