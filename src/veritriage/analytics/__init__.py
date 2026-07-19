"""Regression analytics: what the whole history says, not one run.

Everything here is a pure aggregation over stored RegressionRecords. The
outputs serve two audiences: verification engineers (which assertions and
modules keep failing, what resembles my failure) and project leads (trend,
failure mix, how much is still unexplained).
"""

from veritriage.analytics.compute import RegressionAnalytics, cluster_regressions
from veritriage.analytics.models import (
    AnalyticsReport,
    Counter,
    DailyPoint,
    FailureCluster,
)

__all__ = [
    "AnalyticsReport",
    "Counter",
    "DailyPoint",
    "FailureCluster",
    "RegressionAnalytics",
    "cluster_regressions",
]
