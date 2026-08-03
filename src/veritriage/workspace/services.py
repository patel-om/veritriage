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
from typing import TYPE_CHECKING, Sequence

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from veritriage.models import (
        AgentAssessment,
        AgentReliability,
        AgentResult,
        LearningArtifact,
        LearningContext,
        LearningStatistics,
        LogAnnotationView,
        ProjectContext,
        ProjectProfile,
        ProjectSummary,
    )
    from veritriage.project import ProjectModel

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

    def __init__(
        self,
        session_root: Path | None = None,
        db: Path | None = None,
        project_root: Path | None = None,
        learning_db: Path | None = None,
    ) -> None:
        from veritriage.project import ProjectStore

        self._store = SessionStore(session_root)
        self._db = db
        self._project_store = ProjectStore(project_root)
        # The learning store defaults beside the regression database. It is a
        # derived, rebuildable view: deleting it returns the platform to exact
        # pre-M13 behavior, which is why it is a separate file.
        self._learning_db = learning_db or (
            Path(db).parent / "learning.db" if db is not None else None
        )

    # --- Investigations ----------------------------------------------------

    def gather_engineering_context(
        self, root: Path, max_commits: int = 10
    ) -> EngineeringContext | None:
        """Collect engineering context from every provider available at a root.

        The workspace-level wrapper over the provider registry (added in M9
        so orchestration steps and MCP tools gather context through services
        like everything else). Returns None when nothing contributed, so
        callers can pass the result straight to :meth:`investigate`.
        """
        from veritriage.engineering import collect_context

        gathered = collect_context(root, max_commits=max_commits)
        return None if gathered.is_empty else gathered

    def render_report(
        self,
        session: InvestigationSession,
        output_dir: Path,
        metrics: dict | None = None,
    ) -> Path:
        """Write the session's analysis.json, evidence_graph.json, and
        report.html to a directory; returns the report path.

        ``metrics`` is optional plain data (an orchestration trace's step
        timings) rendered as an "Investigation performance" report section;
        without it the output is byte-identical to pre-M9 reports.
        """
        from veritriage.reports import HtmlReportGenerator
        from veritriage.utils import write_json

        write_json(session.report, output_dir / "analysis.json")
        write_json(session.graph, output_dir / "evidence_graph.json")
        return HtmlReportGenerator().write(
            session.report,
            output_dir / "report.html",
            graph=session.graph,
            metrics=metrics,
        )

    def investigate(
        self,
        paths: Sequence[Path],
        engineering: EngineeringContext | None = None,
        parser_name: str | None = None,
        record_history: bool = False,
        now: datetime | None = None,
        project: "ProjectModel | None" = None,
        agents: bool = True,
        learn: bool = True,
    ) -> InvestigationSession:
        """Run one full analysis and wrap it into an immutable session.

        With ``record_history`` (and a workspace database), the run is
        recorded in the regression database and the report is augmented with
        historical context *before* the session is created, so the session
        stays immutable from birth. Recording is off by default: MCP and
        library callers get a read-only posture unless they opt in.
        """
        # Recall runs before the analysis, so agents receive memory and the
        # Coordinator receives calibration. Nothing here can alter a
        # deterministic conclusion: recall only supplies context.
        recalled = (
            self.recall_learning(project.project_id if project is not None else None)
            if learn
            else None
        )
        outcome = analyze(
            list(paths),
            parser_name=parser_name,
            engineering=engineering,
            project=project,
            agents=agents,
            learning=recalled,
        )
        if record_history and self._db is not None:
            from veritriage.history import HistoryEngine, capture_execution_metadata
            from veritriage.storage import RegressionStore

            with RegressionStore(self._db) as store:
                engine = HistoryEngine(store)
                _, context = engine.record(
                    outcome, execution=capture_execution_metadata()
                )
                engine.augment(outcome, context)
            # The signature-specific half of recall, once the run has one.
            # Mirrors HistoryEngine.record/augment, and like it, appends only.
            if learn and recalled is not None:
                self._augment_learning(outcome.report, context.signature)
        return make_session(outcome.report, outcome.graph, now=now)

    # --- Project intelligence (M11) ----------------------------------------
    #
    # The Project Model is built from the provider registry, cached, and reused
    # by investigations. Like collect_context it is gathered here (a workspace
    # decision), not inside the pure pipeline, and it never enters the graph.

    def build_project_model(self, root: Path) -> "ProjectModel":
        """Build and cache the Project Model for a source root."""
        from veritriage.project import build_project_model

        model = build_project_model(root)
        if not model.is_empty:
            self._project_store.save(model)
        return model

    def load_project_model(self, root: Path) -> "ProjectModel | None":
        """The cached model for a root (None if never built)."""
        return self._project_store.load_for_root(root)

    def project_summary(self, model: "ProjectModel") -> "ProjectSummary":
        """The bounded 'what is this project?' answer."""
        from veritriage.models import ProjectSummary

        return ProjectSummary(
            project_id=model.project_id,
            source_root=model.source_root,
            built_at=model.built_at.isoformat(),
            dut_top=model.dut.top,
            simulator=model.sim_infra.simulator_vendor,
            module_count=len(model.dut.modules),
            interface_count=len(model.dut.interfaces),
            identified_protocols=sorted(
                {i.protocol_id for i in model.dut.interfaces if i.protocol_id}
            ),
            uvm_component_count=len(model.env.components),
            lifecycle_phase_count=len(model.lifecycle.phases),
        )

    def project_context(self, session: InvestigationSession) -> "ProjectContext | None":
        """The project context attached to a session's report, if any."""
        return session.report.project

    def explain_log(
        self, path: Path, model: "ProjectModel | None" = None
    ) -> "list[LogAnnotationView]":
        """Classify a log's lines by origin and lifecycle phase (log intelligence)."""
        from veritriage.project import explain_log

        return explain_log(path, model)

    # --- Agent Framework (M12) ---------------------------------------------
    #
    # Read-only accessors over what the Coordinator already attached to the
    # report. Agents run inside the analysis, so there is nothing to trigger
    # here: these exist so a client never has to reach into report internals.

    def agent_assessment(self, session: InvestigationSession) -> "AgentAssessment | None":
        """The agent layer's second opinion on a session, if agents ran."""
        return session.report.agents

    def agent_result(
        self, session: InvestigationSession, agent_id: str
    ) -> "AgentResult | None":
        """One specialist's full assessment: observations, position, limits."""
        assessment = session.report.agents
        if assessment is None:
            return None
        return next((r for r in assessment.results if r.agent_id == agent_id), None)

    # --- Learning Engine (M13) ---------------------------------------------
    #
    # The workspace owns the learning store the way it owns the project store
    # and the regression database: the pipeline never opens one, so analyze()
    # stays a pure function. Every method degrades to nothing (None, empty
    # list) when no learning database is configured, so the platform behaves
    # exactly as it did before M13.

    def _learning_engine(self):
        """Open a Learning Engine over the workspace's learning store, or None."""
        if self._learning_db is None:
            return None
        from veritriage.learning import LearningEngine, LearningStore

        return LearningEngine(LearningStore(self._learning_db))

    def learn_from_history(self) -> "LearningStatistics | None":
        """Recompute every learning artifact from the regression database.

        The normal path, not a fallback: learning is a pure function of
        recorded history, so a full rebuild is both cheap to reason about and
        the only way a corrected feedback record can fix everything it touches.
        """
        if self._db is None or not Path(self._db).is_file():
            return None
        engine = self._learning_engine()
        if engine is None:
            return None
        from veritriage.storage import RegressionStore

        with RegressionStore(self._db) as store:
            return engine.observe(store.all_records(), store.all_feedback())

    def recall_learning(self, project_key: str | None = None) -> "LearningContext | None":
        """What history suggests for an upcoming investigation."""
        engine = self._learning_engine()
        if engine is None:
            return None
        recalled = engine.recall(project_key)
        return None if recalled.is_empty else recalled

    def _augment_learning(self, report, signature_digest: str) -> None:
        engine = self._learning_engine()
        if engine is not None:
            engine.augment(report, signature_digest)

    def learning_statistics(self) -> "LearningStatistics | None":
        """The shape of what the platform has learned so far."""
        engine = self._learning_engine()
        return engine.statistics() if engine is not None else None

    def learning_artifacts(self, kind: str | None = None) -> "list[LearningArtifact]":
        """Stored learning artifacts, optionally filtered to one family."""
        engine = self._learning_engine()
        return list(engine.artifacts(kind)) if engine is not None else []

    def agent_reliability(self) -> "list[AgentReliability]":
        """Each specialist's track record and the calibration it has earned."""
        from veritriage.models import AgentReliability as _AgentReliability

        return [
            a
            for a in self.learning_artifacts("agent_reliability")
            if isinstance(a, _AgentReliability)
        ]

    def project_memory(self, project_key: str | None = None) -> "ProjectProfile | None":
        """What a project characteristically looks like, learned over its runs."""
        engine = self._learning_engine()
        if engine is None:
            return None
        return engine.recall(project_key).project_profile

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

    # --- Bundles and collaboration (M10) -----------------------------------
    #
    # Bundle operations delegate to the collab package through lazy imports,
    # so WorkspaceServices stays the single public boundary (clients never
    # import collab) with no import-time coupling: exactly how this class
    # already reaches storage, history, and reports.

    def export_bundle(
        self,
        session: InvestigationSession,
        path: Path,
        exported_by: str | None = None,
        title: str | None = None,
        compress: bool = True,
    ) -> Path:
        """Export a session as a portable, sealed investigation bundle file."""
        from veritriage.collab import export_bundle, make_bundle

        bundle = make_bundle(session, exported_by=exported_by, title=title)
        return export_bundle(bundle, path, compress=compress)

    def import_bundle(self, path: Path, save_session: bool = True):
        """Import a bundle file; optionally persist its session so the
        investigation can continue. Returns the bundle."""
        from veritriage.collab import import_bundle

        bundle = import_bundle(path)
        if save_session:
            self._store.save(bundle.session)
        return bundle

    def validate_bundle(self, path: Path):
        """Validate a bundle file; returns a deterministic ValidationResult."""
        from veritriage.collab import import_bundle, validate_bundle

        return validate_bundle(import_bundle(path))

    def review_bundle(
        self, path: Path, verdict: str, reviewer: str, comment: str = ""
    ) -> Path:
        """Append a review to a bundle file in place; returns the path."""
        from veritriage.collab import add_review, export_bundle, import_bundle

        reviewed = add_review(import_bundle(path), verdict, reviewer, comment)
        return export_bundle(reviewed, path)

    def annotate_bundle(
        self, path: Path, target_type: str, target_id: str, author: str, text: str
    ) -> Path:
        """Append an annotation to a bundle file in place; returns the path."""
        from veritriage.collab import add_annotation, export_bundle, import_bundle

        annotated = add_annotation(import_bundle(path), target_type, target_id, author, text)
        return export_bundle(annotated, path)

    def compare_bundles(self, a: Path, b: Path):
        """Explain what changed between two bundle files."""
        from veritriage.collab import compare_bundles, import_bundle

        return compare_bundles(import_bundle(a), import_bundle(b))

    def collaboration_view(self, path: Path) -> dict:
        """Plain collaboration data for the report's Collaboration section.

        Presentation only: built here so the reports package stays ignorant
        of bundle internals.
        """
        from veritriage.collab import import_bundle, review_status, validate_bundle

        bundle = import_bundle(path)
        result = validate_bundle(bundle)
        return {
            "bundle_id": bundle.bundle_id,
            "fingerprint": bundle.metadata.fingerprint,
            "title": bundle.metadata.title,
            "exported_by": bundle.metadata.exported_by,
            "review_status": review_status(bundle),
            "reviews": [
                {"verdict": r.verdict.value, "reviewer": r.reviewer, "comment": r.comment}
                for r in bundle.reviews
            ],
            "annotations": [
                {"target": f"{a.target_type}:{a.target_id}", "author": a.author, "text": a.text}
                for a in bundle.annotations
            ],
            "validation_ok": result.ok,
            "validation_findings": [
                {"severity": f.severity.value, "message": f.message} for f in result.findings
            ],
        }

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
