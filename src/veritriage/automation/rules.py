"""The rule engine: match a trigger, request actions, record the outcome.

Evaluation is a pure function of an event and the registered rules. It reads no
file, calls no service, and executes nothing: it produces
:class:`ActionRequest` objects naming capabilities the workspace already has,
and the workspace decides what to do with them.

That separation is the milestone's load-bearing decision. It is what keeps
evaluation replayable, what keeps automation out of the execution business, and
what makes "actions never execute arbitrary code" structurally true rather than
a policy: there is no code path from here to code.
"""

from __future__ import annotations

from typing import TypeVar

from veritriage.automation.triggers import get_trigger
from veritriage.models import (
    ActionKind,
    ActionRequest,
    AutomationRule,
    Event,
    RuleOutcome,
)

_R = TypeVar("_R", bound=AutomationRule)

_REGISTRY: dict[str, AutomationRule] = {}


def register_rule(rule: AutomationRule) -> AutomationRule:
    """Add a rule to the registry.

    Raises:
        ValueError: If another rule already uses the ID, or the rule references
            a trigger that is not registered. Failing at registration rather
            than silently never firing is the whole point of the check.
    """
    existing = _REGISTRY.get(rule.rule_id)
    if existing is not None and existing != rule:
        raise ValueError(f"Rule ID {rule.rule_id!r} is already registered")
    if get_trigger(rule.when) is None:
        raise ValueError(
            f"Rule {rule.rule_id!r} references unknown trigger {rule.when!r}; "
            "register the trigger first."
        )
    _REGISTRY[rule.rule_id] = rule
    return rule


def unregister_rule(rule_id: str) -> None:
    """Remove a rule (used by tests to clean up throwaway rules)."""
    _REGISTRY.pop(rule_id, None)


def available_rules() -> dict[str, AutomationRule]:
    """All registered rules, keyed by ID."""
    return dict(_REGISTRY)


def enabled_rules() -> list[AutomationRule]:
    """Enabled rules in deterministic firing order: priority, then ID."""
    return sorted(
        (r for r in _REGISTRY.values() if r.enabled),
        key=lambda r: (r.priority, r.rule_id),
    )


class RuleEngine:
    """Evaluates registered rules against events. Decides; never executes."""

    def __init__(self, rules: list[AutomationRule] | None = None) -> None:
        self._rules = rules  # None -> registry defaults, resolved per call

    def evaluate(self, event: Event) -> list[RuleOutcome]:
        """Every enabled rule's verdict on one event, in firing order.

        Outcomes are recorded whether or not a rule fired: knowing that a rule
        looked and declined is as useful as knowing it acted, and it is what
        makes automation auditable rather than merely active.
        """
        rules = self._rules if self._rules is not None else enabled_rules()
        outcomes: list[RuleOutcome] = []

        for rule in rules:
            trigger = get_trigger(rule.when)
            if trigger is None:
                outcomes.append(
                    RuleOutcome(
                        rule_id=rule.rule_id,
                        event_id=event.event_id,
                        event_kind=event.kind,
                        matched=False,
                        reason=f"Trigger {rule.when!r} is no longer registered.",
                    )
                )
                continue
            if not trigger.applies(event):
                continue  # wrong event kind: not a verdict, just not this rule's business

            try:
                matched, reason = trigger.matches(event)
            except Exception as exc:  # a broken trigger must not end evaluation
                outcomes.append(
                    RuleOutcome(
                        rule_id=rule.rule_id,
                        event_id=event.event_id,
                        event_kind=event.kind,
                        matched=False,
                        reason=(
                            f"Trigger {rule.when!r} failed ({type(exc).__name__}); the "
                            "analysis is unaffected."
                        ),
                    )
                )
                continue

            requests = (
                [
                    ActionRequest(
                        action=action,
                        reason=f"{rule.rule_id}: {reason}",
                        subject=event.subject,
                        params={"event_id": event.event_id},
                    )
                    for action in rule.then
                ]
                if matched
                else []
            )
            outcomes.append(
                RuleOutcome(
                    rule_id=rule.rule_id,
                    event_id=event.event_id,
                    event_kind=event.kind,
                    matched=matched,
                    reason=reason,
                    requests=requests,
                )
            )
        return outcomes

    def requests_for(self, event: Event) -> list[ActionRequest]:
        """Just the action requests, deduplicated by (action, subject).

        Two rules asking for the same thing is corroboration, not a reason to
        do it twice.
        """
        seen: dict[tuple[ActionKind, str | None], ActionRequest] = {}
        for outcome in self.evaluate(event):
            for request in outcome.requests:
                seen.setdefault((request.action, request.subject), request)
        return list(seen.values())
