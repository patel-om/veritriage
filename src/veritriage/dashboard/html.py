"""Self-contained HTML dashboard renderer (Jinja2, no external assets).

Renders the AnalyticsReport into an engineering analytics page: stat tiles,
recent regressions, failure clusters, module/assertion hotspots, trends,
confidence distribution, and the module-by-category heatmap. Same design
system as report.html; no JavaScript.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jinja2 import Environment, PackageLoader, select_autoescape

from veritriage.analytics import RegressionAnalytics
from veritriage.storage import RegressionStore

#: Failure-category value -> status role (same palette as report.html).
_STATUS_ROLE = {
    "no_failure": "good",
    "unknown_failure": "warning",
    "timeout": "serious",
    "testbench_failure": "serious",
    "compile_failure": "critical",
    "assertion_failure": "critical",
    "fatal_error": "critical",
}


class DashboardGenerator:
    """Renders the regression database into a single dashboard.html."""

    def __init__(self, store: RegressionStore) -> None:
        self._store = store
        self._env = Environment(
            loader=PackageLoader("veritriage.dashboard", "templates"),
            autoescape=select_autoescape(("html", "j2")),
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def render(self) -> str:
        analytics = RegressionAnalytics(self._store).compute()
        recent = [
            {
                "id": r.regression_id,
                "when": r.created_at.strftime("%Y-%m-%d %H:%M"),
                "test": r.test_name or "-",
                "category": r.report.classification.category.display_name,
                "role": _STATUS_ROLE.get(r.classification, "warning"),
                "confidence": r.confidence,
                "hypothesis": r.top_hypothesis or "-",
                "commit": (r.execution.git_commit or "")[:9] or "-",
            }
            for r in self._store.recent(limit=12)
        ]
        template = self._env.get_template("dashboard.html.j2")
        return template.render(
            a=analytics,
            recent=recent,
            bars=_bars,
            heat=_heatmap_rows(analytics.heatmap),
            trend=_trend(analytics),
            generated=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
            db_path=str(self._store.path),
        )

    def write(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.render(), encoding="utf-8")
        return path


def _bars(counters: list[Any]) -> list[dict[str, Any]]:
    """Counter list -> rows with percentage widths against the row maximum."""
    peak = max((c.count for c in counters), default=0)
    return [
        {
            "label": c.label,
            "count": c.count,
            "share": f"{c.share:.0%}",
            "width": (c.count / peak * 100) if peak else 0,
        }
        for c in counters
    ]


def _heatmap_rows(heatmap: dict[str, dict[str, int]]) -> dict[str, Any] | None:
    """Module x category matrix with per-cell opacity for the meter color."""
    if not heatmap:
        return None
    categories = sorted({c for cats in heatmap.values() for c in cats})
    peak = max((n for cats in heatmap.values() for n in cats.values()), default=1)
    rows = []
    for module, cats in heatmap.items():
        cells = []
        for category in categories:
            count = cats.get(category, 0)
            cells.append(
                {"count": count, "alpha": 0.12 + 0.68 * count / peak if count else 0.0}
            )
        rows.append({"module": module, "cells": cells})
    return {"categories": categories, "rows": rows}


def _trend(analytics: Any) -> list[dict[str, Any]]:
    peak = max((p.runs for p in analytics.daily), default=0)
    return [
        {
            "day": p.day,
            "runs": p.runs,
            "failures": p.failures,
            "runs_w": (p.runs / peak * 100) if peak else 0,
            "fail_w": (p.failures / peak * 100) if peak else 0,
        }
        for p in analytics.daily[-30:]
    ]
