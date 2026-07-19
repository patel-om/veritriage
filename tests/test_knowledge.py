"""Verification Knowledge Engine tests.

Covers the milestone's architecture guarantees: knowledge is deterministic,
AI-free, immutable during reasoning, pluggable without touching reasoning
code, and its playbooks/matches are reproducible.
"""

from __future__ import annotations

from pathlib import Path

from veritriage.knowledge import (
    Concept,
    DebugPlaybook,
    EvidenceClause,
    FailurePattern,
    KnowledgeEngine,
    KnowledgeGraph,
    KnowledgePack,
    PlaybookStep,
    load_packs,
    match_patterns,
    register_pack,
    unregister_pack,
)
from veritriage.pipeline import analyze
from veritriage.reasoning import ReasoningEngine

SRC = Path(__file__).parent.parent / "src" / "veritriage"


# --- Schema and packs ------------------------------------------------------


def test_builtin_packs_load_and_are_versioned():
    packs = load_packs()
    ids = {p.id for p in packs}
    assert {"axi", "uvm", "reset-clocking", "coverage"} <= ids
    for pack in packs:
        assert pack.version
        assert pack.domain
        # Every pattern's playbook reference resolves within its pack set.
        playbook_ids = {b.id for p in packs for b in p.playbooks}
        for pattern in pack.patterns:
            if pattern.playbook_id:
                assert pattern.playbook_id in playbook_ids


def test_knowledge_serializes_round_trip():
    for pack in load_packs():
        restored = KnowledgePack.model_validate_json(pack.model_dump_json())
        assert restored == pack


def test_custom_pack_plugs_in_without_touching_reasoning(fixture_log):
    @register_pack
    def _custom() -> KnowledgePack:
        return KnowledgePack(
            id="custom-test-pack",
            name="Custom",
            version="0.1.0",
            domain="test",
            summary="test pack",
            patterns=[
                FailurePattern(
                    id="custom.scoreboard",
                    name="Custom scoreboard pattern",
                    summary="test pattern",
                    required=[
                        EvidenceClause(name="mismatch", pattern=r"mismatch", must_fail=True)
                    ],
                    typical_causes=["test"],
                    ownership="testbench",
                    playbook_id="custom.pb",
                    confidence_modifiers={"testbench_issue": 0.05},
                )
            ],
            playbooks=[
                DebugPlaybook(
                    id="custom.pb", name="pb", steps=[PlaybookStep(action="do the thing")]
                )
            ],
        )

    try:
        outcome = analyze(fixture_log("uvm_scoreboard.log"))
        assert outcome.report.knowledge is not None
        matched = {p.pattern_id for p in outcome.report.knowledge.patterns}
        assert "custom.scoreboard" in matched
        signal_names = {s.name for s in outcome.report.reasoning.signals}
        assert "knowledge:custom.scoreboard" in signal_names
    finally:
        unregister_pack("custom-test-pack")


# --- The knowledge graph ---------------------------------------------------


def test_knowledge_graph_queries():
    kg = KnowledgeGraph.build()
    assert kg.expected_sequence("axi.read-lifecycle") == [
        "Address issued",
        "Address accepted",
        "Outstanding",
        "Response",
        "Complete",
    ]
    resolved = kg.playbook_for("axi.no-response-after-accept")
    assert resolved is not None
    pack, playbook = resolved
    assert pack.id == "axi"
    assert playbook.id == "axi.read-timeout"
    assert kg.pack_versions()["axi"] == "1.0.0"


def test_knowledge_graph_immutable_during_reasoning(fixture_log):
    kg = KnowledgeGraph.build()
    before = kg.fingerprint()
    outcome = analyze(fixture_log("axi_timeout.log"))
    assert outcome.report.knowledge is not None
    assert kg.fingerprint() == before
    # The graph model itself is frozen: assignment must fail.
    try:
        kg.packs = {}
        raise AssertionError("KnowledgeGraph should be frozen")
    except Exception:
        pass


# --- Deterministic matching ------------------------------------------------


def test_pattern_matching_is_deterministic(fixture_log):
    kg = KnowledgeGraph.build()
    graph = analyze(fixture_log("axi_timeout.log")).graph
    a = match_patterns(kg, graph)
    b = match_patterns(kg, graph)
    assert [(m.pattern.id, m.score, m.matched_evidence) for m in a] == [
        (m.pattern.id, m.score, m.matched_evidence) for m in b
    ]


