"""Triggers: declarative conditions over an event and its payload.

No scripting language, no expression parser, and no embedded code. A trigger is
a registered class with one ``matches()`` method, and a rule references it by
ID. That is the whole mechanism, and it is what keeps rules structured data
rather than programs.

A trigger reads only the event it is given. It never opens a file, calls a
service, or looks at platform state, so evaluation is a pure function and a
replay of the same log reaches the same verdicts.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar, TypeVar

from veritriage.models import Event, EventKind

_T = TypeVar("_T", bound=type["Trigger"])

_REGISTRY: dict[str, type["Trigger"]] = {}


class Trigger(ABC):
    """One declarative condition. Pure: reads the event and nothing else."""

    #: Unique registered trigger ID, referenced by AutomationRule.when.
    trigger_id: ClassVar[str]

    #: The event kind this trigger cares about. None means any kind.
    kind: ClassVar[EventKind | None] = None

    #: What this trigger is for, shown in status output.
    description: ClassVar[str] = ""

    def applies(self, event: Event) -> bool:
        return self.kind is None or event.kind is self.kind

    @abstractmethod
    def matches(self, event: Event) -> tuple[bool, str]:
        """Return (matched, reason). The reason is recorded either way."""
        raise NotImplementedError


def register_trigger(trigger_cls: _T) -> _T:
    """Class decorator adding a trigger to the registry.

    Raises:
        ValueError: If another trigger already registered the same ID.
    """
    existing = _REGISTRY.get(trigger_cls.trigger_id)
    if existing is not None and existing is not trigger_cls:
        raise ValueError(
            f"Trigger ID {trigger_cls.trigger_id!r} is already registered by {existing!r}"
        )
    _REGISTRY[trigger_cls.trigger_id] = trigger_cls
    return trigger_cls


def unregister_trigger(trigger_id: str) -> None:
    """Remove a trigger (used by tests to clean up throwaway triggers)."""
    _REGISTRY.pop(trigger_id, None)


def available_triggers() -> dict[str, type[Trigger]]:
    """All registered triggers, keyed by ID."""
    return dict(_REGISTRY)


def get_trigger(trigger_id: str) -> Trigger | None:
    """Instantiate a registered trigger, or None when unknown."""
    trigger_cls = _REGISTRY.get(trigger_id)
    return trigger_cls() if trigger_cls is not None else None


# --- The built-in triggers ---------------------------------------------------


@register_trigger
class NewRegressionTrigger(Trigger):
    """A failure signature the regression database has not seen before."""

    trigger_id = "regression.new"
    kind = EventKind.REGRESSION_DETECTED
    description = "A failure signature appears for the first time."

    def matches(self, event: Event) -> tuple[bool, str]:
        if event.payload.get("seen_before"):
            return False, "This signature has been seen before; it is not new."
        return True, "This failure signature is new to the regression database."


@register_trigger
class RecurringRegressionTrigger(Trigger):
    """A failure signature that has now repeated."""

    trigger_id = "regression.recurring"
    kind = EventKind.REGRESSION_DETECTED
    description = "A failure signature repeats."

    def matches(self, event: Event) -> tuple[bool, str]:
        times = int(event.payload.get("times_seen", 0) or 0)
        if not event.payload.get("seen_before"):
            return False, "This signature is new, so it has not recurred."
        return True, f"This signature has now been seen {times} time(s) before."


@register_trigger
class AgentDisagreementTrigger(Trigger):
    """Specialists reached different leading conclusions.

    Disagreement is the moment a human should look closely, which is exactly
    the moment worth reacting to.
    """

    trigger_id = "agents.disagreement"
    kind = EventKind.ANALYSIS_COMPLETED
    description = "Domain specialists disagreed, or diverged from deterministic reasoning."

    #: Below this many conflicting pairs, disagreement is routine.
    threshold = 1

    def matches(self, event: Event) -> tuple[bool, str]:
        conflicts = int(event.payload.get("agent_conflicts", 0) or 0)
        agrees = event.payload.get("agents_agree_with_reasoning")
        if conflicts >= self.threshold and agrees is False:
            return True, (
                f"{conflicts} specialist conflict(s), and the specialists diverge from "
                "the deterministic ranking."
            )
        if conflicts >= self.threshold:
            return True, f"{conflicts} specialist conflict(s) were recorded."
        return False, "The specialists agreed."


@register_trigger
class UnexplainedFailureTrigger(Trigger):
    """A failure the deterministic rule set could not classify.

    The platform's own health metric: this is where the next rule or parser
    should be added.
    """

    trigger_id = "analysis.unexplained"
    kind = EventKind.ANALYSIS_COMPLETED
    description = "A failure the rule set could not explain."

    def matches(self, event: Event) -> tuple[bool, str]:
        if event.payload.get("classification") == "unknown_failure":
            return True, (
                "The deterministic rule set could not explain this failure, which is "
                "where the next rule or parser belongs."
            )
        return False, "The failure was classified."


@register_trigger
class CriticalModuleTrigger(Trigger):
    """A failure touching a design region the project model knows about."""

    trigger_id = "design.region_affected"
    kind = EventKind.ANALYSIS_COMPLETED
    description = "A failure lands inside a known design region."

    def matches(self, event: Event) -> tuple[bool, str]:
        affected = int(event.payload.get("design_region_size", 0) or 0)
        if affected > 0:
            return True, f"{affected} structural element(s) sit around this failure."
        return False, "No design region was resolved for this failure."


@register_trigger
class CoverageHoleTrigger(Trigger):
    """A coverage hole correlated with the failing scope."""

    trigger_id = "coverage.hole_near_failure"
    kind = EventKind.ANALYSIS_COMPLETED
    description = "A coverage hole overlaps the failing scope."

    def matches(self, event: Event) -> tuple[bool, str]:
        signals = event.payload.get("signals", "")
        if "coverage-hole-near-failure" in str(signals):
            return True, "A coverage hole overlaps the failing scope."
        return False, "No coverage hole correlated with the failure."


@register_trigger
class ProviderFailureTrigger(Trigger):
    """A generative provider became unavailable or failed."""

    trigger_id = "provider.failure"
    kind = EventKind.PROVIDER_FAILURE
    description = "A generative provider failed."

    def matches(self, event: Event) -> tuple[bool, str]:
        provider = event.payload.get("provider", "unknown")
        return True, (
            f"The {provider!r} provider failed. Analysis is unaffected: generation is "
            "an additional view."
        )


@register_trigger
class LearningChangedTrigger(Trigger):
    """The learning corpus grew or its artifacts changed."""

    trigger_id = "learning.updated"
    kind = EventKind.LEARNING_UPDATED
    description = "Learning artifacts were recomputed."

    def matches(self, event: Event) -> tuple[bool, str]:
        corpus = int(event.payload.get("corpus_size", 0) or 0)
        return True, f"Learning was recomputed over {corpus} recorded investigation(s)."


@register_trigger
class ProjectGrewTrigger(Trigger):
    """The project model changed shape."""

    trigger_id = "project.indexed"
    kind = EventKind.PROJECT_INDEXED
    description = "A project model was built or rebuilt."

    def matches(self, event: Event) -> tuple[bool, str]:
        modules = int(event.payload.get("module_count", 0) or 0)
        return True, f"The project model now describes {modules} module(s)."


@register_trigger
class ScheduleTrigger(Trigger):
    """A caller supplied a clock tick.

    The platform never sleeps, spawns, or polls: a CI job, a cron entry someone
    else owns, or a future daemon publishes this.
    """

    trigger_id = "schedule.tick"
    kind = EventKind.SCHEDULE_TICK
    description = "A caller-supplied clock tick."

    def matches(self, event: Event) -> tuple[bool, str]:
        label = event.payload.get("label", "tick")
        return True, f"A caller published the {label!r} schedule tick."
