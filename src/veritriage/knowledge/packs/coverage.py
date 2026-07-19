"""Functional coverage Knowledge Pack.

Coverage evidence changes the meaning of both failures and passes: a hole
near a failure marks under-tested logic; a hole in a passing regression
means the pass proves less than it appears to.
"""

from __future__ import annotations

from veritriage.knowledge.model import (
    Concept,
    DebugPlaybook,
    EvidenceClause,
    FailurePattern,
    KnowledgePack,
    PlaybookStep,
)
from veritriage.knowledge.registry import register_pack


@register_pack
def coverage_pack() -> KnowledgePack:
    return KnowledgePack(
        id="coverage",
        name="Functional coverage",
        version="1.0.0",
        domain="coverage",
        summary="What coverage holes mean next to failures and next to passes.",
        concepts=[
            Concept(
                id="coverage.hole",
                name="Coverage hole",
                summary=(
                    "A covergroup or scope below target means scenarios the plan calls "
                    "for were never exercised. Holes are not failures, but they bound "
                    "how much any green run actually demonstrates."
                ),
                markers=[r"coverage", r"covergroup", r"\bhole\b", r"\d+(?:\.\d+)?%"],
            ),
        ],
        patterns=[
            FailurePattern(
                id="coverage.hole-near-failure",
                name="Coverage hole overlapping a failure",
                summary=(
                    "The failing scope is also under-covered: the logic around the "
                    "failure has not been exercised enough for its behavior to be "
                    "trusted, and the stimulus may be missing the very scenarios that "
                    "would have caught this earlier."
                ),
                required=[
                    EvidenceClause(
                        name="coverage hole present",
                        pattern=r".",
                        artifact_types=["coverage"],
                    ),
                    EvidenceClause(
                        name="failure present",
                        pattern=r".",
                        must_fail=True,
                    ),
                ],
                typical_causes=[
                    "Stimulus constraints exclude the corner the bug lives in",
                    "New RTL landed without matching coverage-driven tests",
                ],
                ownership="testbench",
                suggested_signals=["covergroup bins for the failing scope"],
                playbook_id="coverage.hole-review",
                confidence_modifiers={"rtl_bug": 0.04, "testbench_issue": 0.03},
            ),
        ],
        playbooks=[
            DebugPlaybook(
                id="coverage.hole-review",
                name="Coverage hole review",
                steps=[
                    PlaybookStep(action="List the unhit bins in the failing scope"),
                    PlaybookStep(action="Map each unhit bin to the stimulus constraint that should reach it"),
                    PlaybookStep(action="Add or relax constraints to target the hole, then re-run", detail="A directed test at the hole often reproduces the failure faster."),
                ],
            ),
        ],
    )
