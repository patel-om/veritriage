"""Annotations: immutable notes pinned to existing session objects by ID.

Every annotation references a real object in the session; the target kinds are
a registry, so a new annotation type is one ``register_annotation_target``
call plus a resolver ("does this ID exist in this session?") with no change to
the bundle model, validation, exchange, or Workspace
(``test_new_annotation_target_needs_only_registration``).

Adding an annotation returns a new, resealed bundle; the embedded session is
never touched (``test_annotations_never_mutate_sessions``).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from typing import Callable

from veritriage.collab.model import Annotation, InvestigationBundle, seal_bundle
from veritriage.workspace.session import InvestigationSession

#: A resolver answers: does ``target_id`` exist in ``session``?
TargetResolver = Callable[[InvestigationSession, str], bool]

_TARGETS: dict[str, TargetResolver] = {}


def register_annotation_target(kind: str, resolver: TargetResolver) -> None:
    """Register an annotation target kind and its existence resolver.

    Raises:
        ValueError: If a different resolver already registered this kind.
    """
    existing = _TARGETS.get(kind)
    if existing is not None and existing is not resolver:
        raise ValueError(f"Annotation target {kind!r} is already registered")
    _TARGETS[kind] = resolver


def unregister_annotation_target(kind: str) -> None:
    """Remove a target kind (used by tests to clean up throwaway kinds)."""
    _TARGETS.pop(kind, None)


def available_targets() -> tuple[str, ...]:
    """Every registered annotation target kind, sorted."""
    return tuple(sorted(_TARGETS))


def target_exists(session: InvestigationSession, target_type: str, target_id: str) -> bool:
    """Whether ``target_id`` resolves for ``target_type`` in ``session``.

    An unknown target kind resolves to False, so validation flags it.
    """
    resolver = _TARGETS.get(target_type)
    return bool(resolver and resolver(session, target_id))


def make_annotation_id(target_type: str, target_id: str, author: str, text: str) -> str:
    digest = hashlib.sha1(f"{target_type}|{target_id}|{author}|{text}".encode("utf-8")).hexdigest()
    return f"ann-{digest[:12]}"


def add_annotation(
    bundle: InvestigationBundle,
    target_type: str,
    target_id: str,
    author: str,
    text: str,
    now: datetime | None = None,
) -> InvestigationBundle:
    """Append an annotation and return a new, resealed bundle.

    Raises:
        ValueError: If the target kind is unknown or the target does not exist
            in the session (annotations may never dangle).
    """
    if target_type not in _TARGETS:
        raise ValueError(
            f"Unknown annotation target {target_type!r}; registered: {', '.join(available_targets()) or 'none'}"
        )
    if not target_exists(bundle.session, target_type, target_id):
        raise ValueError(
            f"Annotation target {target_type}:{target_id} does not exist in this investigation"
        )
    annotation = Annotation(
        id=make_annotation_id(target_type, target_id, author, text),
        target_type=target_type,
        target_id=target_id,
        author=author,
        text=text,
        created_at=now or datetime.now(timezone.utc),
    )
    return seal_bundle(bundle.model_copy(update={"annotations": (*bundle.annotations, annotation)}))


# --- Built-in target resolvers ----------------------------------------------


def _evidence_exists(session: InvestigationSession, target_id: str) -> bool:
    return target_id in session.graph.nodes


def _pattern_exists(session: InvestigationSession, target_id: str) -> bool:
    knowledge = session.report.knowledge
    return knowledge is not None and any(p.pattern_id == target_id for p in knowledge.patterns)


def _waveform_exists(session: InvestigationSession, target_id: str) -> bool:
    waveform = session.report.waveform
    return waveform is not None and any(
        o.observation_id == target_id for o in waveform.observations
    )


def _commit_exists(session: InvestigationSession, target_id: str) -> bool:
    engineering = session.report.engineering
    return engineering is not None and any(
        c.revision == target_id or c.revision.startswith(target_id) for c in engineering.commits
    )


def _recommendation_exists(session: InvestigationSession, target_id: str) -> bool:
    reasoning = session.report.reasoning
    if reasoning is None or not target_id.isdigit():
        return False
    return 0 <= int(target_id) < len(reasoning.recommendations)


def _step_exists(session: InvestigationSession, target_id: str) -> bool:
    return session.trace is not None and any(s.step_id == target_id for s in session.trace.steps)


def register_builtin_targets() -> None:
    """Register the v1 annotation target kinds (idempotent)."""
    register_annotation_target("evidence", _evidence_exists)
    register_annotation_target("knowledge-pattern", _pattern_exists)
    register_annotation_target("waveform-observation", _waveform_exists)
    register_annotation_target("engineering-commit", _commit_exists)
    register_annotation_target("recommendation", _recommendation_exists)
    register_annotation_target("execution-step", _step_exists)
