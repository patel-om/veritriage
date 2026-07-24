"""Investigation Bundle vocabulary: the portable, reviewable engineering artifact.

A bundle is a thin, versioned, content-addressed envelope around an immutable
Investigation Session, plus the collaboration layer (reviews and annotations)
that sits *on top* of the session and never touches it. Everything needed to
understand a regression already travels in the session (normalized evidence,
reasoning, knowledge, waveform, engineering, plan, trace); the bundle adds
identity, integrity, and collaboration.

All models are frozen. Reviews and annotations are appended by returning a new
bundle (``model_copy``), never by mutation, so a received bundle's session is
byte-for-byte the session that was produced.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field

from veritriage.workspace.session import InvestigationSession

#: Bump on a breaking bundle-format change; validation understands majors.
BUNDLE_SCHEMA_VERSION = "1"


class ReviewVerdict(str, Enum):
    """A structured reviewer verdict on an investigation."""

    APPROVED = "approved"
    NEEDS_INVESTIGATION = "needs_investigation"
    INCORRECT_DIAGNOSIS = "incorrect_diagnosis"
    INCOMPLETE_EVIDENCE = "incomplete_evidence"
    FALSE_POSITIVE = "false_positive"


class Review(BaseModel):
    """One immutable review record, layered on top of the session."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="Deterministic content-derived ID.")
    verdict: ReviewVerdict
    reviewer: str
    comment: str = ""
    created_at: datetime


class Annotation(BaseModel):
    """One immutable annotation pinned to an existing session object by ID."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(description="Deterministic content-derived ID.")
    target_type: str = Field(description="A registered annotation-target kind.")
    target_id: str = Field(description="An object ID that must exist in the session.")
    author: str
    text: str
    created_at: datetime


class BundleMetadata(BaseModel):
    """Bundle-level metadata and the integrity fingerprint."""

    model_config = ConfigDict(frozen=True)

    session_id: str
    classification: str
    veritriage_version: str
    created_at: datetime
    exported_by: str | None = None
    title: str | None = None
    fingerprint: str = Field(
        default="", description="sha256 of the canonical bundle payload (fingerprint blanked)."
    )


class InvestigationBundle(BaseModel):
    """A portable, content-addressed investigation: session + collaboration.

    ``extra="allow"`` so a bundle written by a newer VeriTriage imports without
    data loss on an older one (validation reports unknown fields as warnings).
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    schema_version: str = BUNDLE_SCHEMA_VERSION
    bundle_id: str = Field(description="Content-derived (see make_bundle_id).")
    session: InvestigationSession
    reviews: tuple[Review, ...] = ()
    annotations: tuple[Annotation, ...] = ()
    metadata: BundleMetadata


def make_bundle_id(
    session_id: str,
    reviews: tuple[Review, ...],
    annotations: tuple[Annotation, ...],
    schema_version: str = BUNDLE_SCHEMA_VERSION,
) -> str:
    """Deterministic bundle ID from the session and its collaboration layer.

    The same session with the same reviews and annotations is the same
    bundle; adding either yields a new ID, preserving immutability.
    """
    parts = [
        schema_version,
        session_id,
        *sorted(r.id for r in reviews),
        *sorted(a.id for a in annotations),
    ]
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()
    return f"vtb-{digest[:12]}"


def canonical_payload(bundle: InvestigationBundle) -> str:
    """The bundle's canonical JSON with the fingerprint blanked.

    Deterministic (sorted keys, tight separators); the basis for both the
    integrity fingerprint and byte-stable export.
    """
    data = bundle.model_dump(mode="json")
    data.setdefault("metadata", {})["fingerprint"] = ""
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


def compute_fingerprint(bundle: InvestigationBundle) -> str:
    """sha256 of the canonical payload; the bundle's integrity seal."""
    return "sha256:" + hashlib.sha256(canonical_payload(bundle).encode("utf-8")).hexdigest()


def seal_bundle(bundle: InvestigationBundle) -> InvestigationBundle:
    """Return the bundle with a freshly recomputed ID and fingerprint.

    Called after constructing or amending a bundle so identity and integrity
    always reflect current content.
    """
    with_id = bundle.model_copy(
        update={
            "bundle_id": make_bundle_id(
                bundle.session.session_id,
                bundle.reviews,
                bundle.annotations,
                bundle.schema_version,
            )
        }
    )
    fingerprint = compute_fingerprint(with_id)
    return with_id.model_copy(
        update={"metadata": with_id.metadata.model_copy(update={"fingerprint": fingerprint})}
    )


def make_bundle(
    session: InvestigationSession,
    exported_by: str | None = None,
    title: str | None = None,
    now: datetime | None = None,
) -> InvestigationBundle:
    """Wrap one session into a sealed, review-free, annotation-free bundle."""
    created = now or datetime.now(timezone.utc)
    metadata = BundleMetadata(
        session_id=session.session_id,
        classification=session.report.classification.category.value,
        veritriage_version=session.veritriage_version,
        created_at=created,
        exported_by=exported_by,
        title=title,
    )
    draft = InvestigationBundle(
        bundle_id="",
        session=session,
        metadata=metadata,
    )
    return seal_bundle(draft)
