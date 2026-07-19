"""Deterministic failure signatures.

A signature is a stable, content-derived fingerprint of *what kind of failure*
a regression is, independent of when or where it ran. Two runs that fail the
same way (same category, same assertions, same affected scopes, same signals
firing, same competing explanations) produce byte-identical signatures, so
"have we seen this before?" is an exact lookup before any similarity math.

Signatures deliberately exclude anything run-specific: timestamps, seeds,
line numbers, node IDs, and confidences all vary between runs of the same
underlying bug and would destroy stability.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

from veritriage.models import AnalysisReport

if TYPE_CHECKING:
    from veritriage.graph.graph import EvidenceGraph

__all__ = ["FailureSignature", "build_signature"]


class FailureSignature(BaseModel):
    """The normalized fields a signature is computed from, plus the digest."""

    category: str = Field(description="Primary failure classification value.")
    assertions: list[str] = Field(
        default_factory=list, description="Sorted failing assertion names/paths."
    )
    modules: list[str] = Field(
        default_factory=list, description="Sorted design/testbench scopes carrying failing evidence."
    )
    signals: list[str] = Field(
        default_factory=list, description="Sorted names of the reasoning signals that fired."
    )
    hypotheses: list[str] = Field(
        default_factory=list, description="Sorted categories of the generated hypotheses."
    )
    rule: str = Field(description="Classification rule that produced the primary verdict.")

    @property
    def digest(self) -> str:
        """Stable short digest of the canonical signature content."""
        canonical = json.dumps(self.model_dump(), sort_keys=True, separators=(",", ":"))
        return "sig-" + hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:12]


def build_signature(
    report: AnalysisReport, graph: "EvidenceGraph | None" = None
) -> FailureSignature:
    """Compute the deterministic signature of one analyzed regression.

    Pure function of its inputs: no I/O, no randomness, no clock. The same
    analysis always yields the same signature, which is what makes signatures
    usable as exact-match keys in the regression database.

    Args:
        report: The analysis to fingerprint.
        graph: When given, affected modules come from failing evidence nodes;
            otherwise from the recommendations' module fields.
    """
    assertions = sorted(
        {
            (getattr(f, "assertion_path", None) or f.description)
            for f in report.failures
            if f.kind == "assertion_failure"
        }
    )
    if graph is not None:
        modules = sorted({n.module for n in graph.failing() if n.module})
    elif report.reasoning is not None:
        modules = sorted({r.module for r in report.reasoning.recommendations if r.module})
    else:
        modules = []
    signals: list[str] = []
    hypotheses: list[str] = []
    if report.reasoning is not None:
        signals = sorted({s.name for s in report.reasoning.signals})
        hypotheses = sorted({h.category.value for h in report.reasoning.hypotheses})
    return FailureSignature(
        category=report.classification.category.value,
        assertions=assertions,
        modules=modules,
        signals=signals,
        hypotheses=hypotheses,
        rule=report.classification.rule_name,
    )
