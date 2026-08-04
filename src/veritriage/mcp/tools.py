"""The MCP tool table: transport-agnostic investigation tools over services.

Every tool is a name, a description, a JSON-schema input contract, and a
handler that calls :class:`WorkspaceServices` and returns JSON-serializable
normalized data. This table knows nothing about processes, sockets, or SDKs;
``server.py`` (stdio) is one thin transport over it, and any future hosting
(official SDK, HTTP) is another thin file over the same table.

No tool touches a raw artifact beyond handing file paths to ``investigate``,
and none bypasses the Verification Intelligence Core: everything routes
through services (``test_mcp_tools_route_through_services`` pins it).
Adding a tool is one ``register_tool`` call; the crown-jewel test proves a
new endpoint requires zero core changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel

from veritriage.workspace import WorkspaceServices, navigation

Handler = Callable[[WorkspaceServices, dict[str, Any]], Any]


@dataclass(frozen=True)
class ToolSpec:
    """One MCP tool: contract plus handler."""

    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Handler


_TOOLS: dict[str, ToolSpec] = {}


def register_tool(
    name: str, description: str, input_schema: dict[str, Any]
) -> Callable[[Handler], Handler]:
    """Decorator adding a tool to the table.

    Raises:
        ValueError: If another tool already registered the same name.
    """

    def _register(handler: Handler) -> Handler:
        if name in _TOOLS and _TOOLS[name].handler is not handler:
            raise ValueError(f"MCP tool name {name!r} is already registered")
        _TOOLS[name] = ToolSpec(
            name=name, description=description, input_schema=input_schema, handler=handler
        )
        return handler

    return _register


def unregister_tool(name: str) -> None:
    """Remove a tool (used by tests to clean up throwaway tools)."""
    _TOOLS.pop(name, None)


def list_tools() -> list[ToolSpec]:
    """Every registered tool, in sorted-name order (deterministic listing)."""
    return [_TOOLS[name] for name in sorted(_TOOLS)]


def call_tool(services: WorkspaceServices, name: str, arguments: dict[str, Any]) -> Any:
    """Dispatch one tool call; the transport serializes the result.

    Raises:
        KeyError: If no tool with that name is registered.
    """
    spec = _TOOLS.get(name)
    if spec is None:
        known = ", ".join(sorted(_TOOLS)) or "<none>"
        raise KeyError(f"Unknown tool {name!r}. Registered tools: {known}")
    return _serialize(spec.handler(services, arguments))


def _serialize(value: Any) -> Any:
    """Models to plain data, containers recursively; scalars pass through."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_serialize(v) for v in value]
    return value


def _require_session(services: WorkspaceServices, arguments: dict[str, Any]):
    session = services.load(str(arguments["session_id"]))
    if session is None:
        raise KeyError(f"Unknown session {arguments['session_id']!r}")
    return session


_SESSION_ARG = {
    "type": "object",
    "properties": {"session_id": {"type": "string", "description": "Investigation session ID."}},
    "required": ["session_id"],
}


