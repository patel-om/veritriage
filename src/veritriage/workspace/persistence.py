"""Session persistence: one JSON bundle per investigation.

Sessions live under ``.veritriage/sessions/<id>.json`` by default (beside the
regression database, same convention), so an MCP client can analyze in one
tool call and drill down in later calls by ``session_id`` alone, and a CLI
run and an IDE can hand each other investigations by ID.

Bundles are the session serialized verbatim (report + graph + provenance):
loading one reconstructs the exact object, and re-saving an unchanged session
is byte-identical.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from veritriage.workspace.session import InvestigationSession

#: Default sessions directory, beside the default regression database.
DEFAULT_SESSION_ROOT = Path(".veritriage") / "sessions"


class SessionSummary(BaseModel):
    """One line of ``list_sessions``: enough to pick a session by eye."""

    session_id: str
    created_at: str
    classification: str
    confidence: int
    test_name: str | None = None
    input_files: list[str]


class SessionStore:
    """Saves and loads session bundles under one directory."""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root if root is not None else DEFAULT_SESSION_ROOT

    def path_for(self, session_id: str) -> Path:
        return self.root / f"{session_id}.json"

    def save(self, session: InvestigationSession) -> Path:
        """Persist one session; returns the bundle path written."""
        path = self.path_for(session.session_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(session.model_dump_json(indent=2), encoding="utf-8")
        return path

    def load(self, session_id: str) -> InvestigationSession | None:
        """Load a session by ID; None when no bundle exists."""
        path = self.path_for(session_id)
        if not path.is_file():
            return None
        return InvestigationSession.model_validate_json(
            path.read_text(encoding="utf-8")
        )

    def list_sessions(self) -> list[SessionSummary]:
        """Summaries of every stored session, newest first, ties by ID."""
        summaries: list[SessionSummary] = []
        if not self.root.is_dir():
            return summaries
        for path in sorted(self.root.glob("ses-*.json")):
            session = InvestigationSession.model_validate_json(
                path.read_text(encoding="utf-8")
            )
            summaries.append(
                SessionSummary(
                    session_id=session.session_id,
                    created_at=session.created_at.isoformat(),
                    classification=session.report.classification.category.value,
                    confidence=session.report.classification.confidence,
                    test_name=session.report.summary.test_name,
                    input_files=list(session.input_files),
                )
            )
        summaries.sort(key=lambda s: (s.created_at, s.session_id), reverse=True)
        return summaries