def test_axi_timeout_matches_no_response_pattern(fixture_log):
    outcome = analyze(fixture_log("axi_timeout.log"))
    k = outcome.report.knowledge
    assert k is not None
    top = k.patterns[0]
    assert top.pattern_id == "axi.no-response-after-accept"
    assert top.score == 1.0
    assert top.ownership.startswith("design")
    assert "ARVALID" in top.suggested_signals
    assert any(r.source.startswith("AMBA AXI") for r in top.references)
    # Every cited node exists in the evidence graph.
    for ids in top.matched_evidence.values():
        assert all(i in outcome.graph.nodes for i in ids)


def test_forbidden_clause_blocks_pattern(fixture_log):
    # An assertion fired in this run, so the timeout/no-response pattern
    # (which forbids assertion evidence) must not match.
    outcome = analyze(fixture_log("uvm_assertion.log"))
    k = outcome.report.knowledge
    matched = {p.pattern_id for p in k.patterns}
    assert "axi.no-response-after-accept" not in matched
    assert "uvm.scoreboard-mismatch-after-protocol-success" not in matched
    assert "axi.valid-drop-before-ready" in matched


def test_state_projection_shows_where_progress_stopped(fixture_log):
    outcome = analyze(fixture_log("axi_timeout.log"))
    sp = outcome.report.knowledge.state_projection
    assert sp is not None
    assert sp.machine_id == "axi.read-lifecycle"
    reached = [s.state for s in sp.states if s.reached]
    assert reached == ["Address issued", "Address accepted", "Outstanding"]
    assert sp.stopped_at == "Response"


def test_playbooks_are_reproducible(fixture_log):
    runs = [analyze(fixture_log("axi_timeout.log")) for _ in range(2)]
    playbooks = [r.report.knowledge.patterns[0].playbook for r in runs]
    assert playbooks[0] == playbooks[1]
    steps = playbooks[0].steps
    assert [s.order for s in steps] == list(range(1, len(steps) + 1))
    assert steps[0].action.startswith("Check ARVALID")


def test_clean_run_has_no_knowledge_section(fixture_log):
    outcome = analyze(fixture_log("uvm_pass.log"))
    assert outcome.report.knowledge is None


# --- Knowledge feeds reasoning as evidence ---------------------------------


def test_knowledge_signal_influences_ranking_with_trace(fixture_log):
    outcome = analyze(fixture_log("axi_timeout.log"))
    reasoning = outcome.report.reasoning
    knowledge_signals = [s for s in reasoning.signals if s.name.startswith("knowledge:")]
    assert knowledge_signals, "expected knowledge-derived signals"
    for signal in knowledge_signals:
        assert signal.evidence_ids, "knowledge signals must cite evidence"
        assert all(i in outcome.graph.nodes for i in signal.evidence_ids)
    top = reasoning.hypotheses[0]
    assert top.category.value == "rtl_bug"
    trace_sources = {c.source for c in top.confidence_trace.contributions}
    assert "knowledge:axi.no-response-after-accept" in trace_sources


# --- Architecture boundaries -----------------------------------------------


def test_knowledge_never_depends_on_ai():
    banned = ("anthropic", "reasoning.ai", "AIReasoner", "import openai")
    for path in (SRC / "knowledge").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for term in banned:
            assert term not in text, f"{path.name} references {term}"


def test_reasoning_has_no_knowledge_dependency():
    for package in ("reasoning", "rules"):
        for path in (SRC / package).glob("*.py"):
            assert "veritriage.knowledge" not in path.read_text(encoding="utf-8"), path.name


def test_reasoning_executes_with_ai_disabled(fixture_log):
    # The whole knowledge + reasoning stack runs and concludes without any
    # AI: default engines, no API key, no network.
    outcome = analyze(fixture_log("axi_timeout.log"))
    assert outcome.report.reasoning.hypotheses
    assert outcome.report.reasoning.ai_review is None
    assert outcome.report.knowledge is not None
    # And a bare ReasoningEngine (no knowledge rules) still works unchanged.
    bare = ReasoningEngine().reason(outcome.graph)
    assert bare.hypotheses
    assert not any(s.name.startswith("knowledge:") for s in bare.signals)
