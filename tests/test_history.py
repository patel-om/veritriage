"""Regression-intelligence tests: signatures, storage, similarity, history.

Also the Milestone 4 architecture boundary: historical intelligence augments
reasoning without modifying it, so the reasoning package must never depend on
history, storage, similarity, analytics, feedback, or the dashboard.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from veritriage.feedback import FeedbackRecord
from veritriage.history import HistoryEngine, capture_execution_metadata
from veritriage.pipeline import analyze
from veritriage.signatures import build_signature
from veritriage.similarity import FeatureEmbedding, SimilarFailureEngine, cosine
from veritriage.storage import RegressionStore

T0 = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture()
def store(tmp_path):
    with RegressionStore(tmp_path / "regressions.db") as s:
        yield s


@pytest.fixture()
def engine(store):
    return HistoryEngine(store)


def _scoreboard_run(fixture_log):
    return analyze(
        [
            fixture_log("uvm_scoreboard.log"),
            fixture_log("coverage.txt"),
            fixture_log("test_metadata.json"),
        ]
    )


# --- Failure signatures ----------------------------------------------------


def test_signature_is_stable_across_runs(fixture_log):
    a = _scoreboard_run(fixture_log)
    b = _scoreboard_run(fixture_log)
    assert build_signature(a.report, a.graph) == build_signature(b.report, b.graph)
    assert build_signature(a.report, a.graph).digest == build_signature(b.report, b.graph).digest


def test_signature_distinguishes_failure_modes(fixture_log):
    scoreboard = _scoreboard_run(fixture_log)
    timeout = analyze(fixture_log("uvm_timeout.log"))
    sig_a = build_signature(scoreboard.report, scoreboard.graph)
    sig_b = build_signature(timeout.report, timeout.graph)
    assert sig_a.digest != sig_b.digest
    assert sig_a.category == "testbench_failure"
    assert sig_b.category == "timeout"


def test_signature_ignores_run_specific_noise(fixture_log):
    # The digest must not incorporate anything volatile: two analyses of the
    # same artifacts differ in generated_at, yet fingerprint identically.
    a = _scoreboard_run(fixture_log)
    b = _scoreboard_run(fixture_log)
    assert a.report.generated_at != b.report.generated_at
    assert build_signature(a.report, a.graph).digest == build_signature(b.report, b.graph).digest


# --- Regression store ------------------------------------------------------


def test_record_round_trip(store, engine, fixture_log):
    record, _ = engine.record(_scoreboard_run(fixture_log), now=T0)
    loaded = store.get(record.regression_id)
    assert loaded == record
    assert loaded.test_name == "axi_random_test"
    assert loaded.seed == "987654321"
    assert loaded.graph.nodes  # the full Evidence Graph survives storage
    assert loaded.report.reasoning is not None


def test_store_counts_and_recency(store, engine, fixture_log):
    for i in range(3):
        engine.record(_scoreboard_run(fixture_log), now=T0 + timedelta(hours=i))
    assert store.count() == 3
    recent = store.recent(limit=2)
    assert len(recent) == 2
    assert recent[0].created_at > recent[1].created_at


# --- Similarity ------------------------------------------------------------


def test_identical_failure_is_seen_before(engine, fixture_log):
    _, first = engine.record(_scoreboard_run(fixture_log), now=T0)
    assert not first.seen_before
    assert first.similar == []

    _, second = engine.record(_scoreboard_run(fixture_log), now=T0 + timedelta(hours=1))
    assert second.seen_before
    assert second.times_seen == 1
    assert second.similar[0].score == 1.0
    assert second.similar[0].signature_match
    assert second.similar[0].classification == "testbench_failure"


def test_different_failure_mode_is_not_confused(engine, fixture_log):
    engine.record(_scoreboard_run(fixture_log), now=T0)
    _, context = engine.record(
        analyze(fixture_log("uvm_timeout.log")), now=T0 + timedelta(hours=1)
    )
    assert not context.seen_before
    assert all(s.signature_match is False for s in context.similar)
    assert all(s.score < 1.0 for s in context.similar)


def test_clean_run_reports_no_similars(engine, fixture_log):
    engine.record(_scoreboard_run(fixture_log), now=T0)
    _, context = engine.record(
        analyze(fixture_log("uvm_pass.log")), now=T0 + timedelta(hours=1)
    )
    assert context.similar == []


def test_embedding_is_deterministic_and_normalized(engine, fixture_log):
    record, _ = engine.record(_scoreboard_run(fixture_log), now=T0)
    again = FeatureEmbedding().embed(record)
    assert record.embedding == again
    assert cosine(again, again) == pytest.approx(1.0)


def test_feedback_root_cause_surfaces_in_similarity(store, engine, fixture_log):
    record, _ = engine.record(_scoreboard_run(fixture_log), now=T0)
    store.save_feedback(
        FeedbackRecord(
            regression_id=record.regression_id,
            diagnosis="incorrect",
            actual_root_cause="stale predictor entry after reset in axi_scoreboard",
        )
    )
    _, context = engine.record(_scoreboard_run(fixture_log), now=T0 + timedelta(hours=1))
    assert context.similar[0].root_cause == "stale predictor entry after reset in axi_scoreboard"


# --- Report augmentation ---------------------------------------------------


def test_augment_attaches_history_and_precedent_step(engine, fixture_log):
    engine.record(_scoreboard_run(fixture_log), now=T0)
    outcome = _scoreboard_run(fixture_log)
    _, context = engine.record(outcome, now=T0 + timedelta(hours=1))
    before = list(outcome.report.reasoning.recommendations)
    engine.augment(outcome, context)

    assert outcome.report.history is context
    added = outcome.report.reasoning.recommendations[len(before) :]
    assert len(added) == 1
    assert "Compare against regression" in added[0].action
    assert added[0].priority > max(r.priority for r in before)
    # History augments; it never rewrites what the reasoning engine produced.
    assert outcome.report.reasoning.recommendations[: len(before)] == before
    assert outcome.report.model_dump_json()  # still serializable end to end


def test_augment_on_new_failure_adds_no_step(engine, fixture_log):
    outcome = _scoreboard_run(fixture_log)
    _, context = engine.record(outcome, now=T0)
    before = len(outcome.report.reasoning.recommendations)
    engine.augment(outcome, context)
    assert outcome.report.history is context
    assert len(outcome.report.reasoning.recommendations) == before


# --- Feedback --------------------------------------------------------------


def test_feedback_round_trip(store):
    record = FeedbackRecord(
        regression_id="reg-x",
        diagnosis="correct",
        useful_recommendations=["Inspect the scoreboard compare"],
        notes="fixed by tb change",
    )
    store.save_feedback(record)
    loaded = store.feedback_for("reg-x")
    assert loaded == [record]
    assert store.all_feedback() == [record]


# --- Execution metadata ----------------------------------------------------


def test_capture_execution_metadata_degrades_gracefully(tmp_path):
    meta = capture_execution_metadata(cwd=tmp_path)  # not a git repository
    assert meta.git_commit is None
    assert meta.branch is None


# --- Architecture boundaries -----------------------------------------------

_M4_PACKAGES = ("history", "storage", "similarity", "analytics", "feedback", "dashboard")


def test_reasoning_engine_is_untouched_by_history():
    # Milestone 4's core promise: historical intelligence augments reasoning
    # without modifying it. No reasoning (or rules) source may import any
    # regression-intelligence package.
    src = Path(__file__).parent.parent / "src" / "veritriage"
    for package in ("reasoning", "rules"):
        for path in (src / package).glob("*.py"):
            text = path.read_text(encoding="utf-8")
            for m4 in _M4_PACKAGES:
                assert f"veritriage.{m4}" not in text, f"{path.name} imports {m4}"


def test_pipeline_does_not_touch_storage(fixture_log, tmp_path, monkeypatch):
    # analyze() stays pure: recording is the CLI/history layer's decision.
    monkeypatch.chdir(tmp_path)
    analyze(fixture_log("uvm_scoreboard.log"))
    assert not (tmp_path / ".veritriage").exists()
