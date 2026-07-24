"""WorkspaceServices: the stable public API every client consumes.

The CLI and every MCP tool call these methods and nothing else, so
investigation logic exists exactly once and "adding a client" never means
"re-implementing the platform". Everything here is deterministic and AI-free;
the optional AI review stays outside the workspace entirely.

Return types are exclusively normalized models (from ``veritriage.models``,
the graph package, and the workspace's own API models): no ``ParseResult``,
parser, adapter, or provider object ever crosses this API
(``test_public_api_never_exposes_raw_parser_objects`` pins it). Raw artifact
paths go in; normalized objects come out.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from pydantic import BaseModel, Field

from veritriage.engineering import EngineeringContext
from veritriage.engineering.timeline import build_timeline
from veritriage.graph.model import ArtifactType, EvidenceNode
from veritriage.models import (
    EngineeringContextView,
    MatchedPattern,
    SimilarFailure,
    TimelineEventView,
    WaveformObservationView,
)
from veritriage.pipeline import analyze
from veritriage.workspace.persistence import SessionStore, SessionSummary
from veritriage.workspace.search import (
    EvidenceHit,
    KnowledgeHit,
    search_evidence,
    search_knowledge,
)
from veritriage.workspace.session import InvestigationSession, make_session


class InvestigationSummary(BaseModel):
    """One bounded summary of a session: the elevator answer."""

    session_id: str
    created_at: str
    input_files: list[str]
    classification: str
    confidence: int
    top_hypothesis: str | None = None
    top_hypothesis_id: str | None = None
    top_hypothesis_confidence: float | None = None
    evidence_nodes: int
    matched_patterns: list[str] = Field(default_factory=list)
    waveform_observations: int = 0
    engineering_commits: int = 0
    seen_before: bool | None = None
    recommendations: int = 0


class ComparisonView(BaseModel):
    """A deterministic comparison of two investigations."""

    session_a: str
    session_b: str
    same_signature: bool
    classification_a: str
    classification_b: str
    shared_failing_descriptions: list[str] = Field(default_factory=list)
    only_in_a: int = 0
    only_in_b: int = 0


class WorkspaceServices:
    """The platform's public service layer. One instance per workspace."""

    def __init__(self, session_root: Path | None = None, db: Path | None = None) -> None:
        self._store = SessionStore(session_root)
        self._db = db

    # --- Investigations ----------------------------------------------------

    def investigate(
        self,
        paths: Sequence[Path],
        engineering: EngineeringContext | None = None,
        parser_name: str | None = None,
        record_history: bool = False,
        now: datetime | None = None,
    ) -> InvestigationSession:
        """Run one full analysis and wrap it into an immutable session.

        With ``record_history`` (and a workspace database), the run is
        recorded in the regression database and the report is augmented with
        historical context *before* the session is created, so the session
        stays immutable from birth. Recording is off by default: MCP and
        library callers get a read-only posture unless they opt in.
        """
        outcome = analyze(list(paths), parser_name=parser_name, engineering=engineering)
        if record_history and self._db is not None:
            from veritriage.history import HistoryEngine, capture_execution_metadata
            from veritriage.storage import RegressionStore

            with RegressionStore(self._db) as store:
                engine = HistoryEngine(store)
                _, context = engine.record(
                    outcome, execution=capture_execution_metadata()
                )
                engine.augment(outcome, context)
        return make_session(outcome.report, outcome.graph, now=now)

    def save(self, session: InvestigationSession) -> Path:
        return self._store.save(session)

    def load(self, session_id: str) -> InvestigationSession | None:
        return self._store.load(session_id)

    def list_sessions(self) -> list[SessionSummary]:
        return self._store.list_sessions()

    def summary(self, session: InvestigationSession) -> InvestigationSummary:
        """The bounded answer to "what did this investigation conclude?"."""
        report = session.report
        top = (
            report.reasoning.hypotheses[0]
            if report.reasoning and report.reasoning.hypotheses
            else None
        )
        return InvestigationSummary(
            session_id=session.session_id,
            created_at=session.created_at.isoformat(),
            input_files=list(session.input_files),
            classification=report.classification.category.value,
            confidence=report.classification.confidence,
            top_hypothesis=top.title if top else None,
            top_hypothesis_id=top.id if top else None,
            top_hypothesis_confidence=round(top.confidence, 4) if top else None,
            evidence_nodes=report.graph_stats.node_count,
            matched_patterns=(
                [p.pattern_id for p in report.knowledge.patterns] if report.knowledge else []
            ),
            waveform_observations=(
                len(report.waveform.observations) if report.waveform else 0
            ),
            engineering_commits=(
                len(report.engineering.commits) if report.engineering else 0
            ),
            seen_before=report.history.seen_before if report.history else None,
            recommendations=(
                len(report.reasoning.recommendations) if report.reasoning else 0
            ),
        )

    # --- Evidence queries --------------------------------------------------

    def evidence(
        self,
        session: InvestigationSession,
        artifact_type: str | None = None,
        failing_only: bool = False,
    ) -> list[EvidenceNode]:
        """Evidence nodes, optionally filtered by type and failure status."""
        nodes = list(session.graph.nodes.values())
        if artifact_type is not None:
            wanted = ArtifactType(artifact_type)
            nodes = [n for n in nodes if n.artifact_type == wanted]
        if failing_only:
            nodes = [n for n in nodes if n.is_failing]
        return nodes

    def evidence_graph_view(
        self, session: InvestigationSession, max_nodes: int = 60
    ) -> dict:
        """The bounded, normalized graph projection (the same view AI gets)."""
        return session.graph.to_reasoning_view(max_nodes=max_nodes)

    def search(self, session: InvestigationSession, query: str) -> list[EvidenceHit]:
        return search_evidence(session, query)

    # --- Knowledge queries -------------------------------------------------

    def search_knowledge(self, query: str) -> list[KnowledgeHit]:
        return search_knowledge(query)

    def matched_patterns(self, session: InvestigationSession) -> list[MatchedPattern]:
        return list(session.report.knowledge.patterns) if session.report.knowledge else []

    # --- Layer views ---------------------------------------------------------

    def waveform_observations(
        self, session: InvestigationSession
    ) -> list[WaveformObservationView]:
        return list(session.report.waveform.observations) if session.report.waveform else []

    def engineering_context(
        self, session: InvestigationSession
    ) -> EngineeringContextView | None:
        return session.report.engineering

    def timeline(self, session: InvestigationSession) -> list[TimelineEventView]:
        """The investigation timeline; built from the graph when the report
        carries no engineering section (timeline works without context)."""
        if session.report.engineering is not None:
            return list(session.report.engineering.timeline)
        return build_timeline(session.graph, session.report)

    # --- History -------------------------------------------------------------

    def similar_regressions(
        self, session: InvestigationSession, limit: int = 5
    ) -> list[SimilarFailure]:
        """Historical regressions resembling this session, from the database.

        Read-only: the session is compared against history without being
        recorded (recording stays a CLI decision, as it has been since M4).
        Returns [] when the workspace has no database.
        """
        if self._db is None or not Path(self._db).is_file():
            return []
        from veritriage.history.record import RegressionRecord, extract_run_context
        from veritriage.signatures import build_signature
        from veritriage.similarity import SimilarFailureEngine
        from veritriage.storage import RegressionStore

        report, graph = session.report, session.graph
        signature = build_signature(report, graph)
        test_name, seed, configuration = extract_run_context(graph)
        probe = RegressionRecord(
            regression_id=f"probe-{session.session_id}",
            created_at=session.created_at or datetime.now(timezone.utc),
            test_name=test_name or report.summary.test_name,
            seed=seed,
            configuration=configuration,
            signature=signature,
            report=report,
            graph=graph,
        )
        with RegressionStore(self._db) as store:
            engine = SimilarFailureEngine(store)
            probe.embedding = engine.provider.embed(probe)
            return engine.find_similar(probe, top_k=limit)

    # --- Comparison ----------------------------------------------------------

    def compare(
        self, a: InvestigationSession, b: InvestigationSession
    ) -> ComparisonView:
        """Deterministic diff of two investigations: signature, class, evidence."""
        from veritriage.signatures import build_signature

        sig_a = build_signature(a.report, a.graph)
        sig_b = build_signature(b.report, b.graph)
        failing_a = {n.description for n in a.graph.failing()}
        failing_b = {n.description for n in b.graph.failing()}
        return ComparisonView(
            session_a=a.session_id,
            session_b=b.session_id,
            same_signature=sig_a.digest == sig_b.digest,
            classification_a=a.report.classification.category.value,
            classification_b=b.report.classification.category.value,
            shared_failing_descriptions=sorted(failing_a & failing_b),
            only_in_a=len(failing_a - failing_b),
            only_in_b=len(failing_b - failing_a),
        )
