"""The Investigation Session: the canonical object every client exchanges.

A session is one complete investigation, frozen: the analysis report (which
already aggregates classification, reasoning, knowledge, waveform
observations, engineering context, and historical matches) plus the full
Evidence Graph, under a deterministic identity. Clients navigate and project
sessions; nothing mutates one after creation
(``test_sessions_are_immutable`` pins it).

Identity is content-derived: the same investigation of the same artifacts is
the same session, byte for byte, while ``created_at`` stays a separate
provenance field so identity never depends on wall-clock time.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

import veritriage
from veritriage.graph.graph import EvidenceGraph
from veritriage.models import AnalysisReport, InvestigationPlan, InvestigationTrace


def make_session_id(report: AnalysisReport, graph: EvidenceGraph) -> str:
    """Deterministic session ID from the investigation's content.

    Hashes the sorted evidence node IDs (themselves content-derived), the
    classification, and the input file names: everything that identifies
    *what was investigated and what was concluded*, nothing that varies
    between identical runs.
    """
    parts = [
        *sorted(graph.nodes),
        report.classification.category.value,
        *sorted(Path(f).name for f in report.input_files),
    ]
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()
    return f"ses-{digest[:12]}"


class InvestigationSession(BaseModel):
    """One complete, immutable investigation.

    References everything a client needs: the evidence (graph), and via the
    report every intelligence layer's conclusions plus the generated-report
    content. The session adds identity and provenance; it invents no data.
    """

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(description="Deterministic content-derived ID (see make_session_id).")
    created_at: datetime
    input_files: tuple[str, ...] = Field(description="Artifact paths as given at analysis time.")
    veritriage_version: str = Field(description="Platform version that produced this session.")
    report: AnalysisReport
    graph: EvidenceGraph
    plan: InvestigationPlan | None = Field(
        default=None,
        description="The investigation plan that produced this session, when orchestrated. "
        "Attached via model_copy (a new session object); never part of identity.",
    )
    trace: InvestigationTrace | None = Field(
        default=None,
        description="The execution trace of the orchestrated run, when orchestrated. "
        "Workflow bookkeeping only; session_id never depends on it.",
    )


def make_session(
    report: AnalysisReport,
    graph: EvidenceGraph,
    now: datetime | None = None,
) -> InvestigationSession:
    """Wrap one completed analysis into an immutable session."""
    return InvestigationSession(
        session_id=make_session_id(report, graph),
        created_at=now or datetime.now(timezone.utc),
        input_files=tuple(report.input_files),
        veritriage_version=veritriage.__version__,
        report=report,
        graph=graph,
    )
