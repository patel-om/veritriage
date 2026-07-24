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
