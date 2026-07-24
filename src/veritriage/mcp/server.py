"""Minimal MCP stdio transport: a JSON-RPC 2.0 loop over the tool table.

Implements the Model Context Protocol subset a host needs to use VeriTriage
as a tool server: ``initialize``, the ``notifications/initialized``
notification, ``ping``, ``tools/list``, and ``tools/call``, speaking
newline-delimited JSON-RPC over stdin/stdout.

Deliberately dependency-free: the subset is small, deterministic, and fully
testable in-process with fake streams. All investigation behavior lives in
the transport-agnostic tool table (``tools.py``); this file only moves JSON.
A future official-SDK or HTTP hosting is another thin file over the same
table.
"""

from __future__ import annotations

import json
import sys
from typing import Any, TextIO

import veritriage
from veritriage.mcp.tools import call_tool, list_tools
from veritriage.workspace import WorkspaceServices

#: The MCP protocol revision this transport implements the subset of.
PROTOCOL_VERSION = "2024-11-05"

#: JSON-RPC error codes (per spec).
_METHOD_NOT_FOUND = -32601
_INVALID_PARAMS = -32602
_INTERNAL_ERROR = -32603
_PARSE_ERROR = -32700


class McpStdioServer:
    """Serves the VeriTriage tool table over newline-delimited JSON-RPC."""

    def __init__(
        self,
        services: WorkspaceServices,
        in_stream: TextIO | None = None,
        out_stream: TextIO | None = None,
    ) -> None:
        self._services = services
        self._in = in_stream if in_stream is not None else sys.stdin
        self._out = out_stream if out_stream is not None else sys.stdout

    def serve_forever(self) -> None:
        """Read requests until EOF; one JSON-RPC message per line."""
        for line in self._in:
            line = line.strip()
            if not line:
                continue
            response = self.handle_line(line)
            if response is not None:
                self._out.write(json.dumps(response) + "\n")
                self._out.flush()

    def handle_line(self, line: str) -> dict[str, Any] | None:
        """Handle one raw message; None for notifications (no response due)."""
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            return _error(None, _PARSE_ERROR, f"parse error: {exc}")
        if not isinstance(message, dict):
            return _error(None, _PARSE_ERROR, "expected a JSON-RPC object")
        return self.handle_message(message)

    def handle_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """Dispatch one parsed JSON-RPC message."""
        method = message.get("method")
        msg_id = message.get("id")
        params = message.get("params") or {}

        if method == "notifications/initialized":
            return None  # notification: acknowledged silently
        if msg_id is None:
            return None  # unknown notification: ignore per JSON-RPC

        if method == "initialize":
            return _result(
                msg_id,
                {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "veritriage",
                        "version": veritriage.__version__,
                    },
                },
            )
        if method == "ping":
            return _result(msg_id, {})
        if method == "tools/list":
            return _result(
                msg_id,
                {
                    "tools": [
                        {
                            "name": spec.name,
                            "description": spec.description,
                            "inputSchema": spec.input_schema,
                        }
                        for spec in list_tools()
                    ]
                },
            )
        if method == "tools/call":
            return self._handle_tool_call(msg_id, params)
        return _error(msg_id, _METHOD_NOT_FOUND, f"method not found: {method}")

    def _handle_tool_call(self, msg_id: Any, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        if not isinstance(name, str):
            return _error(msg_id, _INVALID_PARAMS, "tools/call requires a tool 'name'")
        arguments = params.get("arguments") or {}
        try:
            result = call_tool(self._services, name, arguments)
        except KeyError as exc:
            return _result(msg_id, _tool_error(str(exc.args[0]) if exc.args else str(exc)))
        except Exception as exc:  # noqa: BLE001 - surfaced to the host, never crashes the loop
            return _result(msg_id, _tool_error(f"{type(exc).__name__}: {exc}"))
        return _result(
            msg_id,
            {
                "content": [{"type": "text", "text": json.dumps(result, indent=2)}],
                "isError": False,
            },
        )


def _result(msg_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "result": result}


def _error(msg_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _tool_error(message: str) -> dict[str, Any]:
    """Tool-level failures are results with isError, per MCP, so the host can
    show them to the model rather than treating the server as broken."""
    return {"content": [{"type": "text", "text": message}], "isError": True}
