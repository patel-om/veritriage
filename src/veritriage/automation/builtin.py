"""The rules that ship.

Deliberately few, and every one earns its place by reacting to something the
platform already detects. A rule that fires on everything is noise, and noise is
how automation gets switched off.

Each is plain data: a trigger ID and a tuple of enum members. Adding one is a
``register_rule`` call with no code at all.
"""

from __future__ import annotations

from veritriage.automation.rules import register_rule
from veritriage.models import ActionKind, AutomationRule

#: A recurrence is the strongest signal the platform has that an investigation
#: is worth automating: the failure is real, reproducible, and already
#: characterized.
RECURRING_REGRESSION = AutomationRule(
    rule_id="recurring-regression",
    description=(
        "A known failure signature repeated. Plan the investigation and refresh "
        "learning so the recurrence is reflected in what the platform knows."
    ),
    when="regression.recurring",
    then=(ActionKind.GENERATE_PLAN, ActionKind.REFRESH_LEARNING, ActionKind.NOTIFY),
    priority=10,
)

#: A new signature is worth recording well, because it is what history will be
#: compared against next time.
NEW_REGRESSION = AutomationRule(
    rule_id="new-regression",
    description=(
        "A failure signature appeared for the first time. Capture a full report so "
        "the first occurrence is documented as thoroughly as later ones."
    ),
    when="regression.new",
    then=(ActionKind.GENERATE_REPORT, ActionKind.NOTIFY),
    priority=20,
)

#: Disagreement is precisely the moment a human should look, so it is precisely
#: the moment to surface.
SPECIALIST_DISAGREEMENT = AutomationRule(
    rule_id="specialist-disagreement",
    description=(
        "Domain specialists reached different conclusions. Surface it and plan the "
        "investigation that would separate them."
    ),
    when="agents.disagreement",
    then=(ActionKind.GENERATE_PLAN, ActionKind.NOTIFY),
    priority=15,
)

#: The platform's own health metric: an unexplained failure is where the next
#: rule or parser belongs.
UNEXPLAINED_FAILURE = AutomationRule(
    rule_id="unexplained-failure",
    description=(
        "The deterministic rule set could not explain this failure. Surface it: this "
        "is where the next rule, parser, or knowledge pack belongs."
    ),
    when="analysis.unexplained",
    then=(ActionKind.NOTIFY, ActionKind.SUMMARIZE_CHANGES),
    priority=25,
)

#: A provider outage must be visible without ever being alarming: analysis is
#: entirely unaffected.
PROVIDER_OUTAGE = AutomationRule(
    rule_id="provider-outage",
    description=(
        "A generative provider failed. Surface it so nobody mistakes missing prose "
        "for missing analysis."
    ),
    when="provider.failure",
    then=(ActionKind.NOTIFY,),
    priority=40,
)

#: A rebuilt project model invalidates the derived design graph.
PROJECT_REINDEXED = AutomationRule(
    rule_id="project-reindexed",
    description=(
        "The project model was rebuilt, so the derived design graph is stale. "
        "Rebuild it."
    ),
    when="project.indexed",
    then=(ActionKind.REBUILD_DESIGN_GRAPH,),
    priority=30,
)

BUILT_IN_RULES = (
    RECURRING_REGRESSION,
    SPECIALIST_DISAGREEMENT,
    NEW_REGRESSION,
    UNEXPLAINED_FAILURE,
    PROJECT_REINDEXED,
    PROVIDER_OUTAGE,
)


def register_built_in_rules() -> None:
    """Register every shipped rule. Idempotent."""
    for rule in BUILT_IN_RULES:
        register_rule(rule)


register_built_in_rules()
