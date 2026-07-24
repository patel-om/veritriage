"""Investigation Orchestrator (Milestone 9).

Turns an investigation from an implicit call sequence into an explicit,
immutable, serializable Investigation Plan, executed by a deterministic
engine that composes existing Workspace Services and records a complete
Execution Trace. The orchestrator schedules and observes; it never
concludes: every technical conclusion still comes from the deterministic
intelligence stack, unchanged.

Public surface:

* profiles: ``get_profile`` / ``available_profiles`` / ``register_profile``
  and ``build_plan``.
* steps: ``InvestigationStep`` + ``register_step`` (the plugin seam).
* execution: ``ExecutionEngine``, ``run_profile``, ``resume_profile``,
  ``attribute_subsystems``.

Importing this package registers the built-in steps and profiles. The
orchestrator imports only the workspace and the models vocabulary: the
pipeline, parsers, engines, providers, and adapters are unimportable here by
architecture guard, so it cannot bypass Workspace Services even by accident.
"""

from veritriage.orchestrator.engine import (
    ExecutionEngine,
    attribute_subsystems,
    resume_profile,
    run_profile,
)
from veritriage.orchestrator.profiles import (
    InvestigationProfile,
    available_profiles,
    build_plan,
    get_profile,
    register_profile,
    unregister_profile,
)
from veritriage.orchestrator.steps import (
    InvestigationStep,
    StepError,
    available_steps,
    get_step,
    register_step,
    unregister_step,
)

__all__ = [
    "ExecutionEngine",
    "InvestigationProfile",
    "InvestigationStep",
    "StepError",
    "attribute_subsystems",
    "available_profiles",
    "available_steps",
    "build_plan",
    "get_profile",
    "get_step",
    "register_profile",
    "register_step",
    "resume_profile",
    "run_profile",
    "unregister_profile",
    "unregister_step",
]
