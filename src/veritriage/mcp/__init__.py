"""VeriTriage MCP server (Milestone 8).

Exposes the platform as a collection of investigation tools over the Model
Context Protocol, so AI development environments (Claude Code, Cursor, VS
Code hosts, ChatGPT connectors) can query VeriTriage without embedding it.

The tool table (``tools.py``) is transport-agnostic and routes everything
through :class:`~veritriage.workspace.WorkspaceServices`; ``server.py`` is
one thin stdio transport over it. Serve with ``veritriage mcp``.
"""

from veritriage.mcp.server import McpStdioServer
from veritriage.mcp.tools import (
    ToolSpec,
    call_tool,
    list_tools,
    register_tool,
    unregister_tool,
)

__all__ = [
    "McpStdioServer",
    "ToolSpec",
    "call_tool",
    "list_tools",
    "register_tool",
    "unregister_tool",
]
