"""The deterministic execution engine: plans in, traces out.

Boring on purpose. Steps execute in Kahn topological order with the ready
frontier processed in sorted-id order, so the same plan always executes in
the same sequence (and the frontier is exactly the seam a future
asynchronous engine would dispatch concurrently, with no step changing).

Failure isolation is first-class: a step that raises is retried up to its
budget, then marked FAILED; its transitive dependents become SKIPPED with
the blocking step named; independent branches keep running, and partial
completion is a legitimate, fully-traced outcome.

Timings are wall-clock observability, never identity: the trace's
*structure* (steps, order, statuses, artifact flow, attribution) is
deterministic and test-compared; durations are excluded from determinism
guarantees. No AI is involved anywhere.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Sequence

from veritriage.models import (
    InvestigationPlan,
    InvestigationTrace,
    StepStatus,
    StepTrace,
    SubsystemAttribution,
)
from veritriage.orchestrator.profiles import build_plan, get_profile
from veritriage.orchestrator.steps import get_step
from veritriage.workspace import InvestigationSession, WorkspaceServices

#: Reasoning-signal name prefixes -> the subsystem that contributed them.
_SIGNAL_SUBSYSTEM = (
    ("knowledge:", "knowledge"),
    ("waveform:", "waveform"),
    ("engineering:", "engineering"),
    ("project:", "project"),
)

#: Recommendation-rationale markers -> the subsystem that appended them.
_RECOMMENDATION_MARKERS = (
    ("Regression database precedent", "history"),
    ("Ownership metadata", "ownership"),
)


class ExecutionEngine:
    """Executes one immutable plan against one services instance."""

    def __init__(self, services: WorkspaceServices) -> None:
        self._services = services

    def execute(
        self,
        plan: InvestigationPlan,
        seed_context: dict[str, Any] | None = None,
        completed_steps: frozenset[str] = frozenset(),
    ) -> tuple[dict[str, Any], InvestigationTrace]:
        """Run the plan; returns the final artifact context and the trace.

        ``completed_steps`` (used by resume) are carried into the trace as
        COMPLETED without re-execution; their artifacts must already be in
        ``seed_context``.
        """
        context: dict[str, Any] = dict(seed_context or {})
        by_id = {step.id: step for step in plan.steps}
        remaining_deps = {
            step.id: {d for d in step.depends_on if d not in completed_steps}
            for step in plan.steps
        }
        status: dict[str, StepStatus] = {step.id: StepStatus.PENDING for step in plan.steps}
        blocked_by: dict[str, str] = {}
        traces: list[StepTrace] = []
        context["step_metrics"] = {"profile": plan.profile, "total_ms": 0.0, "steps": []}
        started = time.perf_counter()

        for step_id in completed_steps:
            if step_id in by_id:
                status[step_id] = StepStatus.COMPLETED
                traces.append(
                    StepTrace(
                        step_id=step_id,
                        step_type=by_id[step_id].step_type,
                        status=StepStatus.COMPLETED,
                        attempts=0,
                        consumed=(),
                        produced=by_id[step_id].outputs,
                        note="carried over from the previous run",
                    )
                )

        ready = sorted(
            step_id
            for step_id, deps in remaining_deps.items()
            if not deps and status[step_id] is StepStatus.PENDING
        )
        while ready:
            step_id = ready.pop(0)
            spec = by_id[step_id]
            trace = self._run_step(spec, context)
            traces.append(trace)
            status[step_id] = trace.status
            context["step_metrics"]["steps"].append(
                {
                    "label": spec.id,
                    "status": trace.status.value,
                    "duration_ms": trace.duration_ms,
                }
            )
            context["step_metrics"]["total_ms"] = (time.perf_counter() - started) * 1000.0

            if trace.status is StepStatus.COMPLETED:
                newly_ready = []
                for other_id, deps in remaining_deps.items():
                    if step_id in deps:
                        deps.discard(step_id)
                        if not deps and status[other_id] is StepStatus.PENDING:
                            newly_ready.append(other_id)
                ready = sorted([*ready, *newly_ready])
            else:
                # Failure isolation: transitive dependents are skipped with the
                # blocking step named; everything independent keeps running.
                for dependent in self._transitive_dependents(plan, step_id):
                    if status[dependent] is StepStatus.PENDING:
                        status[dependent] = StepStatus.SKIPPED
                        blocked_by[dependent] = step_id
                ready = [r for r in ready if status[r] is StepStatus.PENDING]

        # Skipped steps enter the trace in deterministic plan order.
        for step in plan.steps:
            if status[step.id] is StepStatus.SKIPPED:
                traces.append(
                    StepTrace(
                        step_id=step.id,
                        step_type=step.step_type,
                        status=StepStatus.SKIPPED,
                        note=f"skipped: dependency '{blocked_by.get(step.id, '?')}' did not complete",
                    )
                )

        session = context.get("session")
        trace = InvestigationTrace(
            plan_id=plan.plan_id,
            profile=plan.profile,
            steps=tuple(traces),
            attribution=attribute_subsystems(session) if session is not None else (),
            total_duration_ms=(time.perf_counter() - started) * 1000.0,
            completed=all(s is StepStatus.COMPLETED for s in status.values()),
        )
        return context, trace

    def _run_step(self, spec, context: dict[str, Any]) -> StepTrace:
        """Execute one step with its retry budget; never raises."""
        consumed = tuple(name for name in spec.inputs if name in context)
        attempts = 0
        begun = time.perf_counter()
        last_error: str | None = None
        while attempts <= spec.max_retries:
            attempts += 1
            try:
                step = get_step(spec.step_type)
                produced = step.run(self._services, context, dict(spec.params)) or {}
                context.update(produced)
                return StepTrace(
                    step_id=spec.id,
                    step_type=spec.step_type,
                    status=StepStatus.COMPLETED,
                    attempts=attempts,
                    duration_ms=(time.perf_counter() - begun) * 1000.0,
                    consumed=consumed,
                    produced=tuple(sorted(produced)),
                    evidence=_step_evidence(produced),
                )
            except Exception as exc:  # noqa: BLE001 - isolation: recorded, never propagated
                last_error = f"{type(exc).__name__}: {exc}"
        return StepTrace(
            step_id=spec.id,
            step_type=spec.step_type,
            status=StepStatus.FAILED,
            attempts=attempts,
            duration_ms=(time.perf_counter() - begun) * 1000.0,
            consumed=consumed,
            note=last_error,
        )

    @staticmethod
    def _transitive_dependents(plan: InvestigationPlan, step_id: str) -> list[str]:
        dependents: set[str] = set()
        frontier = {step_id}
        while frontier:
            current = frontier.pop()
            for step in plan.steps:
                if current in step.depends_on and step.id not in dependents:
                    dependents.add(step.id)
                    frontier.add(step.id)
        return sorted(dependents)


def _step_evidence(produced: dict[str, Any]) -> tuple[str, ...]:
    """Key references from a step's artifacts, for the trace."""
    evidence: list[str] = []
    session = produced.get("session")
    if isinstance(session, InvestigationSession):
        evidence.append(f"session:{session.session_id}")
        evidence.append(f"evidence-nodes:{len(session.graph.nodes)}")
    for key in ("report_path", "session_path"):
        if key in produced:
            evidence.append(f"{key}:{produced[key]}")
    if "similar" in produced:
        evidence.append(f"similar-regressions:{len(produced['similar'])}")
    return tuple(evidence)


