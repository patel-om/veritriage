"""The Automation Engine (M18): the platform reacts.

Not continuously, not autonomously debugging, and not by running anything: by
observing changes it already detects and deciding what should follow.

The law, pinned by tests: **automation observes and decides; it never concludes
and never executes.** This package imports only ``models``. It publishes
events, evaluates triggers, fires rules, and emits ``ActionRequest`` objects
naming capabilities the workspace already has. The workspace executes them.

That separation is why the non-goals hold by construction rather than by
policy: there is no simulation, no CI call, no webhook, no OS job, and no file
I/O anywhere here, because there is no code path to any of them.

Importing this package registers the built-in triggers and rules.
"""

from veritriage.automation import builtin  # noqa: F401  (registers the built-in rules)
from veritriage.automation.builtin import BUILT_IN_RULES, register_built_in_rules
from veritriage.automation.bus import DEFAULT_CAPACITY, EventBus
from veritriage.automation.rules import (
    RuleEngine,
    available_rules,
    enabled_rules,
    register_rule,
    unregister_rule,
)
from veritriage.automation.triggers import (
    Trigger,
    available_triggers,
    get_trigger,
    register_trigger,
    unregister_trigger,
)

__all__ = [
    "BUILT_IN_RULES",
    "DEFAULT_CAPACITY",
    "EventBus",
    "RuleEngine",
    "Trigger",
    "available_rules",
    "available_triggers",
    "enabled_rules",
    "get_trigger",
    "register_built_in_rules",
    "register_rule",
    "register_trigger",
    "unregister_rule",
    "unregister_trigger",
]
