"""The Planning Engine (M14): what should happen next.

Reasoning determines what is likely true. Learning contributes historical
experience. Agents contribute specialized perspectives. **Planning determines
what should happen next.** It never changes conclusions; it consumes them.

The law, pinned by tests: **the Planner contributes structure, never content.**
Every step is derived from an artifact that already exists (a knowledge
playbook step, an agent recommendation, a reasoning recommendation, or an
evidence gap) and names it in ``derived_from``. Planning arranges, orders,
branches, and values what other layers produced.

Planning never executes: no file is opened, no tool is run, no step performed.

Named apart from the M9 orchestration vocabulary on purpose: an
``InvestigationPlan`` is what the platform will run, a ``DebugPlan`` is what the
engineer should do.

Importing this package registers the four built-in step sources.
"""

from veritriage.planning import sources  # noqa: F401  (registers the built-ins)
from veritriage.planning.context import PlanningContext, StepCandidate
from veritriage.planning.engine import Planner, build_plan
from veritriage.planning.progress import plan_progress
from veritriage.planning.registry import (
    StepSource,
    available_sources,
    default_sources,
    get_source,
    register_source,
    unregister_source,
)
from veritriage.planning.valuation import value_of

__all__ = [
    "Planner",
    "PlanningContext",
    "StepCandidate",
    "StepSource",
    "available_sources",
    "build_plan",
    "default_sources",
    "get_source",
    "plan_progress",
    "register_source",
    "unregister_source",
    "value_of",
]