def attribute_subsystems(session: InvestigationSession) -> tuple[SubsystemAttribution, ...]:
    """Which subsystem contributed which signals and recommendations.

    Computed deterministically from the session: signal names carry their
    source prefix (knowledge:/waveform:/engineering:, else the built-in
    rules), and appended recommendations carry documented rationale markers
    (history precedent, ownership routing). No re-execution, no guessing.
    """
    reasoning = session.report.reasoning
    if reasoning is None:
        return ()
    signals: dict[str, list[str]] = {}
    for signal in reasoning.signals:
        subsystem = next(
            (name for prefix, name in _SIGNAL_SUBSYSTEM if signal.name.startswith(prefix)),
            "rules",
        )
        signals.setdefault(subsystem, []).append(signal.name)
    recommendations: dict[str, int] = {}
    for step in reasoning.recommendations:
        subsystem = next(
            (name for marker, name in _RECOMMENDATION_MARKERS if marker in step.rationale),
            "reasoning",
        )
        recommendations[subsystem] = recommendations.get(subsystem, 0) + 1
    subsystems = sorted(set(signals) | set(recommendations))
    return tuple(
        SubsystemAttribution(
            subsystem=name,
            signals=tuple(sorted(signals.get(name, []))),
            recommendations=recommendations.get(name, 0),
        )
        for name in subsystems
    )


def run_profile(
    services: WorkspaceServices,
    profile_name: str,
    paths: Sequence[Path],
    context_root: Path | None = None,
    output_dir: Path | None = None,
) -> InvestigationSession:
    """Run one investigation profile end to end; returns the final session.

    The returned (and persisted) session carries the plan and the complete
    trace, attached via ``model_copy`` so immutability holds and
    ``session_id`` is unchanged: workflow bookkeeping is never identity.
    """
    profile = get_profile(profile_name)
    plan = build_plan(profile, [str(p) for p in paths])
    seed: dict[str, Any] = {
        "artifact_paths": [str(p) for p in paths],
        "context_root": str(context_root or Path(".")),
    }
    if output_dir is not None:
        seed["output_dir"] = str(output_dir)
    context, trace = ExecutionEngine(services).execute(plan, seed_context=seed)

    session = context.get("session")
    if session is None:
        raise RuntimeError(
            f"profile {profile_name!r} produced no session "
            f"(analyze-artifacts {next((t.status.value for t in trace.steps if t.step_id == 'analyze-artifacts'), 'missing')})"
        )
    final = session.model_copy(update={"plan": plan, "trace": trace})
    services.save(final)
    return final


def resume_profile(
    services: WorkspaceServices, session_id: str
) -> InvestigationSession:
    """Re-execute only the steps a stored orchestrated session did not
    complete, reusing its analysis; a fully completed session is a no-op.

    Raises:
        KeyError: If the session does not exist or was not orchestrated.
    """
    session = services.load(session_id)
    if session is None:
        raise KeyError(f"Unknown session {session_id!r}")
    if session.plan is None or session.trace is None:
        raise KeyError(f"Session {session_id!r} was not produced by the orchestrator")
    if session.trace.completed:
        return session

    completed = frozenset(
        t.step_id for t in session.trace.steps if t.status is StepStatus.COMPLETED
    )
    seed: dict[str, Any] = {
        "artifact_paths": list(session.input_files),
        "context_root": ".",
        "session": session,
    }
    context, trace = ExecutionEngine(services).execute(
        session.plan, seed_context=seed, completed_steps=completed
    )
    final = context["session"].model_copy(update={"plan": session.plan, "trace": trace})
    services.save(final)
    return final
