"""The RegressionRecord: one completed analysis, preserved in full.

A record is everything VeriTriage knew about one run: execution metadata,
the Evidence Graph, the reasoning output, the classification, and the
deterministic failure signature. Records are the platform's historical
memory; nothing in them is ever summarized away, so future capabilities
(better similarity, better analytics, learned feedback) can re-read old
regressions without re-running anything.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from veritriage.graph.graph import EvidenceGraph
from veritriage.graph.model import ArtifactType
from veritriage.models import AnalysisReport
from veritriage.signatures import FailureSignature


class ExecutionMetadata(BaseModel):
    """Where and on what code a regression ran; every field is best-effort."""

    git_commit: str | None = None
    branch: str | None = None
    author: str | None = None


class RegressionRecord(BaseModel):
    """One analyzed regression, stored verbatim in the regression database."""

    schema_version: str = "1"
    regression_id: str
    created_at: datetime
    execution: ExecutionMetadata = Field(default_factory=ExecutionMetadata)
    test_name: str | None = None
    seed: str | None = None
    configuration: dict[str, Any] = Field(
        default_factory=dict, description="Run configuration from test metadata, when present."
    )
    signature: FailureSignature
    embedding: dict[str, float] = Field(
        default_factory=dict, description="Sparse feature embedding used for similarity search."
    )
    report: AnalysisReport
    graph: EvidenceGraph

    @property
    def classification(self) -> str:
        return self.report.classification.category.value

    @property
    def confidence(self) -> int:
        return self.report.classification.confidence

    @property
    def is_failure(self) -> bool:
        return self.classification != "no_failure"

    @property
    def top_hypothesis(self) -> str | None:
        """Title of the highest-ranked hypothesis, if reasoning ran."""
        if self.report.reasoning and self.report.reasoning.hypotheses:
            return self.report.reasoning.hypotheses[0].title
        return None


def extract_run_context(graph: EvidenceGraph) -> tuple[str | None, str | None, dict[str, Any]]:
    """Pull (test_name, seed, configuration) from test-metadata evidence."""
    for node in graph.nodes_of_type(ArtifactType.TEST_METADATA):
        attrs = dict(node.attributes)
        seed = attrs.pop("seed", None)
        test_name = attrs.pop("test_name", None) or node.module
        attrs.pop("raw_line", None)
        return test_name, (str(seed) if seed is not None else None), attrs
    return None, None, {}


def capture_execution_metadata(cwd: Path | None = None) -> ExecutionMetadata:
    """Read git commit/branch/author from the working directory, best-effort.

    Any git failure (not a repo, git missing) degrades to empty fields; the
    record stays valid either way.
    """

    def _git(*args: str) -> str | None:
        try:
            out = subprocess.run(
                ["git", *args],
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            ).stdout.strip()
            return out or None
        except (OSError, subprocess.SubprocessError):
            return None

    return ExecutionMetadata(
        git_commit=_git("rev-parse", "HEAD"),
        branch=_git("rev-parse", "--abbrev-ref", "HEAD"),
        author=_git("log", "-1", "--format=%an"),
    )


def new_regression_id(signature_digest: str, now: datetime | None = None) -> str:
    """Unique per-run ID: signature fragment + UTC timestamp.

    Readable on purpose: the prefix tells an engineer at a glance whether two
    regressions share a signature, and the timestamp orders them.
    """
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y%m%d%H%M%S%f")
    return f"reg-{signature_digest.removeprefix('sig-')}-{stamp}"
