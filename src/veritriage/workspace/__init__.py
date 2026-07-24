"""Verification Workspace (Milestone 8): the platform's public service layer.

The Verification Intelligence Core is architecturally complete; this package
wraps it once, as a deliberate public API, so every client (the CLI, the MCP
server, a future VS Code extension, internal tools) consumes the same
services instead of re-implementing call patterns over the pipeline.

Public surface:

* ``InvestigationSession``: the immutable canonical exchange object (report +
  graph + deterministic identity).
* ``WorkspaceServices``: investigate, persist, summarize, query evidence and
  knowledge, similar history, timeline, search, compare.
* ``navigation``: every report section individually addressable.
* ``search``: deterministic search over evidence and the knowledge base.

Dependencies point outward only: this package imports the core; no core
package may ever import this one (architecture-test enforced).
"""

from veritriage.workspace import navigation
from veritriage.workspace.persistence import (
    DEFAULT_SESSION_ROOT,
    SessionStore,
    SessionSummary,
)
from veritriage.workspace.search import (
    EvidenceHit,
    KnowledgeHit,
    search_evidence,
    search_knowledge,
    search_playbooks,
)
from veritriage.workspace.services import (
    ComparisonView,
    InvestigationSummary,
    WorkspaceServices,
)
from veritriage.workspace.session import (
    InvestigationSession,
    make_session,
    make_session_id,
)

__all__ = [
    "ComparisonView",
    "DEFAULT_SESSION_ROOT",
    "EvidenceHit",
    "InvestigationSession",
    "InvestigationSummary",
    "KnowledgeHit",
    "SessionStore",
    "SessionSummary",
    "WorkspaceServices",
    "make_session",
    "make_session_id",
    "navigation",
    "search_evidence",
    "search_knowledge",
    "search_playbooks",
]
