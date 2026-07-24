"""Investigation profiles: named, registered compositions of steps.

A profile selects which services participate in an investigation and in what
dependency order: it contains zero reasoning logic and changes nothing about
how any service behaves. ``@register_profile`` is the extension point; the
built-ins cover the spectrum from a thirty-second triage to the
everything-on reference workflow.

Plan IDs are deterministic: the same profile over the same inputs is the
same plan, byte for byte.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Sequence, TypeVar

from pydantic import BaseModel, ConfigDict, Field

from veritriage.models import InvestigationPlan, PlanStep

_P = TypeVar("_P", bound="InvestigationProfile")

_REGISTRY: dict[str, "InvestigationProfile"] = {}


class InvestigationProfile(BaseModel):
    """One named workflow: which steps run, and their dependency shape."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    steps: tuple[PlanStep, ...] = Field(min_length=1)


def register_profile(profile: InvestigationProfile) -> InvestigationProfile:
    """Register a profile under its name.

    Raises:
        ValueError: If another profile already registered the same name.
    """
    if profile.name in _REGISTRY and _REGISTRY[profile.name] != profile:
        raise ValueError(f"Profile {profile.name!r} is already registered")
    _REGISTRY[profile.name] = profile
    return profile


def unregister_profile(name: str) -> None:
    """Remove a profile (used by tests to clean up throwaway profiles)."""
    _REGISTRY.pop(name, None)


def available_profiles() -> dict[str, InvestigationProfile]:
    """All registered profiles, keyed by name."""
    return dict(_REGISTRY)


def get_profile(name: str) -> InvestigationProfile:
    """Look a profile up by name.

    Raises:
        KeyError: If no profile with that name is registered.
    """
    try:
        return _REGISTRY[name]
    except KeyError:
        known = ", ".join(sorted(_REGISTRY)) or "<none>"
        raise KeyError(f"Unknown profile {name!r}. Registered: {known}") from None


def build_plan(profile: InvestigationProfile, created_for: Sequence[str | Path]) -> InvestigationPlan:
    """Instantiate one immutable plan from a profile.

    The plan carries no execution state; statuses live in the trace.
    """
    names = tuple(str(Path(p).name) if isinstance(p, Path) else str(p) for p in created_for)
    digest = hashlib.sha1(
        "|".join([profile.name, *(s.id for s in profile.steps), *sorted(names)]).encode("utf-8")
    ).hexdigest()
    return InvestigationPlan(
        plan_id=f"plan-{digest[:12]}",
        profile=profile.name,
        created_for=names,
        steps=profile.steps,
    )


# --- Built-in profiles ------------------------------------------------------

#: Shared step shapes, written once so profiles stay declarative.
def _step(
    id: str,
    step_type: str | None = None,
    depends_on: tuple[str, ...] = (),
    inputs: tuple[str, ...] = (),
    outputs: tuple[str, ...] = (),
    **params: object,
) -> PlanStep:
    return PlanStep(
        id=id,
        step_type=step_type or id,
        depends_on=depends_on,
        inputs=inputs,
        outputs=outputs,
        params=dict(params),
    )


_ANALYZE = _step(
    "analyze-artifacts", inputs=("artifact_paths", "engineering_context"), outputs=("session",)
)
_ANALYZE_RECORDING = _step(
    "analyze-artifacts",
    inputs=("artifact_paths", "engineering_context"),
    outputs=("session",),
    record_history=True,
)
_GATHER = _step("gather-context", inputs=("context_root",), outputs=("engineering_context",))


def _after_analyze(id: str, outputs: tuple[str, ...], step_type: str | None = None) -> PlanStep:
    return _step(
        id, step_type=step_type, depends_on=("analyze-artifacts",), inputs=("session",), outputs=outputs
    )


_SUMMARIZE = _after_analyze("summarize", ("summary",))
_PERSIST = _after_analyze("persist-session", ("session_path",))
_HISTORICAL = _after_analyze("historical-lookup", ("similar",))
_TIMELINE = _after_analyze("build-timeline", ("timeline",))
_KNOWLEDGE = _after_analyze("knowledge-review", ("knowledge_review",))
_WAVEFORM = _after_analyze("waveform-review", ("waveform_review",))
_ENGINEERING = _after_analyze("engineering-review", ("engineering_review",))
_REPORT = _after_analyze("render-report", ("report_path",))

_ANALYZE_AFTER_GATHER = _ANALYZE.model_copy(update={"depends_on": ("gather-context",)})
_ANALYZE_RECORDING_AFTER_GATHER = _ANALYZE_RECORDING.model_copy(
    update={"depends_on": ("gather-context",)}
)


register_profile(
    InvestigationProfile(
        name="fast-triage",
        description="The minimal loop: analyze, summarize, persist. Thirty seconds to a verdict.",
        steps=(_ANALYZE, _SUMMARIZE, _PERSIST),
    )
)

register_profile(
    InvestigationProfile(
        name="full-investigation",
        description="Everything on: context, analysis, history, timeline, report, session.",
        steps=(
            _GATHER,
            _ANALYZE_AFTER_GATHER,
            _SUMMARIZE,
            _HISTORICAL,
            _TIMELINE,
            _REPORT,
            _PERSIST,
        ),
    )
)

register_profile(
    InvestigationProfile(
        name="regression-analysis",
        description="Record the run into the regression database and rank historical precedents.",
        steps=(_ANALYZE_RECORDING, _SUMMARIZE, _HISTORICAL, _PERSIST),
    )
)

register_profile(
    InvestigationProfile(
        name="protocol-debug",
        description="Surface matched protocol patterns and their debug playbooks, with a report.",
        steps=(_ANALYZE, _SUMMARIZE, _KNOWLEDGE, _REPORT, _PERSIST),
    )
)

register_profile(
    InvestigationProfile(
        name="waveform-focused",
        description="Center the waveform observations and capability gaps, with a report.",
        steps=(_ANALYZE, _SUMMARIZE, _WAVEFORM, _REPORT, _PERSIST),
    )
)

register_profile(
    InvestigationProfile(
        name="infrastructure-review",
        description="Environment first: engineering context, CI drift, and historical precedent.",
        steps=(_GATHER, _ANALYZE_AFTER_GATHER, _SUMMARIZE, _ENGINEERING, _HISTORICAL, _PERSIST),
    )
)

register_profile(
    InvestigationProfile(
        name="engineering-review",
        description="What changed: engineering context, correlated changes, and the timeline.",
        steps=(_GATHER, _ANALYZE_AFTER_GATHER, _SUMMARIZE, _ENGINEERING, _TIMELINE, _PERSIST),
    )
)