def _session_arg_with(extra: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    schema = {
        "type": "object",
        "properties": {"session_id": _SESSION_ARG["properties"]["session_id"], **extra},
        "required": ["session_id", *(required or [])],
    }
    return schema


# --- The v1 tool set --------------------------------------------------------


@register_tool(
    "analyze_regression",
    "Analyze verification artifacts (simulation/compile logs, coverage, test "
    "metadata, waveform files, engineering-context manifests) into a persisted "
    "investigation session. Returns the session summary including session_id "
    "for follow-up queries.",
    {
        "type": "object",
        "properties": {
            "paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Artifact file paths to analyze together.",
            },
        },
        "required": ["paths"],
    },
)
def _analyze_regression(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    session = services.investigate([Path(p) for p in arguments["paths"]])
    services.save(session)
    return services.summary(session)


@register_tool(
    "get_investigation_summary",
    "The bounded summary of one investigation: classification, top hypothesis, "
    "layer counts, and whether this failure was seen before.",
    _SESSION_ARG,
)
def _get_summary(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    return services.summary(_require_session(services, arguments))


@register_tool(
    "get_evidence_graph",
    "The bounded, normalized Evidence Graph projection for one session: "
    "failing evidence first, plus the edges among included nodes.",
    _session_arg_with({"max_nodes": {"type": "integer", "description": "Node budget (default 60)."}}),
)
def _get_evidence_graph(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    session = _require_session(services, arguments)
    return services.evidence_graph_view(session, max_nodes=int(arguments.get("max_nodes", 60)))


@register_tool(
    "get_hypothesis",
    "One ranked hypothesis by ID, with its full evidence-cited confidence trace.",
    _session_arg_with(
        {"hypothesis_id": {"type": "string", "description": "e.g. 'hyp-rtl_bug'."}},
        required=["hypothesis_id"],
    ),
)
def _get_hypothesis(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    session = _require_session(services, arguments)
    return navigation.hypothesis(session, str(arguments["hypothesis_id"]))


@register_tool(
    "find_similar_regressions",
    "Historical regressions resembling this session, from the regression "
    "database: signature matches first, then similarity-ranked.",
    _session_arg_with({"limit": {"type": "integer", "description": "Max results (default 5)."}}),
)
def _find_similar(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    session = _require_session(services, arguments)
    return services.similar_regressions(session, limit=int(arguments.get("limit", 5)))


@register_tool(
    "search_knowledge",
    "Search the Verification Knowledge Base (13 packs: protocols, UVM, SVA, "
    "CDC, coherency...) for concepts, failure patterns, and debug playbooks.",
    {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Substring to search for."}},
        "required": ["query"],
    },
)
def _search_knowledge(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    return services.search_knowledge(str(arguments["query"]))


@register_tool(
    "search_playbooks",
    "Search debug playbooks across every Knowledge Pack: fixed, deterministic "
    "step-by-step debug sequences for known failure modes.",
    {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "Substring to search for."}},
        "required": ["query"],
    },
)
def _search_playbooks(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    from veritriage.workspace import search_playbooks

    return search_playbooks(str(arguments["query"]))


@register_tool(
    "list_matched_patterns",
    "The known verification failure patterns this investigation matched, with "
    "ownership, suggested signals, references, and playbooks.",
    _SESSION_ARG,
)
def _list_patterns(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    return services.matched_patterns(_require_session(services, arguments))


@register_tool(
    "get_waveform_observations",
    "Engineering observations the Waveform Intelligence Engine derived from "
    "waveform metadata: dead clocks, stalled FSMs, incomplete handshakes, "
    "unretired transactions.",
    _SESSION_ARG,
)
def _get_waveform(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    return services.waveform_observations(_require_session(services, arguments))


@register_tool(
    "get_engineering_context",
    "What changed before this run broke: recent commits with correlated "
    "failures, CI environment drift, ownership, and likely-impacted tests.",
    _SESSION_ARG,
)
def _get_engineering(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    return services.engineering_context(_require_session(services, arguments))


@register_tool(
    "get_timeline",
    "The investigation timeline: commits, CI, compile, simulation failures, "
    "waveform observations, and knowledge matches, in engineering order.",
    _SESSION_ARG,
)
def _get_timeline(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    return services.timeline(_require_session(services, arguments))


@register_tool(
    "search_evidence",
    "Search one session's evidence nodes by description or scope; every hit "
    "cites its node ID and artifact location.",
    _session_arg_with(
        {"query": {"type": "string", "description": "Substring to search for."}},
        required=["query"],
    ),
)
def _search_evidence(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    session = _require_session(services, arguments)
    return services.search(session, str(arguments["query"]))


# --- Orchestration tools (M9) -----------------------------------------------


@register_tool(
    "run_investigation",
    "Run one orchestrated investigation profile (fast-triage, "
    "full-investigation, regression-analysis, protocol-debug, "
    "waveform-focused, infrastructure-review, engineering-review) over "
    "artifact paths. Returns the investigation summary; the persisted session "
    "carries the plan and the full execution trace.",
    {
        "type": "object",
        "properties": {
            "profile": {"type": "string", "description": "Registered profile name."},
            "paths": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Artifact file paths to investigate together.",
            },
            "context_root": {
                "type": "string",
                "description": "Directory the context providers inspect (default '.').",
            },
        },
        "required": ["profile", "paths"],
    },
)
def _run_investigation(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    from veritriage.orchestrator import run_profile

    session = run_profile(
        services,
        str(arguments["profile"]),
        [Path(p) for p in arguments["paths"]],
        context_root=Path(str(arguments.get("context_root", "."))),
    )
    return services.summary(session)


@register_tool(
    "list_profiles",
    "The registered investigation profiles: name, description, and the "
    "ordered steps each one runs.",
    {"type": "object", "properties": {}},
)
def _list_profiles(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    from veritriage.orchestrator import available_profiles

    return [
        {
            "name": name,
            "description": profile.description,
            "steps": [s.id for s in profile.steps],
        }
        for name, profile in sorted(available_profiles().items())
    ]


@register_tool(
    "get_investigation_plan",
    "The immutable investigation plan an orchestrated session ran: steps, "
    "dependencies, and declared artifact flow.",
    _SESSION_ARG,
)
def _get_plan(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    session = _require_session(services, arguments)
    if session.plan is None:
        raise KeyError(f"Session {session.session_id!r} was not produced by the orchestrator")
    return session.plan


@register_tool(
    "get_investigation_trace",
    "The complete execution trace of an orchestrated session: per-step "
    "status, timing, artifact flow, and per-subsystem attribution.",
    _SESSION_ARG,
)
def _get_trace(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    session = _require_session(services, arguments)
    if session.trace is None:
        raise KeyError(f"Session {session.session_id!r} was not produced by the orchestrator")
    return session.trace


@register_tool(
    "resume_investigation",
    "Re-execute only the steps an orchestrated session did not complete, "
    "reusing its analysis; a fully completed session is a no-op.",
    _SESSION_ARG,
)
def _resume_investigation(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    from veritriage.orchestrator import resume_profile

    session = resume_profile(services, str(arguments["session_id"]))
    return {
        "summary": services.summary(session).model_dump(mode="json"),
        "completed": session.trace.completed if session.trace else None,
    }


# --- Collaboration tools (M10) ----------------------------------------------


@register_tool(
    "export_investigation",
    "Export a persisted session as a portable, content-addressed, integrity-"
    "checked investigation bundle file (.vtb) that another engineer can import "
    "without access to the original regression environment.",
    _session_arg_with(
        {
            "path": {"type": "string", "description": "Bundle file to write."},
            "title": {"type": "string", "description": "Optional human title."},
            "exported_by": {"type": "string", "description": "Optional exporter name."},
        },
        required=["path"],
    ),
)
def _export_investigation(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    session = _require_session(services, arguments)
    path = services.export_bundle(
        session,
        Path(str(arguments["path"])),
        exported_by=arguments.get("exported_by"),
        title=arguments.get("title"),
    )
    return {"bundle_path": str(path), "session_id": session.session_id}


@register_tool(
    "import_investigation",
    "Import an investigation bundle file, loading its session into the "
    "workspace so the investigation can continue. Returns the bundle metadata.",
    {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Bundle file to import."}},
        "required": ["path"],
    },
)
def _import_investigation(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    bundle = services.import_bundle(Path(str(arguments["path"])))
    return {"bundle_id": bundle.bundle_id, "session_id": bundle.session.session_id, "metadata": bundle.metadata}


@register_tool(
    "validate_bundle",
    "Validate a bundle file: schema compatibility, integrity fingerprint, and "
    "referential consistency. Deterministic.",
    {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Bundle file to validate."}},
        "required": ["path"],
    },
)
def _validate_bundle(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    result = services.validate_bundle(Path(str(arguments["path"])))
    return {"ok": result.ok, "bundle_id": result.bundle_id, "findings": result.findings}


@register_tool(
    "compare_bundles",
    "Explain what changed between two investigation bundles across evidence, "
    "knowledge, waveform, engineering, recommendations, and execution trace.",
    {
        "type": "object",
        "properties": {
            "bundle_a": {"type": "string", "description": "First bundle file."},
            "bundle_b": {"type": "string", "description": "Second bundle file."},
        },
        "required": ["bundle_a", "bundle_b"],
    },
)
def _compare_bundles(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    return services.compare_bundles(
        Path(str(arguments["bundle_a"])), Path(str(arguments["bundle_b"]))
    )


@register_tool(
    "get_bundle_metadata",
    "The metadata, review status, and validation verdict of a bundle file.",
    {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Bundle file."}},
        "required": ["path"],
    },
)
def _get_bundle_metadata(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    return services.collaboration_view(Path(str(arguments["path"])))


@register_tool(
    "list_reviews",
    "The reviews recorded on a bundle file (verdict, reviewer, comment).",
    {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Bundle file."}},
        "required": ["path"],
    },
)
def _list_reviews(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    return services.collaboration_view(Path(str(arguments["path"])))["reviews"]


@register_tool(
    "list_annotations",
    "The annotations recorded on a bundle file (target, author, text).",
    {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Bundle file."}},
        "required": ["path"],
    },
)
def _list_annotations(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    return services.collaboration_view(Path(str(arguments["path"])))["annotations"]


# --- Project intelligence tools (M11) ---------------------------------------


@register_tool(
    "analyze_project",
    "Build the Verification Project Model for a project root (or *.vproj.json "
    "manifest): DUT hierarchy, interfaces and identified protocols, UVM topology, "
    "simulation lifecycle, and sim infrastructure. Understand the project before "
    "analyzing any failure. Returns the project summary.",
    {
        "type": "object",
        "properties": {
            "root": {"type": "string", "description": "Project root or manifest path."}
        },
        "required": ["root"],
    },
)
def _analyze_project(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    model = services.build_project_model(Path(str(arguments["root"])))
    return services.project_summary(model)


@register_tool(
    "get_project_model",
    "The full Verification Project Model for a root: DUT modules/interfaces/ "
    "protocols, UVM components, expected simulation lifecycle, and sim infra. "
    "Built once and cached; a lens over evidence, never part of the Evidence Graph.",
    {
        "type": "object",
        "properties": {
            "root": {"type": "string", "description": "Project root or manifest path."}
        },
        "required": ["root"],
    },
)
def _get_project_model(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    root = Path(str(arguments["root"]))
    return services.load_project_model(root) or services.build_project_model(root)


@register_tool(
    "get_project_context",
    "The project context attached to an investigation session: identified "
    "protocols, DUT and UVM topology, the run's projection onto the expected "
    "simulation lifecycle, and the origin breakdown of its failing evidence.",
    _SESSION_ARG,
)
def _get_project_context(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    session = _require_session(services, arguments)
    context = services.project_context(session)
    if context is None:
        raise KeyError(f"Session {session.session_id!r} carries no project context")
    return context


@register_tool(
    "explain_log",
    "Log intelligence: classify each line of a log by origin (rtl / testbench / "
    "vip / simulator / infrastructure) and expected lifecycle phase, using the "
    "project's log profile. Runs before failure analysis.",
    {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Log file to classify."},
            "root": {
                "type": "string",
                "description": "Project root for the model used to classify (default '.').",
            },
        },
        "required": ["path"],
    },
)
def _explain_log(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    root = Path(str(arguments.get("root", ".")))
    model = services.load_project_model(root) or services.build_project_model(root)
    model = model if not model.is_empty else None
    return services.explain_log(Path(str(arguments["path"])), model)


# --- Agent Framework tools (M12) --------------------------------------------


@register_tool(
    "get_agent_assessment",
    "The Agent Framework's second opinion on an investigation: which domain "
    "specialists were consulted, the merged findings ranked by confidence with "
    "agreement and conflict made explicit, the union of their recommendations "
    "and stated limitations, and whether the agent layer agrees with the "
    "deterministic reasoning engine. Never replaces the reasoning result.",
    _SESSION_ARG,
)
def _get_agent_assessment(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    session = _require_session(services, arguments)
    assessment = services.agent_assessment(session)
    if assessment is None:
        raise KeyError(f"Session {session.session_id!r} carries no agent assessment")
    return assessment


@register_tool(
    "get_agent_result",
    "One specialist's full assessment of an investigation: its observations "
    "with cited evidence node IDs, its evidence-backed positions with "
    "confidence, its recommendations, and what it could not determine.",
    _session_arg_with(
        {
            "agent_id": {
                "type": "string",
                "description": "Agent ID, e.g. 'protocol', 'rtl', 'testbench', 'formal'.",
            }
        },
        required=["agent_id"],
    ),
)
def _get_agent_result(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    session = _require_session(services, arguments)
    agent_id = str(arguments["agent_id"])
    result = services.agent_result(session, agent_id)
    if result is None:
        raise KeyError(
            f"Session {session.session_id!r} carries no result for agent {agent_id!r}"
        )
    return result


@register_tool(
    "list_agents",
    "The registered domain specialists and the reasoning providers available to "
    "narrate them. Deterministic agents always run; providers are the optional "
    "generative seam and default to none.",
    {"type": "object", "properties": {}},
)
def _list_agents(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    from veritriage.agents import available_agents, available_providers

    return {
        "agents": [
            {"agent_id": agent_id, "domain": agent_cls.domain.value}
            for agent_id, agent_cls in sorted(available_agents().items())
        ],
        "providers": sorted(available_providers()),
    }


# --- Learning Engine tools (M13) --------------------------------------------


@register_tool(
    "learn_from_history",
    "Recompute every learning artifact from the regression database. Learning "
    "is a pure function of recorded history, so this is idempotent: the same "
    "records and feedback always produce the same artifacts.",
    {"type": "object", "properties": {}},
)
def _learn_from_history(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    stats = services.learn_from_history()
    if stats is None:
        raise KeyError("This workspace has no regression database to learn from")
    return stats


@register_tool(
    "learning_statistics",
    "The shape of what the platform has learned: corpus size, feedback count, "
    "artifacts by family, and the registered learners.",
    {"type": "object", "properties": {}},
)
def _learning_statistics(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    stats = services.learning_statistics()
    if stats is None:
        raise KeyError("This workspace has no learning database")
    return stats


@register_tool(
    "recent_patterns",
    "Recurring failure modes and evidence combinations learned from history, "
    "each linked back to the investigations it was learned from. Hints, never "
    "conclusions.",
    {
        "type": "object",
        "properties": {
            "kind": {
                "type": "string",
                "description": "Artifact family filter, e.g. 'investigation_pattern' "
                "or 'evidence_pattern'. Omit for every family.",
            },
            "limit": {"type": "integer", "description": "Maximum artifacts to return."},
        },
    },
)
def _recent_patterns(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    kind = arguments.get("kind")
    limit = int(arguments.get("limit", 20))
    artifacts = services.learning_artifacts(str(kind) if kind else None)
    ranked = sorted(artifacts, key=lambda a: (-a.observations, a.artifact_id))
    return ranked[:limit]


@register_tool(
    "agent_reliability",
    "Each domain specialist's historical track record and the bounded influence "
    "multiplier it has earned. Calibration is applied by the Coordinator at "
    "merge time and never changes what an agent concludes.",
    {"type": "object", "properties": {}},
)
def _agent_reliability(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    return services.agent_reliability()


@register_tool(
    "project_memory",
    "What a project characteristically looks like, learned over its recorded "
    "runs: dominant failure classes, common modules, protocols in play, "
    "recurring signatures, and verification maturity.",
    {
        "type": "object",
        "properties": {
            "project_key": {
                "type": "string",
                "description": "Project ID from a Project Model; omit for the unscoped profile.",
            }
        },
    },
)
def _project_memory(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    key = arguments.get("project_key")
    profile = services.project_memory(str(key) if key else None)
    if profile is None:
        raise KeyError("No project memory has been learned yet")
    return profile


@register_tool(
    "similar_investigations",
    "Historical regressions resembling a session, from the regression database: "
    "exact failure-signature matches first, then similarity ranking, each with "
    "its best known root cause.",
    _session_arg_with(
        {"limit": {"type": "integer", "description": "Maximum results (default 5)."}}
    ),
)
def _similar_investigations(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    session = _require_session(services, arguments)
    return services.similar_regressions(session, limit=int(arguments.get("limit", 5)))


# --- Planning Engine tools (M14) --------------------------------------------


@register_tool(
    "generate_investigation_plan",
    "The structured, branching debug plan for an investigation: ordered steps "
    "with purpose and valuation, decision points, evidence still needed, "
    "completion conditions, and risks. Every step names the artifact it "
    "restates. Advisory only: planning never executes anything.",
    _SESSION_ARG,
)
def _generate_investigation_plan(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    session = _require_session(services, arguments)
    return services.investigation_plan(session) or services.build_investigation_plan(session)


@register_tool(
    "next_debug_step",
    "The single highest-value next action for an investigation, with what it "
    "would tell you, what it costs, and the arithmetic behind its priority.",
    _SESSION_ARG,
)
def _next_debug_step(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    session = _require_session(services, arguments)
    step = services.next_debug_step(session)
    if step is None:
        raise KeyError(f"Session {session.session_id!r} has no outstanding debug steps")
    return step


@register_tool(
    "missing_evidence",
    "What the platform does not have for an investigation, why each item "
    "matters, and which competing explanations it would separate.",
    _SESSION_ARG,
)
def _missing_evidence(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    return services.missing_evidence(_require_session(services, arguments))


@register_tool(
    "decision_tree",
    "The branching points of an investigation plan: the question at each fork, "
    "what each outcome implies, and whether this run's evidence already "
    "settled it.",
    _SESSION_ARG,
)
def _decision_tree(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    return services.decision_tree(_require_session(services, arguments))


@register_tool(
    "investigation_progress",
    "How far along an investigation is: which evidence requests the current "
    "graph satisfies, which remain outstanding, and which questions are still "
    "open. A pure function of the plan and the evidence, with no stored state.",
    _SESSION_ARG,
)
def _investigation_progress(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    return services.plan_progress(_require_session(services, arguments))


@register_tool(
    "project_debug_strategy",
    "The planning strategy for an investigation: the objective, the shape of "
    "the approach adapted to this project's protocols and topology, the "
    "estimated effort, and the risks that could make the plan mislead.",
    _SESSION_ARG,
)
def _project_debug_strategy(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    session = _require_session(services, arguments)
    plan = services.investigation_plan(session) or services.build_investigation_plan(session)
    return {
        "objective": plan.objective,
        "strategy": plan.strategy,
        "confidence_target": plan.confidence_target.value if plan.confidence_target else None,
        "estimated_effort": plan.estimated_effort,
        "risks": plan.risks,
        "historical_success": plan.historical_success,
        "sources": plan.sources,
    }


# --- Design Intelligence tools (M15) ----------------------------------------

_ROOT_ARG = {
    "type": "object",
    "properties": {
        "root": {"type": "string", "description": "Project root or manifest path (default '.')."}
    },
}


def _root(arguments: dict[str, Any]) -> Path:
    return Path(str(arguments.get("root", ".")))


@register_tool(
    "describe_module",
    "One structural element of the design (module, IP, interface, UVM "
    "component) and every typed relationship one hop around it, each naming "
    "the project-model field it was derived from.",
    {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Module, IP, interface, or component name."},
            "root": {"type": "string", "description": "Project root (default '.')."},
        },
        "required": ["name"],
    },
)
def _describe_module(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    found = services.describe_module(str(arguments["name"]), _root(arguments))
    if found is None:
        raise KeyError(f"No design element named {arguments['name']!r}")
    return found


@register_tool(
    "show_hierarchy",
    "The DUT instantiation tree, resolved from the project model's parent "
    "declarations rather than from name matching.",
    {
        "type": "object",
        "properties": {
            "top": {"type": "string", "description": "Root module (defaults to the DUT top)."},
            "root": {"type": "string", "description": "Project root (default '.')."},
        },
    },
)
def _show_hierarchy(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    top = arguments.get("top")
    return services.design_hierarchy(_root(arguments), str(top) if top else None)


@register_tool(
    "trace_dependency",
    "What a structural element depends on and what depends on it, traced "
    "through the Design Graph.",
    {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Element to trace."},
            "root": {"type": "string", "description": "Project root (default '.')."},
        },
        "required": ["name"],
    },
)
def _trace_dependency(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    query = services.design_query(_root(arguments))
    if query is None:
        raise KeyError("This project has no design model to trace")
    name = str(arguments["name"])
    return {
        "name": name,
        "depends_on": [n.name for n in query.dependencies_of(name)],
        "depended_on_by": [n.name for n in query.dependents_of(name)],
    }


@register_tool(
    "find_interface_owner",
    "Which UVM agent owns an interface, and everything observing it. The "
    "question the platform previously answered with substring matching.",
    {
        "type": "object",
        "properties": {
            "interface": {"type": "string", "description": "Interface name."},
            "root": {"type": "string", "description": "Project root (default '.')."},
        },
        "required": ["interface"],
    },
)
def _find_interface_owner(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    query = services.design_query(_root(arguments))
    if query is None:
        raise KeyError("This project has no design model")
    interface = str(arguments["interface"])
    owner = query.owner_of(interface)
    return {
        "interface": interface,
        "owner": owner.qualified_name or owner.name if owner is not None else None,
        "observers": [n.name for n in query.observers_of(interface)],
    }


@register_tool(
    "clock_domain_view",
    "The project's clock domains, which modules live in each, and where two "
    "communicating modules do not share a clock.",
    _ROOT_ARG,
)
def _clock_domain_view(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    query = services.design_query(_root(arguments))
    if query is None:
        raise KeyError("This project has no design model")
    graph = query.graph
    from veritriage.design import DesignRelation, NodeKind

    return {
        "domains": [
            {
                "name": domain.name,
                "modules": sorted(
                    n.name
                    for n in graph.sources(domain.id, DesignRelation.CLOCKED_BY)
                    if n.kind is NodeKind.MODULE
                ),
            }
            for domain in sorted(graph.of_kind(NodeKind.CLOCK_DOMAIN), key=lambda n: n.name)
        ],
        "crossings": [
            {"left": left.name, "right": right.name} for left, right in query.crossings()
        ],
    }


@register_tool(
    "verification_topology",
    "Who watches what: UVM components and VIPs resolved to the interfaces they "
    "monitor, drive, or predict, through the graph rather than by name.",
    _ROOT_ARG,
)
def _verification_topology(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    query = services.design_query(_root(arguments))
    if query is None:
        raise KeyError("This project has no design model")
    graph = query.graph
    from veritriage.design import DesignRelation, NodeKind

    rows = []
    for node in sorted(
        graph.of_kind(NodeKind.UVM_COMPONENT, NodeKind.VIP), key=lambda n: n.name
    ):
        for edge in graph.edges_from(
            node.id,
            DesignRelation.MONITORS,
            DesignRelation.DRIVES,
            DesignRelation.PREDICTS,
        ):
            rows.append(
                {
                    "component": node.qualified_name or node.name,
                    "type": node.attributes.get("type", node.kind.value),
                    "relation": edge.relation.value,
                    "interface": graph.nodes[edge.target_id].name,
                }
            )
    return rows


@register_tool(
    "affected_region",
    "The design neighbourhood around an investigation's failing scopes: the "
    "modules, domains, interfaces, and verification components implicated by "
    "where the evidence pointed.",
    _SESSION_ARG,
)
def _affected_region(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    session = _require_session(services, arguments)
    region = services.affected_design_region(session)
    if not region:
        raise KeyError(
            f"Session {session.session_id!r} carries no design context "
            "(no project model was supplied)"
        )
    return region


@register_tool(
    "protocol_map",
    "Which protocols this project speaks and on which interfaces, resolved "
    "against the Knowledge Packs.",
    _ROOT_ARG,
)
def _protocol_map(services: WorkspaceServices, arguments: dict[str, Any]) -> Any:
    query = services.design_query(_root(arguments))
    if query is None:
        raise KeyError("This project has no design model")
    return query.protocol_map()
