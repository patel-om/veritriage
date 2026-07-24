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
