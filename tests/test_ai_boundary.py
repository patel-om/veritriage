"""Architectural guard: the AI layer reasons over the Evidence Graph only.

These tests pin the boundary rather than the AI output (which needs a live
API): the summarizer must not touch the filesystem, and its failure mode
without the optional dependency must be clean.
"""

from __future__ import annotations

import inspect

import pytest

import veritriage.analyzers.summary as summary_module
from veritriage.analyzers import AISummarizer, AISummaryError
from veritriage.pipeline import analyze


def test_summarizer_signature_takes_graph_not_paths():
    params = inspect.signature(AISummarizer.summarize).parameters
    assert "graph" in params
    assert "path" not in params and "paths" not in params


def test_summarizer_source_never_reads_files():
    # The module must not open artifacts: its only inputs are the report and
    # the graph's reasoning view. A file read here would break the boundary.
    source = inspect.getsource(summary_module)
    assert "read_text" not in source
    assert "open(" not in source
    assert "Path(" not in source


def test_missing_sdk_raises_clean_error(fixture_log):
    if AISummarizer.available():  # pragma: no cover - environment-dependent
        pytest.skip("anthropic installed; this test covers the missing-SDK path")
    outcome = analyze(fixture_log("uvm_assertion.log"))
    with pytest.raises(AISummaryError, match="not installed"):
        AISummarizer().summarize(outcome.report, outcome.graph)
