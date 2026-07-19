"""Analytics, clustering, and dashboard tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from veritriage.analytics import RegressionAnalytics, cluster_regressions
from veritriage.dashboard import DashboardGenerator
from veritriage.history import HistoryEngine
from veritriage.pipeline import analyze
from veritriage.storage import RegressionStore

T0 = datetime(2026, 7, 1, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture()
def store(tmp_path):
    with RegressionStore(tmp_path / "regressions.db") as s:
        yield s


@pytest.fixture()
def populated(store, fixture_log):
    """Three scoreboard failures, one timeout, one clean run, over three days."""
    engine = HistoryEngine(store)
    scoreboard = [
        fixture_log("uvm_scoreboard.log"),
        fixture_log("coverage.txt"),
        fixture_log("test_metadata.json"),
    ]
    for day in range(3):
        engine.record(analyze(scoreboard), now=T0 + timedelta(days=day))
    engine.record(analyze(fixture_log("uvm_timeout.log")), now=T0 + timedelta(days=1, hours=2))
    engine.record(analyze(fixture_log("uvm_pass.log")), now=T0 + timedelta(days=2, hours=2))
    return store


def test_analytics_aggregations(populated):
    a = RegressionAnalytics(populated).compute()
    assert a.total_runs == 5
    assert a.total_failures == 4
    assert a.failure_rate == pytest.approx(0.8)
    assert a.unknown_failures == 0
    assert a.distinct_signatures == 2

    categories = {c.label: c.count for c in a.failure_categories}
    assert categories == {"Testbench Failure": 3, "Timeout": 1}
    assert a.failing_modules[0].count >= 3  # the scoreboard scope dominates
    signals = {c.label for c in a.signal_frequency}
    assert "scoreboard-mismatch" in signals
    assert "timeout-deadlock" in signals
    assert sum(p.runs for p in a.daily) == 5
    assert sum(p.failures for p in a.daily) == 4
    assert len(a.daily) == 3
    assert a.repeated_recommendations[0].count >= 2
    assert a.heatmap  # module x category counts exist for the failing scope


def test_clustering_groups_same_signature(populated):
    a = RegressionAnalytics(populated).compute()
    assert len(a.clusters) == 2
    biggest = a.clusters[0]
    assert biggest.size == 3
    assert biggest.category == "Testbench Failure"
    assert "axi_random_test" in biggest.tests
    # Deterministic: recompute yields the identical clustering.
    b = RegressionAnalytics(populated).compute()
    assert [c.model_dump() for c in a.clusters] == [c.model_dump() for c in b.clusters]


def test_clustering_of_empty_history():
    assert cluster_regressions([]) == []


def test_dashboard_renders_all_sections(populated, tmp_path):
    path = DashboardGenerator(populated).write(tmp_path / "dashboard.html")
    html = path.read_text(encoding="utf-8")
    for section in (
        "Regression History",
        "Recent Regressions",
        "Failure Clusters",
        "Most Unstable Modules",
        "Failure Types",
        "Reasoning Signal Frequency",
        "Classification Confidence",
        "Most Repeated Recommendations",
        "Failure Trend",
        "Regression Heatmap",
    ):
        assert section in html, f"missing section: {section}"
    assert "axi_random_test" in html
    assert "Testbench Failure" in html


def test_dashboard_on_empty_database(tmp_path):
    with RegressionStore(tmp_path / "empty.db") as store:
        html = DashboardGenerator(store).render()
    assert "No regressions stored yet" in html
    assert "Failure Clusters" not in html
