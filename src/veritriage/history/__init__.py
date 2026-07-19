"""Regression history: the layer that makes VeriTriage remember.

Sits strictly downstream of the reasoning engine. Design rationale and the
full data flow: docs/REGRESSION_INTELLIGENCE.md.
"""

from veritriage.history.engine import HistoryEngine
from veritriage.history.record import (
    ExecutionMetadata,
    RegressionRecord,
    capture_execution_metadata,
    extract_run_context,
    new_regression_id,
)

__all__ = [
    "ExecutionMetadata",
    "HistoryEngine",
    "RegressionRecord",
    "capture_execution_metadata",
    "extract_run_context",
    "new_regression_id",
]
