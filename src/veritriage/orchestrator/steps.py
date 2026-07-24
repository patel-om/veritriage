"""Investigation steps: the orchestrator's unit of work, over services only.

Every step is a thin, deterministic call into :class:`WorkspaceServices`: it
reads named artifacts from the execution context, calls one service, and
returns the artifacts it produced. Steps never conclude anything, never
touch a raw artifact beyond passing paths to ``investigate``, and never
import an engine, parser, provider, or the pipeline: the orchestrator cannot
bypass Workspace Services even by accident, because those modules are
unimportable here by architecture guard.

``@register_step`` is the plugin seam: a future workflow capability is one
registered step class referenced from a profile: no engine change, no core
change (``test_new_step_needs_only_registration`` proves it).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, ClassVar, TypeVar

from veritriage.workspace import WorkspaceServices, navigation  # noqa: F401  (navigation: step use)

_S = TypeVar("_S", bound=type["InvestigationStep"])

_REGISTRY: dict[str, type["InvestigationStep"]] = {}


class StepError(RuntimeError):
    """Raised by a step to signal a controlled failure (engine retries it)."""


class InvestigationStep(ABC):
    """Base class for every investigation step."""

    #: Unique registered step type name.
    step_type: ClassVar[str]

    #: Artifact names this step reads/writes by default (contract + trace
    #: bookkeeping; execution gating is by plan dependencies).
    default_inputs: ClassVar[tuple[str, ...]] = ()
    default_outputs: ClassVar[tuple[str, ...]] = ()

    @abstractmethod
    def run(
        self,
        services: WorkspaceServices,
        context: dict[str, Any],
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute; return the artifacts produced (name -> value)."""
        raise NotImplementedError


def register_step(step_cls: _S) -> _S:
    """Class decorator adding a step type to the registry.

    Raises:
        ValueError: If another step already registered the same type name.
    """
    existing = _REGISTRY.get(step_cls.step_type)
    if existing is not None and existing is not step_cls:
        raise ValueError(f"Step type {step_cls.step_type!r} is already registered by {existing!r}")
    _REGISTRY[step_cls.step_type] = step_cls
    return step_cls


def unregister_step(step_type: str) -> None:
    """Remove a step type (used by tests to clean up throwaway steps)."""
    _REGISTRY.pop(step_type, None)


def available_steps() -> dict[str, type[InvestigationStep]]:
    """All registered step types, keyed by name."""
    return dict(_REGISTRY)


def get_step(step_type: str) -> InvestigationStep:
    """Instantiate a registered step type.

    Raises:
        KeyError: If no step with that type name is registered.
    """
    try:
        return _REGISTRY[step_type]()
    except KeyError:
        known = ", ".join(sorted(_REGISTRY)) or "<none>"
        raise KeyError(f"Unknown step type {step_type!r}. Registered: {known}") from None


def _session(context: dict[str, Any]):
    session = context.get("session")
    if session is None:
        raise StepError("no session in the execution context; analyze-artifacts must run first")
    return session


# --- The built-in step library ----------------------------------------------


@register_step
class GatherContextStep(InvestigationStep):
    """Collect engineering context from the providers at the context root."""

    step_type = "gather-context"
    default_inputs = ("context_root",)
    default_outputs = ("engineering_context",)

    def run(self, services, context, params):
        root = Path(params.get("root") or context.get("context_root") or ".")
        gathered = services.gather_engineering_context(
            root, max_commits=int(params.get("max_commits", 10))
        )
        return {"engineering_context": gathered} if gathered is not None else {}


@register_step
class AnalyzeArtifactsStep(InvestigationStep):
    """Run the full deterministic intelligence pipeline, atomically.

    Deliberately one step: the pipeline's internal order (evidence ->
    knowledge -> waveform -> engineering -> reasoning) is the platform's
    core guarantee; the trace attributes its results per subsystem instead
    of fragmenting its execution (see INVESTIGATION_ORCHESTRATOR.md).
    """

    step_type = "analyze-artifacts"
    default_inputs = ("artifact_paths", "engineering_context")
    default_outputs = ("session",)

    def run(self, services, context, params):
        paths = [Path(p) for p in context.get("artifact_paths", [])]
        if not paths:
            raise StepError("no artifact paths in the execution context")
        session = services.investigate(
            paths,
            engineering=context.get("engineering_context"),
            record_history=bool(params.get("record_history", False)),
        )
        return {"session": session}


@register_step
class SummarizeStep(InvestigationStep):
    """Produce the bounded investigation summary."""

    step_type = "summarize"
    default_inputs = ("session",)
    default_outputs = ("summary",)

    def run(self, services, context, params):
        return {"summary": services.summary(_session(context))}


@register_step
class HistoricalLookupStep(InvestigationStep):
    """Ask the regression database: have we seen this before?"""

    step_type = "historical-lookup"
    default_inputs = ("session",)
    default_outputs = ("similar",)

    def run(self, services, context, params):
        similar = services.similar_regressions(
            _session(context), limit=int(params.get("limit", 5))
        )
        return {"similar": similar}


@register_step
class KnowledgeReviewStep(InvestigationStep):
    """Collect the matched verification patterns and their playbooks."""

    step_type = "knowledge-review"
    default_inputs = ("session",)
    default_outputs = ("knowledge_review",)

    def run(self, services, context, params):
        patterns = services.matched_patterns(_session(context))
        return {
            "knowledge_review": {
                "patterns": patterns,
                "playbooks": [p.playbook.name for p in patterns if p.playbook is not None],
            }
        }


@register_step
class WaveformReviewStep(InvestigationStep):
    """Collect waveform observations plus honest capability gaps."""

    step_type = "waveform-review"
    default_inputs = ("session",)
    default_outputs = ("waveform_review",)

    def run(self, services, context, params):
        session = _session(context)
        waveform = session.report.waveform
        return {
            "waveform_review": {
                "observations": services.waveform_observations(session),
                "unavailable": list(waveform.unavailable) if waveform else [],
            }
        }


@register_step
class EngineeringReviewStep(InvestigationStep):
    """Collect the engineering-context slice: changes, CI drift, ownership."""

    step_type = "engineering-review"
    default_inputs = ("session",)
    default_outputs = ("engineering_review",)

    def run(self, services, context, params):
        return {"engineering_review": services.engineering_context(_session(context))}


@register_step
class BuildTimelineStep(InvestigationStep):
    """Assemble the investigation timeline."""

    step_type = "build-timeline"
    default_inputs = ("session",)
    default_outputs = ("timeline",)

    def run(self, services, context, params):
        return {"timeline": services.timeline(_session(context))}


@register_step
class RenderReportStep(InvestigationStep):
    """Write analysis.json, evidence_graph.json, and report.html."""

    step_type = "render-report"
    default_inputs = ("session", "output_dir", "step_metrics")
    default_outputs = ("report_path",)

    def run(self, services, context, params):
        session = _session(context)
        out_dir = Path(
            params.get("output_dir")
            or context.get("output_dir")
            or Path(".veritriage") / "reports" / session.session_id
        )
        metrics = context.get("step_metrics")
        path = services.render_report(session, out_dir, metrics=metrics)
        return {"report_path": str(path)}


@register_step
class PersistSessionStep(InvestigationStep):
    """Save the session bundle (the orchestrator re-saves it afterwards with
    the completed plan and trace embedded; see engine.run_profile)."""

    step_type = "persist-session"
    default_inputs = ("session",)
    default_outputs = ("session_path",)

    def run(self, services, context, params):
        return {"session_path": str(services.save(_session(context)))}
