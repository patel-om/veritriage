"""SQLite-backed regression database.

One file, zero extra dependencies, safe for the scale a verification team
actually produces (thousands of regressions). Full records are stored as
JSON blobs so nothing is lost; the columns that queries and analytics need
(signature, classification, timestamps) are indexed alongside.

The store is an adapter: everything above it (history, similarity,
analytics, dashboard) talks to this class, so swapping SQLite for a server
database later is a storage-layer change only.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

from veritriage.feedback import FeedbackRecord

if TYPE_CHECKING:  # storage sits below history; import it lazily to avoid a cycle
    from veritriage.history.record import RegressionRecord


def _load_record(blob: str) -> "RegressionRecord":
    from veritriage.history.record import RegressionRecord

    return RegressionRecord.model_validate_json(blob)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS regressions (
    regression_id TEXT PRIMARY KEY,
    created_at    TEXT NOT NULL,
    test_name     TEXT,
    classification TEXT NOT NULL,
    confidence    INTEGER NOT NULL,
    signature     TEXT NOT NULL,
    git_commit    TEXT,
    branch        TEXT,
    record        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_regressions_signature ON regressions (signature);
CREATE INDEX IF NOT EXISTS idx_regressions_created ON regressions (created_at);

CREATE TABLE IF NOT EXISTS feedback (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    regression_id TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    record        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_feedback_regression ON feedback (regression_id);
"""


class RegressionStore:
    """The regression database: VeriTriage's historical memory."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self.path)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "RegressionStore":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # --- Regressions -------------------------------------------------------

    def save(self, record: "RegressionRecord") -> None:
        """Insert one completed analysis (records are immutable once stored)."""
        self._conn.execute(
            "INSERT OR REPLACE INTO regressions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record.regression_id,
                record.created_at.isoformat(),
                record.test_name,
                record.classification,
                record.confidence,
                record.signature.digest,
                record.execution.git_commit,
                record.execution.branch,
                record.model_dump_json(),
            ),
        )
        self._conn.commit()

    def get(self, regression_id: str) -> RegressionRecord | None:
        row = self._conn.execute(
            "SELECT record FROM regressions WHERE regression_id = ?", (regression_id,)
        ).fetchone()
        return _load_record(row[0]) if row else None

    def recent(self, limit: int = 20) -> list[RegressionRecord]:
        """Most recent regressions, newest first."""
        rows = self._conn.execute(
            "SELECT record FROM regressions ORDER BY created_at DESC, regression_id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [_load_record(r[0]) for r in rows]

    def all_records(self) -> list[RegressionRecord]:
        """Every stored regression, oldest first (analytics input)."""
        rows = self._conn.execute(
            "SELECT record FROM regressions ORDER BY created_at ASC, regression_id ASC"
        ).fetchall()
        return [_load_record(r[0]) for r in rows]

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM regressions").fetchone()[0]

    def count_signature(self, signature_digest: str) -> int:
        """How many stored regressions carry exactly this failure signature."""
        return self._conn.execute(
            "SELECT COUNT(*) FROM regressions WHERE signature = ?", (signature_digest,)
        ).fetchone()[0]

    def with_signature(self, signature_digest: str) -> list[RegressionRecord]:
        rows = self._conn.execute(
            "SELECT record FROM regressions WHERE signature = ? ORDER BY created_at DESC",
            (signature_digest,),
        ).fetchall()
        return [_load_record(r[0]) for r in rows]

    # --- Feedback (implements veritriage.feedback.FeedbackSink) ------------

    def save_feedback(self, record: FeedbackRecord) -> None:
        self._conn.execute(
            "INSERT INTO feedback (regression_id, created_at, record) VALUES (?, ?, ?)",
            (record.regression_id, record.created_at.isoformat(), record.model_dump_json()),
        )
        self._conn.commit()

    def feedback_for(self, regression_id: str) -> list[FeedbackRecord]:
        rows = self._conn.execute(
            "SELECT record FROM feedback WHERE regression_id = ? ORDER BY id ASC",
            (regression_id,),
        ).fetchall()
        return [FeedbackRecord.model_validate_json(r[0]) for r in rows]

    def all_feedback(self) -> list[FeedbackRecord]:
        rows = self._conn.execute("SELECT record FROM feedback ORDER BY id ASC").fetchall()
        return [FeedbackRecord.model_validate_json(r[0]) for r in rows]

    def confirmed_root_cause(self, regression_id: str) -> str | None:
        """The engineer-confirmed root cause for a regression, if any was recorded."""
        for fb in reversed(self.feedback_for(regression_id)):
            if fb.actual_root_cause:
                return fb.actual_root_cause
        return None
